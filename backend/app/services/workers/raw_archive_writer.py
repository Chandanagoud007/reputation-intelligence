"""
Raw Archive Writer
Consumes from: reputation.raw.ingested
Writes to:     MinIO bucket (rip-raw-reviews)

What it does:
- Reads every raw review from reputation.raw.ingested
- Writes it to MinIO as a JSON file (immutable archive)
- Path: raw-reviews/{tenant_id}/{platform}/{YYYY}/{MM}/{DD}/{message_id}.json
- Runs in parallel with normalize worker — does NOT block the pipeline
- Same consumer group isolation — uses its own group_id

Run with: python -m app.services.workers.raw_archive_writer
"""
import asyncio
import io
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer
from miniopy_async import Minio

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN = "reputation.raw.ingested"
GROUP_ID = "raw-archive-writer-group"


def build_object_path(message: dict) -> str:
    """
    Build the MinIO object path for a raw review.
    Format: raw-reviews/{tenant_id}/{platform}/{YYYY}/{MM}/{DD}/{message_id}.json
    Makes it easy to query by tenant, platform, or date later.
    """
    tenant_id   = message.get("tenant_id", "unknown")
    platform    = message.get("source_platform", "unknown")
    message_id  = message.get("message_id", "unknown")
    ingested_at = message.get("ingested_at", datetime.now(timezone.utc).isoformat())

    try:
        dt = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)

    return f"raw-reviews/{tenant_id}/{platform}/{dt.year}/{dt.month:02d}/{dt.day:02d}/{message_id}.json"


async def run_worker():
    log.info("Starting raw archive writer", topic_in=TOPIC_IN, bucket=settings.MINIO_BUCKET)

    # MinIO client
    minio = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,   # local dev — no TLS
    )

    # Ensure bucket exists
    bucket_exists = await minio.bucket_exists(settings.MINIO_BUCKET)
    if not bucket_exists:
        await minio.make_bucket(settings.MINIO_BUCKET)
        log.info("Created MinIO bucket", bucket=settings.MINIO_BUCKET)
    else:
        log.info("MinIO bucket ready", bucket=settings.MINIO_BUCKET)

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=100,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    await consumer.start()
    log.info("Raw archive writer ready, consuming messages")

    try:
        async for msg in consumer:
            raw = msg.value
            message_id = raw.get("message_id", "unknown")
            tenant_id  = raw.get("tenant_id", "unknown")

            log.info(
                "Archiving raw review",
                message_id=message_id,
                tenant_id=tenant_id,
                platform=raw.get("source_platform"),
                offset=msg.offset,
            )

            try:
                object_path = build_object_path(raw)
                data        = json.dumps(raw, indent=2).encode("utf-8")
                data_stream = io.BytesIO(data)

                await minio.put_object(
                    bucket_name=settings.MINIO_BUCKET,
                    object_name=object_path,
                    data=data_stream,
                    length=len(data),
                    content_type="application/json",
                )

                await consumer.commit()

                log.info(
                    "Raw review archived",
                    message_id=message_id,
                    path=object_path,
                )

            except Exception as e:
                log.error(
                    "Failed to archive review",
                    message_id=message_id,
                    error=str(e),
                )
                # Don't commit — will retry on restart
                # Archive writer failure should never block the pipeline

    finally:
        await consumer.stop()
        log.info("Raw archive writer stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
