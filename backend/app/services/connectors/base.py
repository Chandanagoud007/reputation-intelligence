"""
Connector Base Class
All platform connectors inherit from this.
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import ReviewCreate

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
        self.log.info("Starting sync", mode="incremental" if since else "full")
        try:
            is_valid = await self.validate_connection()
            if not is_valid:
                self.credentials = await self.refresh_tokens()
            reviews = await self.fetch_reviews(since=since)
            self.log.info("Fetched reviews", count=len(reviews))
            return {
                "status": "success",
                "platform": self.platform,
                "location_id": str(self.location_id),
                "reviews_fetched": len(reviews),
                "reviews": reviews,
                "synced_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            self.log.error("Sync failed", error=str(e))
            return {
                "status": "error",
                "platform": self.platform,
                "location_id": str(self.location_id),
                "reviews_fetched": 0,
                "reviews": [],
                "error": str(e),
                "synced_at": datetime.utcnow().isoformat(),
            }
