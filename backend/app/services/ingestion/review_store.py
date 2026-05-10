"""MongoDB persistence for normalized reviews."""
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.database import get_collection


def _mongo_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value
    if isinstance(value, list):
        return [_mongo_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _mongo_safe(item) for key, item in value.items()}
    return value


class ReviewStore:
    """Stores reviews using a stable platform/location/external id key."""

    collection_name = "reviews"

    async def upsert_many(self, reviews: list[dict[str, Any]]) -> int:
        collection = get_collection(self.collection_name)
        changed = 0

        for review in reviews:
            document = _mongo_safe(review)
            document["updated_at"] = datetime.utcnow()
            document.setdefault("ingested_at", datetime.utcnow())

            result = await collection.update_one(
                {
                    "tenant_id": document["tenant_id"],
                    "location_id": document["location_id"],
                    "platform": document["platform"],
                    "external_id": document["external_id"],
                },
                {"$set": document},
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                changed += 1

        return changed

    async def list_reviews(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        platform: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        collection = get_collection(self.collection_name)
        query: dict[str, Any] = {"tenant_id": str(tenant_id)}
        if location_id:
            query["location_id"] = str(location_id)
        if platform:
            query["platform"] = platform

        cursor = collection.find(query, {"_id": 0}).sort("published_at", -1).limit(limit)
        return await cursor.to_list(length=limit)


review_store = ReviewStore()
