"""
Entity Resolution Worker
Consumes from: reputation.deduplicated
Produces to:   reputation.entity.resolved
               reputation.dlq (on failure)

What it does:
- Takes a deduplicated review with brand_id + optional location_id
- Verifies brand_id exists and belongs to the correct tenant
- If location_id is null, fuzzy matches location using city/name from metadata
- Resolves full hierarchy: Brand → Region → Location
- Enriches message with region_id + verified location_id
- Unresolvable reviews go to DLQ with reason tag

Run with: python -m app.services.workers.entity_resolve_worker
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.deduplicated"
TOPIC_OUT = "reputation.entity.resolved"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "entity-resolve-worker-group"

FUZZY_THRESHOLD = 0.4  # similarity threshold for location name matching


# ── DB setup (worker has its own engine, independent of FastAPI) ──────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Entity resolution logic ───────────────────────────────────────────────────
async def resolve_brand(db: AsyncSession, brand_id: str, tenant_id: str) -> dict | None:
    """Verify brand exists and belongs to this tenant."""
    result = await db.execute(
        text("""
            SELECT id, name, tenant_id
            FROM tenant_mgmt.brands
            WHERE id = :brand_id
              AND tenant_id = :tenant_id
              AND is_active = true
        """),
        {"brand_id": brand_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {"id": str(row.id), "name": row.name, "tenant_id": str(row.tenant_id)}


async def resolve_location_by_id(db: AsyncSession, location_id: str, brand_id: str) -> dict | None:
    """Resolve location by exact ID, verify it belongs to the brand."""
    result = await db.execute(
        text("""
            SELECT l.id, l.name, l.city, l.state, l.country, l.region_id,
                   r.brand_id, r.id as region_id_val, r.name as region_name
            FROM tenant_mgmt.locations l
            JOIN tenant_mgmt.regions r ON l.region_id = r.id
            WHERE l.id = :location_id
              AND r.brand_id = :brand_id
              AND l.is_active = true
        """),
        {"location_id": location_id, "brand_id": brand_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "location_id": str(row.id),
        "location_name": row.name,
        "city": row.city,
        "state": row.state,
        "country": row.country,
        "region_id": str(row.region_id_val),
        "region_name": row.region_name,
    }


async def fuzzy_resolve_location(
    db: AsyncSession, brand_id: str, hint: str
) -> dict | None:
    """
    Fuzzy match a location by name/city hint using PostgreSQL similarity.
    Uses pg_trgm extension for trigram similarity matching.
    Falls back to ILIKE if pg_trgm is not available.
    """
    if not hint:
        return None

    try:
        # Try pg_trgm similarity first (best results)
        result = await db.execute(
            text("""
                SELECT l.id, l.name, l.city, l.state, l.country,
                       r.id as region_id, r.name as region_name,
                       similarity(l.name, :hint) as name_sim,
                       similarity(COALESCE(l.city, ''), :hint) as city_sim
                FROM tenant_mgmt.locations l
                JOIN tenant_mgmt.regions r ON l.region_id = r.id
                WHERE r.brand_id = :brand_id
                  AND l.is_active = true
                  AND (
                      similarity(l.name, :hint) > :threshold
                      OR similarity(COALESCE(l.city, ''), :hint) > :threshold
                  )
                ORDER BY GREATEST(
                    similarity(l.name, :hint),
                    similarity(COALESCE(l.city, ''), :hint)
                ) DESC
                LIMIT 1
            """),
            {"brand_id": brand_id, "hint": hint, "threshold": FUZZY_THRESHOLD},
        )
        row = result.fetchone()
    except Exception:
        # pg_trgm not available — fall back to ILIKE
        result = await db.execute(
            text("""
                SELECT l.id, l.name, l.city, l.state, l.country,
                       r.id as region_id, r.name as region_name
                FROM tenant_mgmt.locations l
                JOIN tenant_mgmt.regions r ON l.region_id = r.id
                WHERE r.brand_id = :brand_id
                  AND l.is_active = true
                  AND (l.name ILIKE :hint OR l.city ILIKE :hint)
                LIMIT 1
            """),
            {"brand_id": brand_id, "hint": f"%{hint}%"},
        )
        row = result.fetchone()

    if not row:
        return None

    return {
        "location_id": str(row.id),
        "location_name": row.name,
        "city": row.city,
        "state": row.state,
        "country": row.country,
        "region_id": str(row.region_id),
        "region_name": row.region_name,
    }


async def resolve_entities(message: dict) -> dict | None:
    """
    Main resolution logic.
    Returns resolved entity dict or None if unresolvable.
    """
    tenant_id   = message.get("tenant_id")
    brand_id    = message.get("brand_id")
    location_id = message.get("location_id")
    metadata    = message.get("metadata", {})

    async with AsyncSessionLocal() as db:
        # Step 1: verify brand belongs to tenant
        brand = await resolve_brand(db, brand_id, tenant_id)
        if not brand:
            log.warning(
                "Brand not found or wrong tenant",
                brand_id=brand_id,
                tenant_id=tenant_id,
            )
            return None

        # Step 2: resolve location
        location = None

        if location_id:
            # Try exact match first
            location = await resolve_location_by_id(db, location_id, brand_id)

        if not location:
            # Try fuzzy match using location hint from metadata or connector
            hint = (
                metadata.get("location_name")
                or metadata.get("location_hint")
                or metadata.get("city")
                or ""
            )
            if hint:
                location = await fuzzy_resolve_location(db, brand_id, hint)

        if not location:
            log.warning(
                "Location could not be resolved",
                brand_id=brand_id,
                location_id=location_id,
                hint=metadata.get("location_name"),
            )
            return None

        return {
            "brand_id": brand_id,
            "brand_name": brand["name"],
            "region_id": location["region_id"],
            "region_name": location["region_name"],
            "location_id": location["location_id"],
            "location_name": location["location_name"],
            "city": location["city"],
            "state": location["state"],
            "country": location["country"],
        }


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting entity resolve worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

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
    log.info("Entity resolve worker ready, consuming messages")

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            log.info(
                "Received deduplicated review",
                message_id=message_id,
                tenant_id=tenant_id,
                platform=message.get("source_platform"),
                offset=msg.offset,
            )

            try:
                resolved = await resolve_entities(message)

                if not resolved:
                    # Can't resolve — send to DLQ
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **message,
                            "dlq_reason": "entity_unresolved",
                            "dlq_stage": "entity_resolve",
                            "dlq_at": datetime.now(timezone.utc).isoformat(),
                        },
                        key=tenant_id,
                    )
                    await consumer.commit()
                    log.warning(
                        "Review sent to DLQ — entity unresolved",
                        message_id=message_id,
                    )
                    continue

                # Build resolved message
                resolved_message = {
                    **message,
                    # Overwrite with verified/resolved values
                    "brand_id": resolved["brand_id"],
                    "brand_name": resolved["brand_name"],
                    "region_id": resolved["region_id"],
                    "region_name": resolved["region_name"],
                    "location_id": resolved["location_id"],
                    "location_name": resolved["location_name"],
                    "city": resolved["city"],
                    "state": resolved["state"],
                    "country": resolved["country"],
                    "entity_resolved_at": datetime.now(timezone.utc).isoformat(),
                }

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=resolved_message,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("source_platform", message.get("source_platform", "").encode()),
                        ("schema_version", b"1.0"),
                    ],
                )

                await consumer.commit()

                log.info(
                    "Entity resolved and published",
                    message_id=message_id,
                    brand=resolved["brand_name"],
                    location=resolved["location_name"],
                    region=resolved["region_name"],
                    topic=TOPIC_OUT,
                )

            except Exception as e:
                log.error(
                    "Entity resolution error, sending to DLQ",
                    message_id=message_id,
                    error=str(e),
                )
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **message,
                            "dlq_reason": str(e),
                            "dlq_stage": "entity_resolve",
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
        await engine.dispose()
        log.info("Entity resolve worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
