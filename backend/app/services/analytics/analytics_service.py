"""
Analytics Aggregation Service
Computes rating stats, sentiment breakdowns, and trends from MongoDB reviews.
"""
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from app.core.database import get_collection

log = structlog.get_logger()


class AnalyticsService:

    def _collection(self):
        return get_collection("reviews")

    async def get_summary(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        platform: str | None = None,
        days: int = 30,
    ) -> dict:
        """
        Overall summary for a tenant/location:
        - total reviews
        - average rating
        - sentiment breakdown
        - positive/negative/neutral counts
        """
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=days)

        match = {
            "tenant_id": str(tenant_id),
            "published_at": {"$gte": since},
        }
        if location_id:
            match["location_id"] = str(location_id)
        if platform:
            match["platform"] = platform

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_reviews": {"$sum": 1},
                "avg_rating": {"$avg": "$rating"},
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
                "neutral":  {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "neutral"]}, 1, 0]}},
                "mixed":    {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "mixed"]}, 1, 0]}},
                "avg_sentiment_score": {"$avg": "$sentiment.score"},
                "five_star":  {"$sum": {"$cond": [{"$eq": ["$rating", 5.0]}, 1, 0]}},
                "four_star":  {"$sum": {"$cond": [{"$eq": ["$rating", 4.0]}, 1, 0]}},
                "three_star": {"$sum": {"$cond": [{"$eq": ["$rating", 3.0]}, 1, 0]}},
                "two_star":   {"$sum": {"$cond": [{"$eq": ["$rating", 2.0]}, 1, 0]}},
                "one_star":   {"$sum": {"$cond": [{"$eq": ["$rating", 1.0]}, 1, 0]}},
            }},
        ]

        results = await collection.aggregate(pipeline).to_list(length=1)
        if not results:
            return self._empty_summary(days)

        r = results[0]
        total = r["total_reviews"] or 1  # avoid division by zero

        return {
            "period_days": days,
            "total_reviews": r["total_reviews"],
            "avg_rating": round(r["avg_rating"] or 0, 2),
            "avg_sentiment_score": round(r["avg_sentiment_score"] or 0, 4),
            "sentiment": {
                "positive": r["positive"],
                "negative": r["negative"],
                "neutral": r["neutral"],
                "mixed": r["mixed"],
                "positive_pct": round(r["positive"] / total * 100, 1),
                "negative_pct": round(r["negative"] / total * 100, 1),
            },
            "rating_distribution": {
                "5": r["five_star"],
                "4": r["four_star"],
                "3": r["three_star"],
                "2": r["two_star"],
                "1": r["one_star"],
            },
        }

    async def get_trends(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        platform: str | None = None,
        days: int = 30,
        group_by: str = "day",  # day | week | month
    ) -> list[dict]:
        """
        Rating and sentiment trends over time.
        Returns a list of data points for charting.
        """
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=days)

        match = {
            "tenant_id": str(tenant_id),
            "published_at": {"$gte": since},
        }
        if location_id:
            match["location_id"] = str(location_id)
        if platform:
            match["platform"] = platform

        # Date grouping format
        date_trunc = {
            "day":   {"$dateToString": {"format": "%Y-%m-%d", "date": "$published_at"}},
            "week":  {"$dateToString": {"format": "%Y-W%V", "date": "$published_at"}},
            "month": {"$dateToString": {"format": "%Y-%m", "date": "$published_at"}},
        }.get(group_by, {"$dateToString": {"format": "%Y-%m-%d", "date": "$published_at"}})

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": date_trunc,
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating"},
                "avg_sentiment": {"$avg": "$sentiment.score"},
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]

        results = await collection.aggregate(pipeline).to_list(length=365)
        return [
            {
                "date": r["_id"],
                "count": r["count"],
                "avg_rating": round(r["avg_rating"] or 0, 2),
                "avg_sentiment": round(r["avg_sentiment"] or 0, 4),
                "positive": r["positive"],
                "negative": r["negative"],
            }
            for r in results
        ]

    async def get_platform_breakdown(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        days: int = 30,
    ) -> list[dict]:
        """Compare performance across platforms."""
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=days)

        match = {"tenant_id": str(tenant_id), "published_at": {"$gte": since}}
        if location_id:
            match["location_id"] = str(location_id)

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": "$platform",
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating"},
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
            }},
            {"$sort": {"count": -1}},
        ]

        results = await collection.aggregate(pipeline).to_list(length=20)
        return [
            {
                "platform": r["_id"],
                "total_reviews": r["count"],
                "avg_rating": round(r["avg_rating"] or 0, 2),
                "positive": r["positive"],
                "negative": r["negative"],
            }
            for r in results
        ]

    def _empty_summary(self, days: int) -> dict:
        return {
            "period_days": days,
            "total_reviews": 0,
            "avg_rating": 0,
            "avg_sentiment_score": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "positive_pct": 0, "negative_pct": 0},
            "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
        }


analytics_service = AnalyticsService()
