"""
Prescriptive Analytics Service
Answers: "What should we focus on improving this month?"
Uses review content and sentiment trends to generate actionable suggestions.
"""
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from app.core.database import get_collection
from app.core.config import settings

log = structlog.get_logger()

TOPIC_KEYWORDS = {
    "wait_time":    ["wait", "slow", "long", "queue", "delayed", "hours"],
    "staff":        ["staff", "rude", "helpful", "friendly", "team", "employee", "service"],
    "cleanliness":  ["clean", "dirty", "hygiene", "mess", "filthy", "spotless"],
    "price":        ["expensive", "cheap", "price", "cost", "value", "worth", "overpriced"],
    "quality":      ["quality", "poor", "excellent", "bad", "good", "great", "terrible"],
    "communication":["response", "reply", "contact", "follow up", "ignored", "email", "call"],
    "location":     ["parking", "location", "far", "close", "accessible", "navigate"],
}


class PrescriptiveAnalyticsService:

    def _collection(self):
        return get_collection("reviews")

    async def get_improvement_areas(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        days: int = 30,
    ) -> dict:
        """
        Analyze negative reviews to find top areas to improve.
        Returns ranked list of improvement areas with evidence.
        """
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=days)

        match = {
            "tenant_id": str(tenant_id),
            "published_at": {"$gte": since},
            "sentiment.label": {"$in": ["negative", "neutral"]},
            "rating": {"$lte": 3.0},
        }
        if location_id:
            match["location_id"] = str(location_id)

        cursor = collection.find(match, {"content": 1, "rating": 1, "platform": 1})
        reviews = await cursor.to_list(length=200)

        if not reviews:
            return {
                "period_days": days,
                "total_negative_reviews": 0,
                "improvement_areas": [],
                "top_priority": None,
                "generated_at": datetime.utcnow().isoformat(),
            }

        # Count keyword hits per topic
        topic_hits: dict[str, list[str]] = {topic: [] for topic in TOPIC_KEYWORDS}

        for review in reviews:
            content = review.get("content", "").lower()
            for topic, keywords in TOPIC_KEYWORDS.items():
                if any(kw in content for kw in keywords):
                    topic_hits[topic].append(content[:100])

        # Build ranked improvement areas
        areas = []
        for topic, mentions in topic_hits.items():
            if mentions:
                areas.append({
                    "area": topic,
                    "mention_count": len(mentions),
                    "sample_complaints": mentions[:3],
                    "priority": "high" if len(mentions) >= 5 else "medium" if len(mentions) >= 2 else "low",
                })

        areas.sort(key=lambda x: x["mention_count"], reverse=True)
        top = areas[0]["area"].replace("_", " ").title() if areas else None

        return {
            "period_days": days,
            "total_negative_reviews": len(reviews),
            "improvement_areas": areas[:5],
            "top_priority": top,
            "recommendation": f"Focus on improving '{top}' — mentioned in {areas[0]['mention_count']} negative reviews this month." if top else "No major issues detected.",
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def get_winning_areas(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None,
        days: int = 30,
    ) -> dict:
        """
        Analyze positive reviews to find what's working well.
        Helps reinforce strengths.
        """
        collection = self._collection()
        since = datetime.utcnow() - timedelta(days=days)

        match = {
            "tenant_id": str(tenant_id),
            "published_at": {"$gte": since},
            "sentiment.label": "positive",
            "rating": {"$gte": 4.0},
        }
        if location_id:
            match["location_id"] = str(location_id)

        cursor = collection.find(match, {"content": 1})
        reviews = await cursor.to_list(length=200)

        topic_hits: dict[str, int] = {topic: 0 for topic in TOPIC_KEYWORDS}
        for review in reviews:
            content = review.get("content", "").lower()
            for topic, keywords in TOPIC_KEYWORDS.items():
                if any(kw in content for kw in keywords):
                    topic_hits[topic] += 1

        strengths = [
            {"area": topic.replace("_", " ").title(), "mention_count": count}
            for topic, count in sorted(topic_hits.items(), key=lambda x: x[1], reverse=True)
            if count > 0
        ]

        return {
            "period_days": days,
            "total_positive_reviews": len(reviews),
            "strengths": strengths[:5],
            "generated_at": datetime.utcnow().isoformat(),
        }


prescriptive_service = PrescriptiveAnalyticsService()
