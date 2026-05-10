"""
Anomaly Detection Service
Detects sudden rating drops and sentiment spikes.
"""
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from app.core.database import get_collection

log = structlog.get_logger()


class AnomalyDetectionService:

    def _collection(self):
        return get_collection("reviews")

    async def detect_rating_drop(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        platform: str | None = None,
        window_days: int = 7,
        threshold: float = 0.8,
    ) -> list[dict]:
        """
        Detect locations/platforms where avg rating dropped significantly.
        Compares current window vs previous window.
        threshold: fraction drop that triggers anomaly (0.8 = 20% drop)
        """
        collection = self._collection()
        now = datetime.utcnow()
        current_start = now - timedelta(days=window_days)
        previous_start = now - timedelta(days=window_days * 2)

        base_match = {"tenant_id": str(tenant_id)}
        if location_id:
            base_match["location_id"] = str(location_id)
        if platform:
            base_match["platform"] = platform

        # Current window
        current_pipeline = [
            {"$match": {**base_match, "published_at": {"$gte": current_start}}},
            {"$group": {
                "_id": {"location_id": "$location_id", "platform": "$platform"},
                "avg_rating": {"$avg": "$rating"},
                "count": {"$sum": 1},
            }},
        ]

        # Previous window
        previous_pipeline = [
            {"$match": {**base_match, "published_at": {"$gte": previous_start, "$lt": current_start}}},
            {"$group": {
                "_id": {"location_id": "$location_id", "platform": "$platform"},
                "avg_rating": {"$avg": "$rating"},
                "count": {"$sum": 1},
            }},
        ]

        current_results = {
            f"{r['_id']['location_id']}:{r['_id']['platform']}": r
            for r in await collection.aggregate(current_pipeline).to_list(length=100)
        }
        previous_results = {
            f"{r['_id']['location_id']}:{r['_id']['platform']}": r
            for r in await collection.aggregate(previous_pipeline).to_list(length=100)
        }

        anomalies = []
        for key, current in current_results.items():
            previous = previous_results.get(key)
            if not previous or previous["avg_rating"] == 0:
                continue

            ratio = current["avg_rating"] / previous["avg_rating"]
            if ratio < threshold:
                drop_pct = round((1 - ratio) * 100, 1)
                anomalies.append({
                    "type": "rating_drop",
                    "location_id": current["_id"]["location_id"],
                    "platform": current["_id"]["platform"],
                    "current_avg_rating": round(current["avg_rating"], 2),
                    "previous_avg_rating": round(previous["avg_rating"], 2),
                    "drop_percentage": drop_pct,
                    "current_review_count": current["count"],
                    "severity": "high" if drop_pct >= 30 else "medium",
                    "detected_at": now.isoformat(),
                })

        anomalies.sort(key=lambda x: x["drop_percentage"], reverse=True)
        log.info("Anomaly detection complete", anomalies_found=len(anomalies))
        return anomalies

    async def detect_negative_spike(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        window_days: int = 3,
        spike_threshold: float = 0.5,
    ) -> list[dict]:
        """
        Detect when negative review ratio spikes above threshold.
        spike_threshold: fraction of negative reviews that triggers alert (0.5 = 50%)
        """
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=window_days)

        match = {
            "tenant_id": str(tenant_id),
            "published_at": {"$gte": since},
        }
        if location_id:
            match["location_id"] = str(location_id)

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"location_id": "$location_id", "platform": "$platform"},
                "total": {"$sum": 1},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
            }},
        ]

        results = await collection.aggregate(pipeline).to_list(length=100)
        spikes = []
        for r in results:
            if r["total"] < 3:
                continue  # not enough data
            negative_ratio = r["negative"] / r["total"]
            if negative_ratio >= spike_threshold:
                spikes.append({
                    "type": "negative_spike",
                    "location_id": r["_id"]["location_id"],
                    "platform": r["_id"]["platform"],
                    "negative_ratio": round(negative_ratio, 2),
                    "negative_count": r["negative"],
                    "total_count": r["total"],
                    "severity": "high" if negative_ratio >= 0.7 else "medium",
                    "detected_at": datetime.utcnow().isoformat(),
                })

        return spikes


anomaly_service = AnomalyDetectionService()
