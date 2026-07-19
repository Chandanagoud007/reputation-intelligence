"""
Risk Detector Worker
Consumes from: reputation.entity.resolved
Produces to:   reputation.ai.classified (adds risk fields)
               reputation.dlq (on failure)

Pipeline: regex first-pass → keyword scoring → risk level assignment
Risk levels: LOW / MEDIUM / HIGH / CRITICAL
Risk types: legal_threat, health_violation, safety_incident,
            media_escalation, abusive_language, crisis_keyword

Configurable keyword blocklist per tenant:
    ./config/risk/{tenant_id}.yaml

Run with: python -m app.services.workers.risk_worker
"""
import asyncio
import json
import re
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.entity.resolved"
TOPIC_OUT = "reputation.ai.classified"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "risk-worker-group"

# ── Risk patterns ─────────────────────────────────────────────────────────────
# Each entry: (risk_type, level, patterns[])
# Patterns are regex strings, case-insensitive
RISK_PATTERNS = [
    # CRITICAL
    ("legal_threat", "CRITICAL", [
        r"\b(sue|lawsuit|lawyer|attorney|legal action|court|litigation|police|FIR|complaint)\b",
        r"\b(going to report|reported to|health department|food safety|FSSAI|FDA)\b",
    ]),
    ("health_violation", "CRITICAL", [
        r"\b(food poisoning|food poison|got sick|fell ill|hospitalized|vomiting|diarrhea|diarrhoea)\b",
        r"\b(cockroach|rat|rodent|pest|maggot|worm|foreign object|hair in food|insect)\b",
        r"\b(expired|expiry|rotten|mold|mould|spoiled|contaminated)\b",
    ]),
    ("safety_incident", "CRITICAL", [
        r"\b(injured|injury|accident|burned|scalded|broken glass|chipped|hurt|wound)\b",
        r"\b(allergic reaction|anaphylaxis|allergy attack)\b",
    ]),
    # HIGH
    ("media_escalation", "HIGH", [
        r"\b(going viral|post on social media|tweet|instagram|facebook|review bomb|zomato blog)\b",
        r"\b(news|journalist|reporter|media|newspaper|TV channel|expose)\b",
        r"\b(never coming back|telling everyone|warn people|avoid this place)\b",
    ]),
    ("abusive_language", "HIGH", [
        r"\b(scam|fraud|cheat|thief|steal|lied|lie|fake|disgusting|horrible|terrible|worst ever)\b",
        r"\b(harassment|harassed|threatened|abused|rude staff|disrespect)\b",
    ]),
    # MEDIUM
    ("crisis_keyword", "MEDIUM", [
        r"\b(refund|compensation|sorry|apology|escalate|manager|owner|headquarters)\b",
        r"\b(very disappointed|extremely upset|unacceptable|outrageous|disgusted)\b",
    ]),
    # LOW
    ("general_complaint", "LOW", [
        r"\b(not happy|unhappy|dissatisfied|bad experience|poor quality|below average)\b",
    ]),
]

LEVEL_PRIORITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def detect_risks(text: str, extra_patterns: list = None) -> dict:
    """
    Run regex risk detection pipeline.
    Returns highest risk level found + list of all detected risk types.
    """
    text_lower = text.lower()
    detected   = []
    max_level  = "NONE"

    all_patterns = RISK_PATTERNS + (extra_patterns or [])

    for risk_type, level, patterns in all_patterns:
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if risk_type not in [d["type"] for d in detected]:
                    detected.append({"type": risk_type, "level": level})
                if LEVEL_PRIORITY.get(level, 0) > LEVEL_PRIORITY.get(max_level, 0):
                    max_level = level
                break

    return {
        "risk_flags": [d["type"] for d in detected],
        "risk_level": max_level if detected else "NONE",
        "risk_details": detected,
    }


def load_tenant_risk_config(tenant_id: str) -> list:
    """Load custom risk keyword blocklist for a tenant if it exists."""
    import os
    yaml_path = os.path.join(
        os.path.dirname(__file__), "config", "risk", f"{tenant_id}.yaml"
    )
    if not os.path.exists(yaml_path):
        return []
    try:
        import yaml
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        custom = []
        for item in config.get("patterns", []):
            custom.append((
                item.get("type", "custom"),
                item.get("level", "MEDIUM"),
                item.get("patterns", []),
            ))
        return custom
    except Exception as e:
        log.warning("Failed to load tenant risk config", error=str(e))
        return []


_risk_config_cache: dict[str, list] = {}


def get_risk_config(tenant_id: str) -> list:
    if tenant_id not in _risk_config_cache:
        _risk_config_cache[tenant_id] = load_tenant_risk_config(tenant_id)
    return _risk_config_cache[tenant_id]


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting risk worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

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
    log.info("Risk worker ready")

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            try:
                text         = message.get("normalized_content", {}).get("text_cleaned", "")
                extra        = get_risk_config(tenant_id)
                risk_result  = detect_risks(text, extra)

                enriched = {
                    **message,
                    "risk_flags":   risk_result["risk_flags"],
                    "risk_level":   risk_result["risk_level"],
                    "risk_details": risk_result["risk_details"],
                    "risk_detected_at": datetime.now(timezone.utc).isoformat(),
                }

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=enriched,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("schema_version", b"1.0"),
                        ("worker", b"risk"),
                    ],
                )
                await consumer.commit()

                if risk_result["risk_level"] in ("HIGH", "CRITICAL"):
                    log.warning(
                        "High risk review detected",
                        message_id=message_id,
                        risk_level=risk_result["risk_level"],
                        risk_flags=risk_result["risk_flags"],
                    )
                else:
                    log.info(
                        "Risk assessed",
                        message_id=message_id,
                        risk_level=risk_result["risk_level"],
                    )

            except Exception as e:
                log.error("Risk detection failed", message_id=message_id, error=str(e))
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={**message, "dlq_reason": str(e), "dlq_stage": "risk", "dlq_at": datetime.now(timezone.utc).isoformat()},
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))

    finally:
        await consumer.stop()
        await producer.stop()
        log.info("Risk worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
