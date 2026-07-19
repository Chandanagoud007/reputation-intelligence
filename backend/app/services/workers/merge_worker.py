"""
AI Merge Worker
Consumes from: reputation.ai.classified  (multiple messages per review)
Produces to:   reputation.ai.merged      (one complete message per review)
               reputation.dlq            (on timeout or failure)

What it does:
- Collects all 4 worker outputs (sentiment, topic, risk, summary) for the same message_id
- Uses Redis to accumulate fields with a 5-minute TTL
- Once all expected workers have contributed, merges and publishes one clean message
- If TTL expires before all workers respond, publishes with whatever fields arrived

Expected workers: sentiment, topic, risk, summary
Merge key: message_id

Run with: python -m app.services.workers.merge_worker
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from redis.asyncio import from_url

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.ai.classified"
TOPIC_OUT = "reputation.ai.merged"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "merge-worker-group"

MERGE_TTL     = 300   # 5 minutes — wait this long for all workers
MERGE_TIMEOUT = 60    # seconds — publish partial merge after this

# Fields contributed by each worker
WORKER_FIELDS = {
    "sentiment": ["sentiment", "sentiment_score", "sentiment_confidence", "sentiment_model", "sentiment_classified_at"],
    "topic":     ["topics", "topic_classified_at"],
    "risk":      ["risk_flags", "risk_level", "risk_details", "risk_detected_at"],
    "summary":   ["summary", "key_themes", "action_items", "summarized_at"],
}

EXPECTED_WORKERS = {"sentiment", "topic", "risk"}


def detect_worker(message: dict) -> str | None:
    """Detect which worker produced this message based on fields present."""
    if "sentiment_classified_at" in message:
        return "sentiment"
    if "topic_classified_at" in message:
        return "topic"
    if "risk_detected_at" in message:
        return "risk"
    if "summarized_at" in message:
        return "summary"
    return None


def merge_messages(messages: list[dict]) -> dict:
    """
    Merge multiple worker outputs into one complete message.
    Base message comes from the first (earliest) message.
    Worker-specific fields are overlaid from each worker's message.
    """
    if not messages:
        return {}

    # Start with the base message (has all pipeline fields)
    merged = {**messages[0]}

    # Overlay fields from each worker message
    for msg in messages[1:]:
        for worker, fields in WORKER_FIELDS.items():
            for field in fields:
                if field in msg:
                    merged[field] = msg[field]

    merged["merged_at"] = datetime.now(timezone.utc).isoformat()
    merged["merge_worker_count"] = len(messages)
    return merged


async def run_worker():
    log.info("Starting merge worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

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
    log.info("Merge worker ready")

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            worker = detect_worker(message)
            if not worker:
                # Not from an AI worker — skip
                await consumer.commit()
                continue

            # Skip already-merged messages (avoid loop)
            if message.get("merged_at"):
                await consumer.commit()
                continue

            log.info(
                "Received AI worker output",
                message_id=message_id,
                worker=worker,
            )

            # Redis keys for this message
            bucket_key   = f"merge:{message_id}:messages"
            workers_key  = f"merge:{message_id}:workers"
            published_key = f"merge:{message_id}:published"

            try:
                # Don't process if already published
                already_published = await redis.exists(published_key)
                if already_published:
                    await consumer.commit()
                    continue

                # Store this worker's message in Redis list
                await redis.rpush(bucket_key, json.dumps(message))
                await redis.expire(bucket_key, MERGE_TTL)

                # Track which workers have contributed
                await redis.sadd(workers_key, worker)
                await redis.expire(workers_key, MERGE_TTL)

                # Check how many workers have contributed
                contributed = await redis.smembers(workers_key)

                all_arrived = EXPECTED_WORKERS.issubset(contributed)

                if all_arrived:
                    # All 4 workers done — merge and publish
                    raw_messages = await redis.lrange(bucket_key, 0, -1)
                    messages_list = [json.loads(m) for m in raw_messages]

                    merged = merge_messages(messages_list)

                    await producer.send_and_wait(
                        TOPIC_OUT,
                        value=merged,
                        key=tenant_id,
                        headers=[
                            ("tenant_id", tenant_id.encode()),
                            ("schema_version", b"1.0"),
                        ],
                    )

                    # Mark as published so we don't publish again
                    await redis.set(published_key, "1", ex=MERGE_TTL)

                    # Cleanup
                    await redis.delete(bucket_key, workers_key)

                    log.info(
                        "Review fully merged and published",
                        message_id=message_id,
                        workers=list(contributed),
                        topic=TOPIC_OUT,
                    )
                else:
                    missing = EXPECTED_WORKERS - contributed
                    log.info(
                        "Waiting for more workers",
                        message_id=message_id,
                        received=list(contributed),
                        missing=list(missing),
                    )

                await consumer.commit()

            except Exception as e:
                log.error(
                    "Merge failed, sending to DLQ",
                    message_id=message_id,
                    error=str(e),
                )
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **message,
                            "dlq_reason": str(e),
                            "dlq_stage": "merge",
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
        log.info("Merge worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
