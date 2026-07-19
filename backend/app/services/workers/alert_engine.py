"""
Alert Rule Engine
Consumes from: reputation.score.updated
Produces to:   reputation.alert.created
               reputation.dlq (on failure)

What it does:
- Loads active alert rules for the tenant from PostgreSQL
- Evaluates each rule's conditions against the incoming score event
- Checks Redis cooldown TTL — skips if alert fired recently for same rule+location
- Publishes alert event if conditions are met and cooldown has passed
- Caches rules per tenant for 60 seconds to avoid repeated DB queries

Supported condition types:
    score_lte       — overall score <= threshold
    rating_lte      — rating avg <= threshold
    sentiment_lte   — sentiment avg <= threshold
    risk_level_in   — risk_level is in list (e.g. ["HIGH", "CRITICAL"])
    negative_pct_gte — negative review % >= threshold

Run with: python -m app.services.workers.alert_engine
"""
import asyncio
import json
import time
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from redis.asyncio import from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.score.updated"
TOPIC_OUT = "reputation.alert.created"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "alert-engine-group"

RULE_CACHE_TTL = 60   # seconds — re-fetch rules from DB every 60s


# ── DB setup ──────────────────────────────────────────────────────────────────
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Rule cache ────────────────────────────────────────────────────────────────
_rule_cache: dict[str, dict] = {}   # tenant_id → {rules: [], fetched_at: float}


async def get_rules_for_tenant(tenant_id: str) -> list[dict]:
    """Load active alert rules for tenant. Cached for 60 seconds."""
    cached = _rule_cache.get(tenant_id)
    if cached and (time.monotonic() - cached["fetched_at"]) < RULE_CACHE_TTL:
        return cached["rules"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, name, conditions, channels, cooldown_minutes
                FROM alerts.alert_rules
                WHERE tenant_id = :tenant_id AND is_active = true
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()

    rules = [
        {
            "id": str(row.id),
            "name": row.name,
            "conditions": row.conditions,
            "channels": row.channels,
            "cooldown_minutes": row.cooldown_minutes,
        }
        for row in rows
    ]

    _rule_cache[tenant_id] = {"rules": rules, "fetched_at": time.monotonic()}
    log.info("Loaded alert rules", tenant_id=tenant_id, count=len(rules))
    return rules


# ── Condition evaluator ───────────────────────────────────────────────────────
def evaluate_conditions(conditions: dict, event: dict) -> bool:
    """
    Evaluate all conditions in a rule against the score event.
    All conditions must be true (AND logic).
    """
    score         = event.get("score", 0.0)
    rating_avg    = event.get("rating_avg", 0.0)
    sentiment_avg = event.get("sentiment_avg", 0.0)
    risk_level    = event.get("risk_level", "NONE")
    review_count  = event.get("review_count", 0)
    negative_count = event.get("negative_count", 0)
    negative_pct  = (negative_count / review_count * 100) if review_count > 0 else 0.0

    for condition, threshold in conditions.items():
        if condition == "score_lte":
            if not (score <= float(threshold)):
                return False
        elif condition == "rating_lte":
            if not (rating_avg <= float(threshold)):
                return False
        elif condition == "sentiment_lte":
            if not (sentiment_avg <= float(threshold)):
                return False
        elif condition == "risk_level_in":
            if risk_level not in threshold:
                return False
        elif condition == "negative_pct_gte":
            if not (negative_pct >= float(threshold)):
                return False
        else:
            log.warning("Unknown condition type", condition=condition)

    return True


def determine_severity(conditions: dict, event: dict) -> str:
    """Derive alert severity from conditions and event risk level."""
    risk_level = event.get("risk_level", "NONE")
    if risk_level == "CRITICAL":
        return "critical"
    if risk_level == "HIGH":
        return "high"
    score = event.get("score", 5.0)
    if score <= 2.0:
        return "high"
    if score <= 3.0:
        return "medium"
    return "low"


# ── Cooldown check ────────────────────────────────────────────────────────────
def cooldown_key(tenant_id: str, rule_id: str, location_id: str) -> str:
    return f"alert_cooldown:{tenant_id}:{rule_id}:{location_id}"


async def is_in_cooldown(redis, tenant_id: str, rule_id: str, location_id: str) -> bool:
    key = cooldown_key(tenant_id, rule_id, location_id)
    return bool(await redis.exists(key))


async def set_cooldown(redis, tenant_id: str, rule_id: str, location_id: str, minutes: int):
    key = cooldown_key(tenant_id, rule_id, location_id)
    await redis.set(key, "1", ex=minutes * 60)


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting alert engine", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

    redis = await from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await redis.ping()
    log.info("Redis connected")

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=50,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        enable_idempotence=True,
    )

    await consumer.start()
    await producer.start()
    log.info("Alert engine ready")

    try:
        async for msg in consumer:
            event      = msg.value
            message_id = event.get("message_id", "unknown")
            tenant_id  = event.get("tenant_id", "unknown")
            location_id = event.get("location_id", "unknown")

            log.info(
                "Evaluating alert rules",
                message_id=message_id,
                tenant_id=tenant_id,
                score=event.get("score"),
                risk_level=event.get("risk_level"),
            )

            try:
                rules = await get_rules_for_tenant(tenant_id)

                if not rules:
                    log.info("No active rules for tenant", tenant_id=tenant_id)
                    await consumer.commit()
                    continue

                alerts_fired = 0

                for rule in rules:
                    rule_id    = rule["id"]
                    conditions = rule["conditions"]

                    # Check conditions
                    if not evaluate_conditions(conditions, event):
                        continue

                    # Check cooldown
                    if await is_in_cooldown(redis, tenant_id, rule_id, location_id):
                        log.info(
                            "Alert suppressed by cooldown",
                            rule=rule["name"],
                            location_id=location_id,
                        )
                        continue

                    # Fire alert
                    severity = determine_severity(conditions, event)
                    alert = {
                        "schema_version": "1.0",
                        "alert_id":       f"{rule_id}:{message_id}",
                        "rule_id":        rule_id,
                        "rule_name":      rule["name"],
                        "tenant_id":      tenant_id,
                        "brand_id":       event.get("brand_id"),
                        "brand_name":     event.get("brand_name"),
                        "region_id":      event.get("region_id"),
                        "location_id":    location_id,
                        "location_name":  event.get("location_name"),
                        "severity":       severity,
                        "conditions":     conditions,
                        "trigger_values": {
                            "score":         event.get("score"),
                            "rating_avg":    event.get("rating_avg"),
                            "sentiment_avg": event.get("sentiment_avg"),
                            "risk_level":    event.get("risk_level"),
                            "review_count":  event.get("review_count"),
                        },
                        "channels":  rule["channels"],
                        "risk_flags": event.get("risk_flags", []),
                        "topics":    event.get("topics", []),
                        "fired_at":  datetime.now(timezone.utc).isoformat(),
                    }

                    await producer.send_and_wait(
                        TOPIC_OUT,
                        value=alert,
                        key=tenant_id,
                        headers=[
                            ("tenant_id", tenant_id.encode()),
                            ("severity", severity.encode()),
                        ],
                    )

                    # Log full alert context to PostgreSQL for dashboard reads
                    async with AsyncSessionLocal() as log_db:
                        await log_db.execute(
                            text("""
                                INSERT INTO alerts.alert_log
                                    (id, alert_id, tenant_id, rule_name, severity,
                                     location_name, brand_name, risk_level,
                                     risk_flags, topics, trigger_values, fired_at)
                                VALUES
                                    (gen_random_uuid(), :alert_id, :tenant_id, :rule_name, :severity,
                                     :location_name, :brand_name, :risk_level,
                                     :risk_flags, :topics, :trigger_values, now())
                                ON CONFLICT (alert_id) DO NOTHING
                            """),
                            {
                                "alert_id":      alert["alert_id"],
                                "tenant_id":     tenant_id,
                                "rule_name":     alert["rule_name"],
                                "severity":      severity,
                                "location_name": alert.get("location_name"),
                                "brand_name":    alert.get("brand_name"),
                                "risk_level":    alert["trigger_values"].get("risk_level"),
                                "risk_flags":    json.dumps(alert.get("risk_flags", [])),
                                "topics":        json.dumps(alert.get("topics", [])),
                                "trigger_values": json.dumps(alert["trigger_values"]),
                            },
                        )
                        await log_db.commit()

                    # Set cooldown
                    await set_cooldown(
                        redis, tenant_id, rule_id, location_id,
                        rule["cooldown_minutes"]
                    )

                    alerts_fired += 1
                    log.warning(
                        "Alert fired",
                        rule=rule["name"],
                        severity=severity,
                        location=event.get("location_name"),
                        score=event.get("score"),
                        risk_level=event.get("risk_level"),
                    )

                await consumer.commit()
                log.info(
                    "Rule evaluation complete",
                    message_id=message_id,
                    alerts_fired=alerts_fired,
                )

            except Exception as e:
                log.error("Alert engine error", message_id=message_id, error=str(e))
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **event,
                            "dlq_reason": str(e),
                            "dlq_stage": "alert_engine",
                            "dlq_at": datetime.now(timezone.utc).isoformat(),
                        },
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))

    finally:
        await consumer.stop()
        await producer.stop()
        await redis.aclose()
        await engine.dispose()
        log.info("Alert engine stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
