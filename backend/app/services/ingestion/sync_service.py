"""Connector scheduler and ingestion orchestration."""
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.token_vault import retrieve_oauth_tokens
from app.models.brand import Brand
from app.models.connector import Connector
from app.models.location import Location
from app.models.region import Region
from app.services.kafka_producer import publish_reviews_batch
from app.services.ingestion.review_store import review_store
from app.services.nlp.sentiment import sentiment_service

log = structlog.get_logger()


class IngestionSyncService:
    async def list_due_connectors(self, db, tenant_id=None):
        stmt = (
            select(Connector, Brand.tenant_id)
            .join(Location, Connector.location_id == Location.id)
            .join(Region, Location.region_id == Region.id)
            .join(Brand, Region.brand_id == Brand.id)
            .where(Connector.is_active == True)
            .where(Connector.sync_status.in_(["pending", "active", "error"]))
        )
        if tenant_id:
            stmt = stmt.where(Brand.tenant_id == tenant_id)

        result = await db.execute(stmt)
        rows = result.all()
        now = datetime.utcnow()

        due = []
        for connector, row_tenant_id in rows:
            if connector.sync_status == "pending" or connector.last_synced is None:
                due.append((connector, row_tenant_id))
                continue
            next_sync_at = connector.last_synced + timedelta(minutes=connector.sync_frequency_minutes)
            if next_sync_at <= now:
                due.append((connector, row_tenant_id))
        return due

    async def enqueue_due_connectors(self, db, tenant_id=None):
        due = await self.list_due_connectors(db, tenant_id=tenant_id)
        for connector, connector_tenant_id in due:
            await self.enqueue_connector(connector, connector_tenant_id)
            connector.sync_status = "queued"
            connector.sync_error = None
        await db.commit()
        return len(due)

    async def enqueue_connector(self, connector, tenant_id):
    # Phase 2: connectors publish directly to Kafka via ConnectorBase.sync()
    # This method is kept for backward compatibility but is now a no-op.
    # Actual Kafka publishing happens in ConnectorBase.sync() → kafka_producer.publish_review()
        pass

    async def sync_connector(self, db, payload):
        connector_id = uuid.UUID(payload["connector_id"])
        result = await db.execute(select(Connector).where(Connector.id == connector_id))
        connector = result.scalar_one_or_none()
        if not connector:
            log.warning("Connector not found", connector_id=str(connector_id))
            return 0

        try:
            connector.sync_status = "syncing"
            connector.sync_error = None
            await db.commit()

            since = datetime.fromisoformat(payload["last_synced"]) if payload.get("last_synced") else None
            reviews = await self._fetch_reviews(connector, payload, since)

            enriched = []
            for review in reviews:
                try:
                    sentiment = await sentiment_service.analyze(
                        review["content"], review.get("language", "en")
                    )
                    review["sentiment"] = {
                        "label": sentiment.label.value,
                        "score": sentiment.score,
                        "positive_score": sentiment.positive_score,
                        "negative_score": sentiment.negative_score,
                        "neutral_score": sentiment.neutral_score,
                        "emotions": sentiment.emotions,
                        "topics": sentiment.topics,
                        "provider": sentiment.provider,
                    }
                    review["is_analyzed"] = True
                except Exception as e:
                    log.warning("Sentiment failed", error=str(e))
                    review["is_analyzed"] = False
                enriched.append(review)

            changed = await review_store.upsert_many(enriched)
            connector.last_synced = datetime.utcnow()
            connector.sync_status = "active"
            connector.sync_error = None
            await db.commit()
            log.info("Sync complete", connector_id=str(connector_id), changed=changed)
            return changed

        except Exception as exc:
            connector.sync_status = "error"
            connector.sync_error = str(exc)[:500]
            await db.commit()
            log.error("Sync failed", connector_id=str(connector_id), error=str(exc))
            raise

    async def _fetch_reviews(self, connector, payload, since):
        try:
            from app.services.connectors.registry import get_connector
            credentials = retrieve_oauth_tokens(connector.encrypted_credentials)
            platform_connector = get_connector(
                platform=payload["platform"],
                connector_id=connector.id,
                location_id=uuid.UUID(payload["location_id"]),
                tenant_id=uuid.UUID(payload["tenant_id"]),
                credentials=credentials,
            )
            review_creates = await platform_connector.fetch_reviews(since=since)
            return [r.dict() for r in review_creates]

        except (ValueError, KeyError, Exception):
            log.info("Platform not in registry, using mock", platform=payload["platform"])
            from app.services.ingestion.platforms import fetcher
            return await fetcher.fetch_reviews(
                tenant_id=uuid.UUID(payload["tenant_id"]),
                location_id=uuid.UUID(payload["location_id"]),
                platform=payload["platform"],
                external_id=payload["external_id"],
                since=since,
            )


ingestion_sync_service = IngestionSyncService()

