"""
NLP Worker
Consumes review sync jobs from RabbitMQ.
Run with: python -m app.services.nlp.worker
"""
import asyncio
import json

import aio_pika
import structlog

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_mongo, init_postgres, init_redis
from app.services.ingestion.queue import SYNC_QUEUE_NAME
from app.services.ingestion.sync_service import ingestion_sync_service

log = structlog.get_logger()


async def process_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            log.info("Processing sync job",
                connector_id=payload.get("connector_id"),
                platform=payload.get("platform"),
            )
            async with AsyncSessionLocal() as db:
                changed = await ingestion_sync_service.sync_connector(db, payload)
                log.info("Sync job complete",
                    connector_id=payload.get("connector_id"),
                    reviews_changed=changed,
                )
        except Exception as exc:
            log.error("Failed to process sync job", error=str(exc))
            raise


async def main() -> None:
    log.info("Starting NLP worker")
    await init_postgres()
    await init_mongo()
    await init_redis()
    log.info("All connections ready, listening for jobs")

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(SYNC_QUEUE_NAME, durable=True)
        log.info("Waiting for sync jobs", queue=SYNC_QUEUE_NAME)
        await queue.consume(process_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
