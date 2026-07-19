"""
Normalize Worker
Consumes from: reputation.raw.ingested
Produces to:   reputation.normalized
               reputation.dlq (on failure)

What it does:
- Strips HTML tags from review text
- Collapses whitespace
- Detects language (langdetect)
- Standardizes review_date to ISO8601 UTC
- Normalizes rating to float 1.0–5.0

Run with: python -m app.services.workers.normalize_worker
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

import emoji

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.raw.ingested"
TOPIC_OUT = "reputation.normalized"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "normalize-worker-group"


# ── HTML stripper ─────────────────────────────────────────────────────────────
class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return "".join(self._parts)


def strip_html(text: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(text or "")
    return stripper.get_text()


def clean_text(text: str) -> str:
    """Strip HTML, convert emoji to text, collapse whitespace, strip leading/trailing spaces."""
    text = strip_html(text)
    text = emoji.demojize(text, delimiters=(" ", " "))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_language(text: str) -> str:
    """Detect language using langdetect. Falls back to 'en' on failure."""
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "en"


def normalize_rating(rating) -> float:
    """Ensure rating is a float between 1.0 and 5.0."""
    try:
        r = float(rating)
        return max(1.0, min(5.0, r))
    except (TypeError, ValueError):
        return 3.0  # neutral fallback


def normalize_date(date_str: str | None) -> str:
    """Standardize date to ISO8601 UTC. Falls back to now() on parse failure."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        # Handle already-valid ISO strings
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


# ── Core normalization logic ──────────────────────────────────────────────────
def normalize_message(raw: dict) -> dict:
    """
    Takes a raw.ingested message, returns a normalized message.
    Preserves all original fields and adds normalized_content block.
    """
    raw_content = raw.get("raw_content", {})

    text_original = raw_content.get("text", "")
    text_cleaned  = clean_text(text_original)

    # Use language from connector if provided, otherwise detect
    language = raw_content.get("language") or detect_language(text_cleaned)

    return {
        "schema_version": "1.0",
        "message_id": raw["message_id"],         # preserve original message_id for tracing
        "source_message_id": raw["message_id"],
        "tenant_id": raw["tenant_id"],
        "brand_id": raw["brand_id"],
        "location_id": raw.get("location_id"),
        "source_platform": raw["source_platform"],
        "source_review_id": raw["source_review_id"],
        "normalized_content": {
            "rating": normalize_rating(raw_content.get("rating")),
            "text_cleaned": text_cleaned,
            "language": language,
            "review_date": normalize_date(raw_content.get("review_date")),
            "reviewer_name": raw_content.get("reviewer_name"),
        },
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "metadata": raw.get("metadata", {}),
    }


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting normalize worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,       # manual commit — only after successful publish
        max_poll_records=50,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        enable_idempotence=True,
    )

    await consumer.start()
    await producer.start()
    log.info("Normalize worker ready, consuming messages")

    try:
        async for msg in consumer:
            raw = msg.value
            message_id = raw.get("message_id", "unknown")
            tenant_id  = raw.get("tenant_id", "unknown")

            log.info(
                "Received raw review",
                message_id=message_id,
                tenant_id=tenant_id,
                platform=raw.get("source_platform"),
                offset=msg.offset,
            )

            try:
                normalized = normalize_message(raw)

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=normalized,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("source_platform", raw.get("source_platform", "").encode()),
                        ("schema_version", b"1.0"),
                    ],
                )

                # Only commit offset AFTER successful publish downstream
                await consumer.commit()

                log.info(
                    "Review normalized and published",
                    message_id=message_id,
                    language=normalized["normalized_content"]["language"],
                    rating=normalized["normalized_content"]["rating"],
                    topic=TOPIC_OUT,
                )

            except Exception as e:
                log.error(
                    "Normalization failed, sending to DLQ",
                    message_id=message_id,
                    error=str(e),
                )
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **raw,
                            "dlq_reason": str(e),
                            "dlq_stage": "normalize",
                            "dlq_at": datetime.now(timezone.utc).isoformat(),
                        },
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))
                    # Don't commit — message will be reprocessed on restart

    finally:
        await consumer.stop()
        await producer.stop()
        log.info("Normalize worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
