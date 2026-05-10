"""
Alert Rules Service
Evaluates alert rules after each sync and triggers notifications.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_collection, get_redis
from app.models.alert_rule import AlertRule

log = structlog.get_logger()


class AlertService:

    async def list_rules(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[AlertRule]:
        result = await db.execute(
            select(AlertRule)
            .where(AlertRule.tenant_id == tenant_id, AlertRule.is_active == True)
            .order_by(AlertRule.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_rule(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
        description: str | None,
        conditions: dict,
        channels: dict,
        cooldown_minutes: int = 60,
    ) -> AlertRule:
        rule = AlertRule(
            tenant_id=tenant_id,
            name=name,
            description=description,
            conditions=conditions,
            channels=channels,
            cooldown_minutes=cooldown_minutes,
            is_active=True,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    async def delete_rule(self, db: AsyncSession, rule: AlertRule) -> None:
        await db.delete(rule)
        await db.commit()

    async def get_rule(
        self,
        db: AsyncSession,
        rule_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> AlertRule | None:
        result = await db.execute(
            select(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def evaluate_rules(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        platform: str,
    ) -> list[dict]:
        """
        Evaluate all active alert rules for a tenant after a sync.
        Returns list of triggered alerts.
        """
        rules = await self.list_rules(db, tenant_id)
        if not rules:
            return []

        # Get recent reviews for this location+platform
        collection = get_collection("reviews")
        since = datetime.utcnow() - timedelta(days=7)
        reviews = await collection.find({
            "tenant_id": str(tenant_id),
            "location_id": str(location_id),
            "platform": platform,
            "published_at": {"$gte": since},
        }).to_list(length=100)

        if not reviews:
            return []

        triggered = []
        for rule in rules:
            # Check cooldown
            if await self._is_in_cooldown(rule):
                log.info("Rule in cooldown, skipping", rule=rule.name)
                continue

            fired = await self._evaluate_rule(rule, reviews)
            if fired:
                alert = {
                    "rule_id": str(rule.id),
                    "rule_name": rule.name,
                    "tenant_id": str(tenant_id),
                    "location_id": str(location_id),
                    "platform": platform,
                    "triggered_at": datetime.utcnow().isoformat(),
                    "evidence": fired,
                    "channels": rule.channels,
                }
                # Store alert in MongoDB
                await self._store_alert(alert)
                # Set cooldown
                await self._set_cooldown(rule)
                # Send notifications
                await self._notify(alert, rule.channels)
                triggered.append(alert)

        return triggered

    async def _evaluate_rule(
        self,
        rule: AlertRule,
        reviews: list[dict],
    ) -> dict | None:
        """
        Check if rule conditions are met.
        Supported conditions:
          - rating_lte: float        (avg rating <= value)
          - rating_gte: float        (avg rating >= value)
          - negative_pct_gte: float  (% negative >= value)
          - review_count_gte: int    (review count >= value)
          - sentiment: str           (dominant sentiment label)
        """
        conditions = rule.conditions
        avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews)
        negative_count = sum(1 for r in reviews if r.get("sentiment", {}).get("label") == "negative")
        negative_pct = (negative_count / len(reviews)) * 100

        evidence = {
            "avg_rating": round(avg_rating, 2),
            "review_count": len(reviews),
            "negative_count": negative_count,
            "negative_pct": round(negative_pct, 1),
        }

        triggered = False

        if "rating_lte" in conditions:
            if avg_rating <= conditions["rating_lte"]:
                triggered = True
                evidence["triggered_by"] = f"avg_rating {avg_rating:.2f} <= {conditions['rating_lte']}"

        if "rating_gte" in conditions:
            if avg_rating >= conditions["rating_gte"]:
                triggered = True
                evidence["triggered_by"] = f"avg_rating {avg_rating:.2f} >= {conditions['rating_gte']}"

        if "negative_pct_gte" in conditions:
            if negative_pct >= conditions["negative_pct_gte"]:
                triggered = True
                evidence["triggered_by"] = f"negative_pct {negative_pct:.1f}% >= {conditions['negative_pct_gte']}%"

        if "review_count_gte" in conditions:
            if len(reviews) >= conditions["review_count_gte"]:
                triggered = True
                evidence["triggered_by"] = f"review_count {len(reviews)} >= {conditions['review_count_gte']}"

        return evidence if triggered else None

    async def _is_in_cooldown(self, rule: AlertRule) -> bool:
        redis = get_redis()
        key = f"alert_cooldown:{rule.id}"
        return await redis.exists(key) > 0

    async def _set_cooldown(self, rule: AlertRule) -> None:
        redis = get_redis()
        key = f"alert_cooldown:{rule.id}"
        await redis.setex(key, rule.cooldown_minutes * 60, "1")

    async def _store_alert(self, alert: dict) -> None:
        collection = get_collection("triggered_alerts")
        await collection.insert_one({**alert, "is_resolved": False})

    async def _notify(self, alert: dict, channels: dict) -> None:
        """Send notifications to configured channels."""
        if "email" in channels:
            await self._send_email(alert, channels["email"])
        if "slack" in channels:
            await self._send_slack(alert, channels["slack"])

    async def _send_email(self, alert: dict, recipients: list[str]) -> None:
        """Send email via SendGrid."""
        try:
            from app.core.config import settings
            import httpx
            if not settings.SENDGRID_API_KEY:
                log.info("SendGrid not configured, skipping email")
                return

            body = f"""
Alert: {alert['rule_name']}
Location: {alert['location_id']}
Platform: {alert['platform']}
Triggered at: {alert['triggered_at']}
Evidence: {alert['evidence']}
            """.strip()

            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                    json={
                        "personalizations": [{"to": [{"email": r} for r in recipients]}],
                        "from": {"email": settings.AWS_SES_SENDER_EMAIL},
                        "subject": f"[RIP Alert] {alert['rule_name']}",
                        "content": [{"type": "text/plain", "value": body}],
                    },
                )
            log.info("Email alert sent", recipients=recipients)
        except Exception as e:
            log.error("Email notification failed", error=str(e))

    async def _send_slack(self, alert: dict, webhook_url: str) -> None:
        """Send Slack webhook notification."""
        try:
            import httpx
            message = {
                "text": f"🚨 *{alert['rule_name']}*\nPlatform: {alert['platform']}\nEvidence: {alert['evidence']}"
            }
            async with httpx.AsyncClient() as client:
                await client.post(webhook_url, json=message)
            log.info("Slack alert sent")
        except Exception as e:
            log.error("Slack notification failed", error=str(e))

    async def list_triggered_alerts(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List triggered alerts from MongoDB."""
        collection = get_collection("triggered_alerts")
        query: dict[str, Any] = {"tenant_id": str(tenant_id)}
        if location_id:
            query["location_id"] = str(location_id)
        cursor = collection.find(query, {"_id": 0}).sort("triggered_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def resolve_alert(self, alert_id: str) -> bool:
        collection = get_collection("triggered_alerts")
        result = await collection.update_one(
            {"rule_id": alert_id},
            {"$set": {"is_resolved": True, "resolved_at": datetime.utcnow().isoformat()}},
        )
        return result.modified_count > 0


alert_service = AlertService()

