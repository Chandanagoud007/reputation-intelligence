"""
Analytics Writer
Consumes from: reputation.ai.merged
Writes to:     ClickHouse rip_analytics.review_events
               ClickHouse rip_analytics.alert_events (consumes alert.created too)

What it does:
- Appends every classified review as an event row in ClickHouse
- Appends every fired alert as an event row in ClickHouse
- Used by the dashboard for trend charts, topic breakdowns, sentiment over time
- Append-only — never updates, never deletes
- Batches writes for efficiency (every 50 events or 5 seconds)

Run with: python -m app.services.workers.analytics_writer
"""
import asyncio
import json
import time
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_REVIEWS = "reputation.ai.merged"
TOPIC_ALERTS  = "reputation.alert.created"
GROUP_ID      = "analytics-writer-group"

BATCH_SIZE     = 50
FLUSH_INTERVAL = 5.0   # seconds


# ── ClickHouse client ─────────────────────────────────────────────────────────
def get_ch_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host="localhost",
        port=8123,
        username="rip_user",
        password="rip_pass",
        database="rip_analytics",
    )


# ── Ensure tables exist ───────────────────────────────────────────────────────
def ensure_tables(client):
    client.command("""
        CREATE TABLE IF NOT EXISTS rip_analytics.review_events (
            event_id        String,
            tenant_id       String,
            brand_id        String,
            brand_name      String,
            region_id       String,
            location_id     String,
            location_name   String,
            source_platform LowCardinality(String),
            sentiment       LowCardinality(String),
            sentiment_score Float32,
            rating          Float32,
            topics          Array(String),
            risk_level      LowCardinality(String),
            risk_flags      Array(String),
            language        LowCardinality(String),
            review_date     DateTime,
            ingested_at     DateTime DEFAULT now()
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(ingested_at)
        ORDER BY (tenant_id, brand_id, location_id, ingested_at)
    """)

    client.command("""
        CREATE TABLE IF NOT EXISTS rip_analytics.alert_events (
            alert_id        String,
            rule_name       String,
            tenant_id       String,
            brand_id        String,
            location_id     String,
            location_name   String,
            severity        LowCardinality(String),
            risk_level      LowCardinality(String),
            risk_flags      Array(String),
            score           Float32,
            fired_at        DateTime DEFAULT now()
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(fired_at)
        ORDER BY (tenant_id, brand_id, location_id, fired_at)
    """)
    log.info("ClickHouse tables ready")


# ── Row builders ──────────────────────────────────────────────────────────────
def parse_dt(dt_str: str | None) -> datetime:
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def build_review_row(message: dict) -> list:
    normalized = message.get("normalized_content", {})
    return [
        message.get("message_id", ""),
        message.get("tenant_id", ""),
        message.get("brand_id", ""),
        message.get("brand_name", ""),
        message.get("region_id", ""),
        message.get("location_id", ""),
        message.get("location_name", ""),
        message.get("source_platform", ""),
        message.get("sentiment", "neutral"),
        float(message.get("sentiment_score", 0.0)),
        float(normalized.get("rating", 0.0)),
        message.get("topics", []),
        message.get("risk_level", "NONE"),
        message.get("risk_flags", []),
        normalized.get("language", "en"),
        parse_dt(normalized.get("review_date")),
        parse_dt(message.get("ingested_at")),
    ]


def build_alert_row(alert: dict) -> list:
    trigger = alert.get("trigger_values", {})
    return [
        alert.get("alert_id", ""),
        alert.get("rule_name", ""),
        alert.get("tenant_id", ""),
        alert.get("brand_id", ""),
        alert.get("location_id", ""),
        alert.get("location_name", ""),
        alert.get("severity", "low"),
        trigger.get("risk_level", "NONE"),
        alert.get("risk_flags", []),
        float(trigger.get("score", 0.0)),
        parse_dt(alert.get("fired_at")),
    ]


REVIEW_COLUMNS = [
    "event_id", "tenant_id", "brand_id", "brand_name", "region_id",
    "location_id", "location_name", "source_platform", "sentiment",
    "sentiment_score", "rating", "topics", "risk_level", "risk_flags",
    "language", "review_date", "ingested_at",
]

ALERT_COLUMNS = [
    "alert_id", "rule_name", "tenant_id", "brand_id", "location_id",
    "location_name", "severity", "risk_level", "risk_flags", "score", "fired_at",
]


# ── Batch flush ───────────────────────────────────────────────────────────────
def flush_reviews(client, batch: list):
    if not batch:
        return
    try:
        client.insert("review_events", batch, column_names=REVIEW_COLUMNS)
        log.info("Flushed review events to ClickHouse", count=len(batch))
    except Exception as e:
        log.error("ClickHouse review insert failed", error=str(e))


def flush_alerts(client, batch: list):
    if not batch:
        return
    try:
        client.insert("alert_events", batch, column_names=ALERT_COLUMNS)
        log.info("Flushed alert events to ClickHouse", count=len(batch))
    except Exception as e:
        log.error("ClickHouse alert insert failed", error=str(e))


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting analytics writer")

    client = get_ch_client()
    ensure_tables(client)

    consumer = AIOKafkaConsumer(
        TOPIC_REVIEWS,
        TOPIC_ALERTS,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=BATCH_SIZE,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    await consumer.start()
    log.info("Analytics writer ready, consuming from both topics")

    review_batch = []
    alert_batch  = []
    last_flush   = time.monotonic()

    async def flush_all():
        flush_reviews(client, review_batch)
        flush_alerts(client, alert_batch)
        review_batch.clear()
        alert_batch.clear()

    try:
        async for msg in consumer:
            message = msg.value
            topic   = msg.topic

            if topic == TOPIC_REVIEWS:
                # Skip if not a fully merged message
                if not message.get("merged_at"):
                    await consumer.commit()
                    continue
                review_batch.append(build_review_row(message))
                log.info(
                    "Review event queued",
                    message_id=message.get("message_id"),
                    sentiment=message.get("sentiment"),
                    platform=message.get("source_platform"),
                )

            elif topic == TOPIC_ALERTS:
                alert_batch.append(build_alert_row(message))
                log.info(
                    "Alert event queued",
                    alert_id=message.get("alert_id"),
                    severity=message.get("severity"),
                )

            await consumer.commit()

            elapsed = time.monotonic() - last_flush
            if (len(review_batch) + len(alert_batch)) >= BATCH_SIZE or elapsed >= FLUSH_INTERVAL:
                await flush_all()
                last_flush = time.monotonic()

    finally:
        await flush_all()
        await consumer.stop()
        log.info("Analytics writer stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
