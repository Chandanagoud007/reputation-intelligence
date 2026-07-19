"""
Review ingestion queue — Kafka implementation.
Replaces the RabbitMQ aio_pika implementation from Phase 1.
API is intentionally kept similar so callers don't need to change.
"""
from app.services.kafka_producer import publish_review, publish_reviews_batch

__all__ = ["publish_review", "publish_reviews_batch"]
