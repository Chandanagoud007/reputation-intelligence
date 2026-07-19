"""
Workflow / Case Engine
Consumes from: reputation.alert.created
Produces to:   reputation.alert.created  (SLA breach re-publish)
               reputation.dlq (on failure)

FSM lifecycle: NEW -> ASSIGNED -> IN_PROGRESS -> RESOLVED / ESCALATED

What it does:
- Creates a case for every fired alert
- Assigns to an agent using round-robin or skill-based matching
  (skill match derived from alert risk_flags/topics)
- Sets an SLA deadline based on severity (critical=15min, high=30min,
  medium=60min, low=120min)
- A background SLA monitor loop checks for breached cases every 30s
  and re-publishes them to reputation.alert.created with escalated=true
- All state transitions are logged to case_events for audit trail

Run with: python -m app.services.workers.case_engine
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.alert.created"
TOPIC_OUT = "reputation.alert.created"   # escalations re-publish here
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "case-engine-group"

SLA_MINUTES = {
    "critical": 15,
    "high":     30,
    "medium":   60,
    "low":      120,
}

SLA_CHECK_INTERVAL = 30   # seconds

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Round-robin pointer per tenant (in-memory — fine for single instance)
_rr_pointer: dict[str, int] = {}


# ── Assignment logic ──────────────────────────────────────────────────────────
async def get_agents(db: AsyncSession, tenant_id: str) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id, name, email, skills
            FROM workflow.agents
            WHERE tenant_id = :tenant_id AND is_active = true
            ORDER BY name
        """),
        {"tenant_id": tenant_id},
    )
    return [
        {"id": str(r.id), "name": r.name, "email": r.email, "skills": r.skills or []}
        for r in result.fetchall()
    ]


def skill_match_agent(agents: list[dict], risk_flags: list[str], topics: list[str]) -> dict | None:
    """Find an agent whose skills overlap with the alert's risk_flags or topics."""
    tags = set(risk_flags) | set(topics)
    best, best_score = None, 0
    for agent in agents:
        overlap = len(set(agent["skills"]) & tags)
        if overlap > best_score:
            best, best_score = agent, overlap
    return best


def round_robin_agent(agents: list[dict], tenant_id: str) -> dict | None:
    if not agents:
        return None
    idx = _rr_pointer.get(tenant_id, 0) % len(agents)
    _rr_pointer[tenant_id] = idx + 1
    return agents[idx]


async def assign_agent(db: AsyncSession, tenant_id: str, risk_flags: list[str], topics: list[str]) -> tuple[dict | None, str]:
    agents = await get_agents(db, tenant_id)
    if not agents:
        return None, "none"

    # Try skill-based first
    if risk_flags or topics:
        skill_agent = skill_match_agent(agents, risk_flags, topics)
        if skill_agent:
            return skill_agent, "skill_based"

    # Fall back to round-robin
    return round_robin_agent(agents, tenant_id), "round_robin"


# ── Case creation ─────────────────────────────────────────────────────────────
async def create_case(db: AsyncSession, alert: dict) -> dict:
    severity     = alert.get("severity", "low")
    sla_minutes  = SLA_MINUTES.get(severity, 60)
    sla_deadline = datetime.now(timezone.utc) + timedelta(minutes=sla_minutes)

    agent, strategy = await assign_agent(
        db,
        alert.get("tenant_id"),
        alert.get("risk_flags", []),
        alert.get("topics", []),
    )

    status = "ASSIGNED" if agent else "NEW"

    result = await db.execute(
        text("""
            INSERT INTO workflow.cases
                (id, tenant_id, brand_id, location_id, alert_id, rule_name,
                 severity, status, assigned_to, assignment_strategy,
                 sla_minutes, sla_deadline, context, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :tenant_id, :brand_id, :location_id, :alert_id, :rule_name,
                 :severity, :status, :assigned_to, :strategy,
                 :sla_minutes, :sla_deadline, :context, now(), now())
            ON CONFLICT (alert_id) DO NOTHING
            RETURNING id, status, assigned_to, sla_deadline
        """),
        {
            "tenant_id":    alert.get("tenant_id"),
            "brand_id":     alert.get("brand_id"),
            "location_id":  alert.get("location_id"),
            "alert_id":     alert.get("alert_id"),
            "rule_name":    alert.get("rule_name"),
            "severity":     severity,
            "status":       status,
            "assigned_to":  agent["name"] if agent else None,
            "strategy":     strategy,
            "sla_minutes":  sla_minutes,
            "sla_deadline": sla_deadline,
            "context":      json.dumps({
                "location_name": alert.get("location_name"),
                "brand_name":    alert.get("brand_name"),
                "risk_flags":    alert.get("risk_flags", []),
                "topics":        alert.get("topics", []),
                "trigger_values": alert.get("trigger_values", {}),
            }),
        },
    )
    await db.commit()
    row = result.fetchone()

    if not row:
        # Already exists (duplicate alert) — fetch existing
        existing = await db.execute(
            text("SELECT id, status, assigned_to, sla_deadline FROM workflow.cases WHERE alert_id = :alert_id"),
            {"alert_id": alert.get("alert_id")},
        )
        row = existing.fetchone()

    case_id = str(row.id)

    # Log event
    await db.execute(
        text("""
            INSERT INTO workflow.case_events
                (id, case_id, event_type, from_status, to_status, actor, details, created_at)
            VALUES
                (gen_random_uuid(), :case_id, 'created', NULL, :status, :actor, :details, now())
        """),
        {
            "case_id": case_id,
            "status":  row.status,
            "actor":   "system",
            "details": json.dumps({"assigned_to": row.assigned_to, "strategy": strategy}),
        },
    )
    await db.commit()

    return {
        "case_id":      case_id,
        "status":       row.status,
        "assigned_to":  row.assigned_to,
        "sla_deadline": row.sla_deadline.isoformat() if row.sla_deadline else None,
    }


# ── SLA monitor (background loop) ─────────────────────────────────────────────
async def sla_monitor_loop(producer: AIOKafkaProducer):
    """Runs forever, checking for breached SLAs every 30s."""
    log.info("SLA monitor started")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT id, tenant_id, brand_id, location_id, alert_id, rule_name,
                               severity, assigned_to, context
                        FROM workflow.cases
                        WHERE status IN ('NEW', 'ASSIGNED', 'IN_PROGRESS')
                          AND sla_deadline < now()
                          AND sla_breached = false
                    """)
                )
                breached = result.fetchall()

                for case in breached:
                    case_id = str(case.id)
                    context = case.context if isinstance(case.context, dict) else json.loads(case.context)

                    # Mark as escalated + breached
                    await db.execute(
                        text("""
                            UPDATE workflow.cases
                            SET status = 'ESCALATED', sla_breached = true, updated_at = now()
                            WHERE id = :case_id
                        """),
                        {"case_id": case_id},
                    )
                    await db.execute(
                        text("""
                            INSERT INTO workflow.case_events
                                (id, case_id, event_type, from_status, to_status, actor, details, created_at)
                            VALUES
                                (gen_random_uuid(), :case_id, 'sla_breached', 'ASSIGNED', 'ESCALATED', 'system', :details, now())
                        """),
                        {"case_id": case_id, "details": json.dumps({"reason": "SLA deadline exceeded"})},
                    )
                    await db.commit()

                    # Re-publish escalated alert
                    escalated_alert = {
                        "schema_version": "1.0",
                        "alert_id":      f"escalated:{case.alert_id}",
                        "rule_name":     case.rule_name,
                        "tenant_id":     str(case.tenant_id),
                        "brand_id":      str(case.brand_id) if case.brand_id else None,
                        "location_id":   str(case.location_id) if case.location_id else None,
                        "location_name": context.get("location_name"),
                        "brand_name":    context.get("brand_name"),
                        "severity":      "critical",   # escalations are always critical
                        "escalated":     True,
                        "original_assignee": case.assigned_to,
                        "risk_flags":    context.get("risk_flags", []),
                        "topics":        context.get("topics", []),
                        "trigger_values": context.get("trigger_values", {}),
                        "channels":      {"email": ["manager@testfoods.com"]},
                        "fired_at":      datetime.now(timezone.utc).isoformat(),
                    }

                    await producer.send_and_wait(
                        TOPIC_OUT,
                        value=escalated_alert,
                        key=str(case.tenant_id),
                    )

                    log.warning(
                        "SLA breached — case escalated",
                        case_id=case_id,
                        rule=case.rule_name,
                        assigned_to=case.assigned_to,
                    )

        except Exception as e:
            log.error("SLA monitor error", error=str(e))

        await asyncio.sleep(SLA_CHECK_INTERVAL)


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting case engine", topic_in=TOPIC_IN)

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=20,
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
    log.info("Case engine ready")

    # Start SLA monitor as background task
    sla_task = asyncio.create_task(sla_monitor_loop(producer))

    try:
        async for msg in consumer:
            alert    = msg.value
            alert_id = alert.get("alert_id", "unknown")
            tenant_id = alert.get("tenant_id", "unknown")

            # Skip escalated re-publishes — don't create a case for a case
            if alert.get("escalated"):
                await consumer.commit()
                continue

            log.info("Creating case for alert", alert_id=alert_id, severity=alert.get("severity"))

            try:
                async with AsyncSessionLocal() as db:
                    case = await create_case(db, alert)

                await consumer.commit()

                log.info(
                    "Case created",
                    case_id=case["case_id"],
                    status=case["status"],
                    assigned_to=case["assigned_to"],
                    sla_deadline=case["sla_deadline"],
                )

            except Exception as e:
                log.error("Case creation failed", alert_id=alert_id, error=str(e))
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={**alert, "dlq_reason": str(e), "dlq_stage": "case_engine",
                               "dlq_at": datetime.now(timezone.utc).isoformat()},
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))

    finally:
        sla_task.cancel()
        await consumer.stop()
        await producer.stop()
        await engine.dispose()
        log.info("Case engine stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
