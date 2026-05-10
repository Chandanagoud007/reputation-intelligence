"""Platform review fetchers.

Real provider integrations can replace these mock fetchers behind the same
interface. For local development, deterministic reviews let the scheduler,
queue, storage, and analytics work in parallel.
"""
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID


class MockPlatformFetcher:
    """Returns deterministic sample reviews for a connector."""

    async def fetch_reviews(
        self,
        *,
        tenant_id: UUID,
        location_id: UUID,
        platform: str,
        external_id: str,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        seed = f"{platform}:{external_id}"
        reviews = [
            {
                "tenant_id": tenant_id,
                "location_id": location_id,
                "platform": platform,
                "external_id": f"{seed}:review:1",
                "rating": 5.0,
                "title": "Great experience",
                "content": "The staff was helpful and the service was fast.",
                "language": "en",
                "author": {"name": "Aarav Mehta"},
                "review_url": None,
                "published_at": now - timedelta(days=1),
            },
            {
                "tenant_id": tenant_id,
                "location_id": location_id,
                "platform": platform,
                "external_id": f"{seed}:review:2",
                "rating": 2.0,
                "title": "Needs attention",
                "content": "The wait time was long and nobody followed up.",
                "language": "en",
                "author": {"name": "Priya Shah"},
                "review_url": None,
                "published_at": now - timedelta(days=2),
            },
        ]

        if since:
            return [review for review in reviews if review["published_at"].replace(tzinfo=None) > since.replace(tzinfo=None)]
        return reviews


fetcher = MockPlatformFetcher()

