"""RabbitMQ helpers for review ingestion jobs."""
import json
from typing import Any

import aio_pika

from app.core.config import settings

SYNC_QUEUE_NAME = "review_sync_jobs"


async def publish_sync_job(payload: dict[str, Any]) -> None:
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(SYNC_QUEUE_NAME, durable=True)
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await channel.default_exchange.publish(message, routing_key=SYNC_QUEUE_NAME)
