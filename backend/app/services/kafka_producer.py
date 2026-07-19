"""
Kafka producer for the RIP ingestion gateway.
Replaces the RabbitMQ queue.py from Phase 1.
All reviews entering the system go through here → reputation.raw.ingested
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings

log = structlog.get_logger()

# Single producer instance shared across the app (initialized on startup)
_producer: AIOKafkaProducer | None = None

TOPIC_RAW_INGESTED = "reputation.raw.ingested"
TOPIC_DLQ = "reputation.dlq"


async def init_kafka_producer() -> None:
    """Call this in FastAPI lifespan startup."""
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        # Reliability settings
        acks="all",                  # wait for all replicas to ack
        enable_idempotence=True,     # exactly-once producer semantics
        max_batch_size=163840,       # 160KB batch size
        linger_ms=10,                # wait 10ms to batch records together
        compression_type="gzip",
        request_timeout_ms=30000,
        retry_backoff_ms=500,
    )
    await _producer.start()
    log.info("Kafka producer started", brokers=settings.KAFKA_BOOTSTRAP_SERVERS)


async def close_kafka_producer() -> None:
    """Call this in FastAPI lifespan shutdown."""
    global _producer
    if _producer:
        await _producer.stop()
        log.info("Kafka producer stopped")


async def publish_review(
    tenant_id: str,
    brand_id: str,
    location_id: str | None,
    source_platform: str,
    source_review_id: str,
    rating: float,
    text: str,
    reviewer_name: str | None,
    review_date: str,
    language: str | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Publish a single review to reputation.raw.ingested.
    Returns the message_id for tracing.
    Sends to DLQ if Kafka is unavailable (fail-safe).
    """
    message_id = str(uuid.uuid4())

    payload = {
        "schema_version": "1.0",
        "message_id": message_id,
        "tenant_id": tenant_id,
        "brand_id": brand_id,
        "location_id": location_id,
        "source_platform": source_platform,
        "source_review_id": source_review_id,
        "raw_content": {
            "rating": rating,
            "text": text,
            "reviewer_name": reviewer_name,
            "review_date": review_date,
            "language": language,
        },
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }

    # Partition key: tenant_id ensures all reviews for a tenant
    # land on the same partition (ordered processing per tenant)
    partition_key = tenant_id

    try:
        await _producer.send_and_wait(
            TOPIC_RAW_INGESTED,
            value=payload,
            key=partition_key,
            headers=[
                ("tenant_id", tenant_id.encode()),
                ("source_platform", source_platform.encode()),
                ("schema_version", b"1.0"),
            ],
        )
        log.info(
            "Review published to Kafka",
            message_id=message_id,
            tenant_id=tenant_id,
            platform=source_platform,
            topic=TOPIC_RAW_INGESTED,
        )
        return message_id

    except KafkaConnectionError as e:
        log.error("Kafka unavailable, sending to DLQ", error=str(e), message_id=message_id)
        await _send_to_dlq(payload, reason="kafka_unavailable")
        raise

    except Exception as e:
        log.error("Failed to publish review", error=str(e), message_id=message_id)
        await _send_to_dlq(payload, reason=str(e))
        raise


async def publish_reviews_batch(reviews: list[dict[str, Any]]) -> list[str]:
    """
    Publish a batch of reviews. Returns list of message_ids.
    Used by connectors after a sync to push all fetched reviews at once.
    """
    message_ids = []
    for review in reviews:
        mid = await publish_review(**review)
        message_ids.append(mid)
    return message_ids


async def _send_to_dlq(payload: dict, reason: str) -> None:
    """Last resort — send to dead letter queue so nothing is silently dropped."""
    try:
        dlq_payload = {
            **payload,
            "dlq_reason": reason,
            "dlq_at": datetime.now(timezone.utc).isoformat(),
        }
        await _producer.send_and_wait(TOPIC_DLQ, value=dlq_payload)
        log.warning("Message sent to DLQ", reason=reason, message_id=payload.get("message_id"))
    except Exception as e:
        # If even DLQ fails, log it — at minimum we have the log trail
        log.critical("DLQ publish also failed", error=str(e), payload=payload)
