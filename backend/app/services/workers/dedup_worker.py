"""
Deduplication Worker
Consumes from: reputation.normalized
Produces to:   reputation.deduplicated
               reputation.dlq (on failure)

What it does:
- Generates SHA-256 fingerprint of (source_platform + source_review_id + text_cleaned)
- Checks Redis for existing fingerprint (fast O(1) lookup)
- Drops duplicates silently — they are NOT forwarded downstream
- Adds fingerprint to Redis with 30-day TTL on first-seen reviews
- Publishes unique reviews to reputation.deduplicated

Run with: python -m app.services.workers.dedup_worker
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from redis.asyncio import from_url

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.normalized"
TOPIC_OUT = "reputation.deduplicated"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "dedup-worker-group"

DEDUP_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def build_fingerprint(message: dict) -> str:
    """
    SHA-256 fingerprint of platform + source_review_id + cleaned text.
    Same review from same platform will always produce the same fingerprint.
    """
    normalized = message.get("normalized_content", {})
    raw_str = "|".join([
        message.get("source_platform", ""),
        message.get("source_review_id", ""),
        normalized.get("text_cleaned", ""),
    ])
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def redis_key(tenant_id: str, fingerprint: str) -> str:
    """Namespace by tenant so cross-tenant dedup is impossible."""
    return f"{tenant_id}:dedup:{fingerprint}"


async def run_worker():
    log.info("Starting dedup worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

    # Redis client
    redis = await from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await redis.ping()
    log.info("Redis connected")

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
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
    log.info("Dedup worker ready, consuming messages")

    try:
        async for msg in consumer:
            message = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            log.info(
                "Received normalized review",
                message_id=message_id,
                tenant_id=tenant_id,
                platform=message.get("source_platform"),
                offset=msg.offset,
            )

            try:
                fingerprint = build_fingerprint(message)
                key         = redis_key(tenant_id, fingerprint)

                # Check if we've seen this review before
                is_duplicate = await redis.exists(key)

                if is_duplicate:
                    log.info(
                        "Duplicate review dropped",
                        message_id=message_id,
                        fingerprint=fingerprint[:16] + "...",
                        tenant_id=tenant_id,
                    )
                    await consumer.commit()
                    continue

                # First time seeing this review — store fingerprint + publish
                await redis.set(key, "1", ex=DEDUP_TTL_SECONDS)

                deduped_message = {
                    **message,
                    "fingerprint": fingerprint,
                    "is_duplicate": False,
                    "deduplicated_at": datetime.now(timezone.utc).isoformat(),
                }

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=deduped_message,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("source_platform", message.get("source_platform", "").encode()),
                        ("schema_version", b"1.0"),
                    ],
                )

                await consumer.commit()

                log.info(
                    "Unique review published",
                    message_id=message_id,
                    fingerprint=fingerprint[:16] + "...",
                    topic=TOPIC_OUT,
                )

            except Exception as e:
                log.error(
                    "Dedup failed, sending to DLQ",
                    message_id=message_id,
                    error=str(e),
                )
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **message,
                            "dlq_reason": str(e),
                            "dlq_stage": "dedup",
                            "dlq_at": datetime.now(timezone.utc).isoformat(),
                        },
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))

    finally:
        await consumer.stop()
        await producer.stop()
        await redis.aclose()
        log.info("Dedup worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
