"""
Connector Base Class
All platform connectors inherit from this.
Updated in Phase 2: after fetching reviews, publishes each one
to reputation.raw.ingested via Kafka instead of storing directly.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import ReviewCreate
from app.services.kafka_producer import publish_review

log = structlog.get_logger()


class ConnectorBase(ABC):
    platform: str = ""

    def __init__(self, connector_id, location_id, tenant_id, credentials):
        self.connector_id = connector_id
        self.location_id = location_id
        self.tenant_id = tenant_id
        self.credentials = credentials
        self.log = structlog.get_logger().bind(
            connector=self.platform,
            location_id=str(location_id),
        )

    @abstractmethod
    async def fetch_reviews(self, since=None, limit=100) -> list[ReviewCreate]: ...

    @abstractmethod
    async def refresh_tokens(self) -> dict: ...

    @abstractmethod
    async def validate_connection(self) -> bool: ...

    async def sync(self, db: AsyncSession, since=None) -> dict:
        """
        Fetch reviews from the platform and publish each one to Kafka.
        Downstream workers (normalize, dedup, entity-resolve) take it from there.
        """
        self.log.info("Starting sync", mode="incremental" if since else "full")
        published = 0
        failed = 0

        try:
            is_valid = await self.validate_connection()
            if not is_valid:
                self.credentials = await self.refresh_tokens()

            reviews: list[ReviewCreate] = await self.fetch_reviews(since=since)
            self.log.info("Fetched reviews from platform", count=len(reviews))

            for review in reviews:
                try:
                    await publish_review(
                        tenant_id=str(self.tenant_id),
                        brand_id=str(review.brand_id),
                        location_id=str(self.location_id) if self.location_id else None,
                        source_platform=self.platform,
                        source_review_id=str(review.external_id),
                        rating=float(review.rating),
                        text=review.content,
                        reviewer_name=getattr(review, "reviewer_name", None),
                        review_date=review.reviewed_at.isoformat() if review.reviewed_at else datetime.utcnow().isoformat(),
                        language=getattr(review, "language", None),
                        metadata={"connector_id": str(self.connector_id)},
                    )
                    published += 1
                except Exception as e:
                    # One review failing shouldn't stop the rest
                    self.log.error("Failed to publish review to Kafka", error=str(e), review_id=str(review.external_id))
                    failed += 1

            self.log.info("Sync complete", published=published, failed=failed)
            return {
                "status": "success",
                "platform": self.platform,
                "location_id": str(self.location_id),
                "reviews_fetched": len(reviews),
                "reviews_published": published,
                "reviews_failed": failed,
                "synced_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.log.error("Sync failed", error=str(e))
            return {
                "status": "error",
                "platform": self.platform,
                "location_id": str(self.location_id),
                "reviews_fetched": 0,
                "reviews_published": 0,
                "reviews_failed": 0,
                "error": str(e),
                "synced_at": datetime.utcnow().isoformat(),
            }
