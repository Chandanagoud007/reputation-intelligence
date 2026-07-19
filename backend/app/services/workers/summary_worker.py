"""
Summarization Worker
Consumes from: reputation.ai.classified
Produces to:   reputation.ai.classified (adds summary fields, same topic)
               reputation.dlq (on failure)

Model: claude-sonnet-4-20250514 via Anthropic API
Cost gate: only triggered for HIGH/CRITICAL risk OR reviews > 50 chars
Batch: groups 20 reviews per API call to minimize cost
Stub mode: if ANTHROPIC_API_KEY is not set, returns placeholder summary

Run with: python -m app.services.workers.summary_worker
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.ai.classified"
TOPIC_OUT = "reputation.ai.classified"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "summary-worker-group-v2"

BATCH_SIZE      = 20
MIN_TEXT_LENGTH = 50    # chars — skip summarization for very short reviews
TRIGGERED_RISKS = {"HIGH", "CRITICAL"}


# ── Cost gate ─────────────────────────────────────────────────────────────────
def should_summarize(message: dict) -> bool:
    """Only summarize HIGH/CRITICAL risk or long reviews."""
    risk_level  = message.get("risk_level", "NONE")
    text        = message.get("normalized_content", {}).get("text_cleaned", "")
    return risk_level in TRIGGERED_RISKS or len(text) > MIN_TEXT_LENGTH


# ── Claude API call ───────────────────────────────────────────────────────────
async def summarize_batch(reviews: list[dict]) -> list[dict]:
    """
    Call Claude API to summarize a batch of reviews.
    Returns list of {summary, key_themes, action_items} dicts.
    Falls back to stub if API key not set.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")

    if not api_key or api_key in ("CHANGE_ME", ""):
        log.warning("ANTHROPIC_API_KEY not set — using stub summaries")
        return [_stub_summary(r) for r in reviews]

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

        review_list = "\n".join([
            f"{i+1}. [{r.get('source_platform','?')}] Rating: {r.get('normalized_content',{}).get('rating','?')} | "
            f"Risk: {r.get('risk_level','NONE')} | Text: {r.get('normalized_content',{}).get('text_cleaned','')[:300]}"
            for i, r in enumerate(reviews)
        ])

        prompt = f"""You are a reputation analyst. Analyze these {len(reviews)} customer reviews and return a JSON array.

Reviews:
{review_list}

Return ONLY a valid JSON array with exactly {len(reviews)} objects, one per review, in order:
[
  {{
    "summary": "2-3 sentence summary of the review",
    "key_themes": ["theme1", "theme2"],
    "action_items": ["action1", "action2"]
  }}
]

No prose, no markdown, no explanation. Just the JSON array."""

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code blocks if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        results = json.loads(raw)

        if len(results) != len(reviews):
            raise ValueError(f"Expected {len(reviews)} results, got {len(results)}")

        return results

    except Exception as e:
        log.error("Claude API call failed, using stub", error=str(e))
        return [_stub_summary(r) for r in reviews]


def _stub_summary(review: dict) -> dict:
    """Placeholder summary when API key is not set."""
    text = review.get("normalized_content", {}).get("text_cleaned", "")
    return {
        "summary": f"Review summary pending API key configuration. Preview: {text[:100]}...",
        "key_themes": review.get("topics", []),
        "action_items": ["Configure ANTHROPIC_API_KEY to enable AI summaries"],
    }


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting summary worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=BATCH_SIZE,
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
    log.info("Summary worker ready")

    pending_batch = []

    async def flush(batch):
        if not batch:
            return
        summaries = await summarize_batch(batch)
        for message, summary in zip(batch, summaries):
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")
            try:
                enriched = {
                    **message,
                    "summary":      summary.get("summary"),
                    "key_themes":   summary.get("key_themes", []),
                    "action_items": summary.get("action_items", []),
                    "summarized_at": datetime.now(timezone.utc).isoformat(),
                }
                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=enriched,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("schema_version", b"1.0"),
                        ("worker", b"summary"),
                    ],
                )
                await consumer.commit()
                log.info("Review summarized", message_id=message_id)
            except Exception as e:
                log.error("Summary publish failed", message_id=message_id, error=str(e))
                await producer.send_and_wait(
                    TOPIC_DLQ,
                    value={**message, "dlq_reason": str(e), "dlq_stage": "summary", "dlq_at": datetime.now(timezone.utc).isoformat()},
                    key=tenant_id,
                )
                await consumer.commit()

    try:
        async for msg in consumer:
            message = msg.value

            # Skip messages already summarized (avoid loop on same topic)
            if message.get("summarized_at"):
                await consumer.commit()
                continue

            # Process any message that has gone through at least one AI worker
            if not any([
                message.get("sentiment_classified_at"),
                message.get("topic_classified_at"),
                message.get("risk_detected_at"),
            ]):
                await consumer.commit()
                continue

            if not should_summarize(message):
                # Not worth summarizing — pass through with null summary
                enriched = {
                    **message,
                    "summary": None,
                    "key_themes": [],
                    "action_items": [],
                    "summarized_at": datetime.now(timezone.utc).isoformat(),
                }
                tenant_id = message.get("tenant_id", "unknown")
                await producer.send_and_wait(TOPIC_OUT, value=enriched, key=tenant_id)
                await consumer.commit()
                continue

            pending_batch.append(message)

            if len(pending_batch) >= BATCH_SIZE:
                await flush(pending_batch)
                pending_batch = []

    finally:
        await flush(pending_batch)
        await consumer.stop()
        await producer.stop()
        log.info("Summary worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
