"""
Topic Classifier Worker
Consumes from: reputation.ai.classified  (after sentiment enrichment)
Produces to:   reputation.ai.classified  (same topic — adds topic fields)

Wait — to keep workers independent, this worker reads from
reputation.entity.resolved and publishes enriched messages alongside
the sentiment worker. The scoring engine merges both.

Actually cleaner approach: sentiment worker publishes to reputation.ai.classified
and topic/risk/summary workers ALL consume from reputation.entity.resolved
and publish THEIR enrichment to reputation.ai.classified.
The scoring engine reads reputation.ai.classified and waits for all fields.

For simplicity in this implementation: topic worker consumes entity.resolved,
adds topic classification, publishes to reputation.ai.classified.
Sentiment worker does the same. Last writer wins on duplicate message_ids
(scoring engine deduplicates by message_id).

Model: keyword-based multi-label classifier (free, instant, no download)
       Upgrade path: facebook/bart-large-mnli zero-shot when budget allows
Labels: food, service, staff, ambience, pricing, wait_time, hygiene,
        delivery, packaging, value_for_money

Run with: python -m app.services.workers.topic_worker
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
GROUP_ID  = "topic-worker-group"

# ── Keyword taxonomy ──────────────────────────────────────────────────────────
# Each label maps to a list of keywords/phrases.
# Case-insensitive. Multi-label — a review can match multiple topics.
DEFAULT_TAXONOMY = {
    "food": [
        "food", "taste", "flavor", "flavour", "delicious", "tasty", "bland", "spicy",
        "fresh", "stale", "portion", "dish", "meal", "cuisine", "biryani", "pizza",
        "burger", "sushi", "dessert", "drink", "beverage", "menu", "recipe", "cook",
        "chef", "quality", "ingredient", "raw", "overcooked", "undercooked",
    ],
    "service": [
        "service", "staff", "waiter", "waitress", "server", "rude", "friendly",
        "helpful", "attentive", "ignored", "slow", "fast", "quick", "prompt",
        "courteous", "polite", "unprofessional", "professional", "customer service",
    ],
    "staff": [
        "manager", "employee", "crew", "team", "host", "hostess", "bartender",
        "cashier", "receptionist", "behavior", "attitude", "manner",
    ],
    "ambience": [
        "ambience", "ambiance", "atmosphere", "decor", "decoration", "vibe",
        "cozy", "comfortable", "noisy", "loud", "quiet", "clean", "dirty",
        "lighting", "music", "seating", "interior", "environment", "setting",
    ],
    "pricing": [
        "price", "pricing", "expensive", "cheap", "affordable", "overpriced",
        "value", "worth", "cost", "bill", "charge", "fee", "rate", "budget",
        "pricey", "reasonable", "costly",
    ],
    "wait_time": [
        "wait", "waiting", "waited", "long wait", "quick", "slow", "delay",
        "delayed", "fast", "speedy", "time", "minutes", "hours", "reservation",
        "queue", "line",
    ],
    "hygiene": [
        "hygiene", "clean", "dirty", "cleanliness", "sanitize", "sanitary",
        "unhygienic", "cockroach", "pest", "rodent", "mold", "mould", "smell",
        "odor", "odour", "stench", "washroom", "bathroom", "toilet", "restroom",
    ],
    "delivery": [
        "delivery", "deliver", "delivered", "courier", "rider", "driver",
        "packaging", "package", "box", "bag", "wrapped", "seal", "tamper",
        "on time", "late delivery", "cold food", "spilled",
    ],
    "value_for_money": [
        "value for money", "worth it", "money's worth", "good deal", "bad deal",
        "rip off", "ripoff", "overcharge", "discount", "offer", "deal", "combo",
    ],
}


def classify_topics(text: str, taxonomy: dict = None) -> list[str]:
    """
    Multi-label keyword-based topic classification.
    Returns top 3 matched topics sorted by match count.
    """
    tax   = taxonomy or DEFAULT_TAXONOMY
    text_lower = text.lower()
    scores = {}

    for label, keywords in tax.items():
        count = 0
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                count += 1
        if count > 0:
            scores[label] = count

    # Sort by match count descending, return top 3
    sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [t[0] for t in sorted_topics[:3]]


def load_tenant_taxonomy(tenant_id: str) -> dict:
    """
    Load custom taxonomy YAML for a tenant if it exists.
    Falls back to default taxonomy.
    Path: ./config/taxonomies/{tenant_id}.yaml
    """
    import os
    yaml_path = os.path.join(
        os.path.dirname(__file__), "config", "taxonomies", f"{tenant_id}.yaml"
    )
    if not os.path.exists(yaml_path):
        return DEFAULT_TAXONOMY
    try:
        import yaml
        with open(yaml_path) as f:
            custom = yaml.safe_load(f)
        # Merge custom on top of default
        merged = {**DEFAULT_TAXONOMY, **custom}
        log.info("Loaded custom taxonomy", tenant_id=tenant_id)
        return merged
    except Exception as e:
        log.warning("Failed to load custom taxonomy, using default", error=str(e))
        return DEFAULT_TAXONOMY


# Cache taxonomies per tenant so we don't reload on every message
_taxonomy_cache: dict[str, dict] = {}


def get_taxonomy(tenant_id: str) -> dict:
    if tenant_id not in _taxonomy_cache:
        _taxonomy_cache[tenant_id] = load_tenant_taxonomy(tenant_id)
    return _taxonomy_cache[tenant_id]


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting topic worker", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

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
    log.info("Topic worker ready")

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            try:
                text       = message.get("normalized_content", {}).get("text_cleaned", "")
                taxonomy   = get_taxonomy(tenant_id)
                topic_hint = message.get("metadata", {}).get("topic_hint")

                topics = classify_topics(text, taxonomy)

                # If the connector/loader supplied a topic hint (e.g. app feature name
                # like "Payments", "Timesheet Requisition"), include it as a topic too.
                # This is common for app store / play store reviews where the review
                # title already names the feature area being discussed.
                if topic_hint:
                    hint_normalized = topic_hint.strip().lower().replace(" ", "_")
                    if hint_normalized not in topics:
                        topics.insert(0, hint_normalized)
                    topics = topics[:5]   # cap at 5 topics total

                enriched = {
                    **message,
                    "topics": topics,
                    "topic_classified_at": datetime.now(timezone.utc).isoformat(),
                }

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=enriched,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("schema_version", b"1.0"),
                        ("worker", b"topic"),
                    ],
                )
                await consumer.commit()

                log.info(
                    "Topics classified",
                    message_id=message_id,
                    topics=topics,
                )

            except Exception as e:
                log.error("Topic classification failed", message_id=message_id, error=str(e))
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={**message, "dlq_reason": str(e), "dlq_stage": "topic", "dlq_at": datetime.now(timezone.utc).isoformat()},
                        key=tenant_id,
                    )
                    await consumer.commit()
                except Exception as dlq_err:
                    log.critical("DLQ publish failed", error=str(dlq_err))

    finally:
        await consumer.stop()
        await producer.stop()
        log.info("Topic worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
