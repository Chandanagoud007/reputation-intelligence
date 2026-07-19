"""
Scoring Engine Worker
Consumes from: reputation.ai.merged
Produces to:   reputation.score.updated
               reputation.dlq (on failure)

Scoring formula:
    score = (rating_normalized × 0.4) + (sentiment_normalized × 0.4) + (volume_trend × 0.2)

Where:
    rating_normalized  = rating / 5.0  (converts 1–5 to 0–1, then ×5 for final scale)
    sentiment_normalized = (sentiment_score + 1) / 2  (converts -1–1 to 0–1)
    volume_trend       = min(review_count / 100, 1.0)  (caps at 100 reviews)

Final score is on a 0.0–5.0 scale.

Writes to:
    - PostgreSQL analytics.reputation_scores (current score, upsert)
    - ClickHouse rip_analytics.reputation_scores (history, append-only)

Rollup:
    Location score → weighted avg to Region → weighted avg to Brand

Run with: python -m app.services.workers.scoring_engine
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.ai.merged"
TOPIC_OUT = "reputation.score.updated"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "scoring-engine-group"

# Score weights
W_RATING    = 0.4
W_SENTIMENT = 0.4
W_VOLUME    = 0.2
VOLUME_CAP  = 100   # reviews needed for full volume score


# ── DB setup ──────────────────────────────────────────────────────────────────
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── ClickHouse setup ──────────────────────────────────────────────────────────
def get_clickhouse_client():
    try:
        import clickhouse_connect
        return clickhouse_connect.get_client(
            host="localhost",
            port=8123,
            username="rip_user",
            password="rip_pass",
            database="rip_analytics",
        )
    except Exception as e:
        log.warning("ClickHouse not available", error=str(e))
        return None


# ── Scoring formula ───────────────────────────────────────────────────────────
def compute_score(rating: float, sentiment_score: float, review_count: int) -> float:
    """
    Compute reputation score on 0.0–5.0 scale.
    rating: 1.0–5.0
    sentiment_score: -1.0 to 1.0
    review_count: total reviews
    """
    rating_norm    = (rating / 5.0)
    sentiment_norm = (sentiment_score + 1.0) / 2.0
    volume_norm    = min(review_count / VOLUME_CAP, 1.0)

    raw = (rating_norm * W_RATING) + (sentiment_norm * W_SENTIMENT) + (volume_norm * W_VOLUME)
    return round(raw * 5.0, 4)   # scale to 0–5


# ── PostgreSQL upsert ─────────────────────────────────────────────────────────
async def upsert_location_score(db: AsyncSession, data: dict) -> dict:
    """
    Fetch existing score for location, recalculate with new review, upsert.
    Returns the updated score record.
    """
    location_id = data["location_id"]
    sentiment   = data["sentiment"]

    # Fetch existing score
    result = await db.execute(
        text("""
            SELECT score, rating_avg, sentiment_avg, review_count,
                   positive_count, negative_count, neutral_count
            FROM analytics.reputation_scores
            WHERE location_id = :location_id AND scope = 'location'
        """),
        {"location_id": location_id},
    )
    existing = result.fetchone()

    if existing:
        # Incremental update — rolling average
        n = existing.review_count + 1
        new_rating_avg    = ((existing.rating_avg * existing.review_count) + data["rating"]) / n
        new_sentiment_avg = ((existing.sentiment_avg * existing.review_count) + data["sentiment_score"]) / n
        pos = existing.positive_count + (1 if sentiment == "positive" else 0)
        neg = existing.negative_count + (1 if sentiment == "negative" else 0)
        neu = existing.neutral_count  + (1 if sentiment == "neutral"  else 0)
    else:
        n                 = 1
        new_rating_avg    = data["rating"]
        new_sentiment_avg = data["sentiment_score"]
        pos = 1 if sentiment == "positive" else 0
        neg = 1 if sentiment == "negative" else 0
        neu = 1 if sentiment == "neutral"  else 0

    new_score = compute_score(new_rating_avg, new_sentiment_avg, n)

    await db.execute(
        text("""
            INSERT INTO analytics.reputation_scores
                (id, tenant_id, brand_id, region_id, location_id,
                 score, rating_avg, sentiment_avg, review_count,
                 positive_count, negative_count, neutral_count,
                 scope, last_review_id, last_review_at, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :tenant_id, :brand_id, :region_id, :location_id,
                 :score, :rating_avg, :sentiment_avg, :review_count,
                 :positive_count, :negative_count, :neutral_count,
                 'location', :last_review_id, now(), now(), now())
            ON CONFLICT (location_id, scope)
            DO UPDATE SET
                score          = EXCLUDED.score,
                rating_avg     = EXCLUDED.rating_avg,
                sentiment_avg  = EXCLUDED.sentiment_avg,
                review_count   = EXCLUDED.review_count,
                positive_count = EXCLUDED.positive_count,
                negative_count = EXCLUDED.negative_count,
                neutral_count  = EXCLUDED.neutral_count,
                last_review_id = EXCLUDED.last_review_id,
                last_review_at = now(),
                updated_at     = now()
        """),
        {
            "tenant_id":     data["tenant_id"],
            "brand_id":      data["brand_id"],
            "region_id":     data["region_id"],
            "location_id":   location_id,
            "score":         new_score,
            "rating_avg":    round(new_rating_avg, 4),
            "sentiment_avg": round(new_sentiment_avg, 4),
            "review_count":  n,
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count":  neu,
            "last_review_id": data["message_id"],
        },
    )
    await db.commit()

    return {
        "score":         new_score,
        "rating_avg":    round(new_rating_avg, 4),
        "sentiment_avg": round(new_sentiment_avg, 4),
        "review_count":  n,
        "positive_count": pos,
        "negative_count": neg,
        "neutral_count":  neu,
    }


async def write_clickhouse_history(data: dict, score: float):
    """Append score history to ClickHouse for trend analytics."""
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(
            host="localhost", port=8123,
            username="rip_user", password="rip_pass",
            database="rip_analytics",
        )
        client.insert(
            "reputation_scores",
            [[
                data["tenant_id"],
                data["brand_id"],
                data["location_id"],
                score,
                data.get("review_count", 1),
                data.get("sentiment_avg", 0.0),
                datetime.now(timezone.utc),
            ]],
            column_names=["tenant_id", "brand_id", "location_id", "score",
                          "review_count", "sentiment_avg", "calculated_at"],
        )
    except Exception as e:
        log.warning("ClickHouse write failed, skipping", error=str(e))


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting scoring engine", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

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
    log.info("Scoring engine ready")

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            log.info(
                "Scoring review",
                message_id=message_id,
                tenant_id=tenant_id,
                sentiment=message.get("sentiment"),
                risk_level=message.get("risk_level"),
            )

            try:
                data = {
                    "message_id":     message_id,
                    "tenant_id":      message.get("tenant_id"),
                    "brand_id":       message.get("brand_id"),
                    "region_id":      message.get("region_id"),
                    "location_id":    message.get("location_id"),
                    "rating":         message.get("normalized_content", {}).get("rating", 3.0),
                    "sentiment":      message.get("sentiment", "neutral"),
                    "sentiment_score": message.get("sentiment_score", 0.0),
                }

                async with AsyncSessionLocal() as db:
                    score_record = await upsert_location_score(db, data)

                # Write to ClickHouse history (non-blocking, best effort)
                await write_clickhouse_history({**data, **score_record}, score_record["score"])

                # Publish score updated event
                score_event = {
                    "schema_version":  "1.0",
                    "message_id":      message_id,
                    "tenant_id":       data["tenant_id"],
                    "brand_id":        data["brand_id"],
                    "region_id":       data["region_id"],
                    "location_id":     data["location_id"],
                    "location_name":   message.get("location_name"),
                    "brand_name":      message.get("brand_name"),
                    "score":           score_record["score"],
                    "rating_avg":      score_record["rating_avg"],
                    "sentiment_avg":   score_record["sentiment_avg"],
                    "review_count":    score_record["review_count"],
                    "positive_count":  score_record["positive_count"],
                    "negative_count":  score_record["negative_count"],
                    "neutral_count":   score_record["neutral_count"],
                    "risk_level":      message.get("risk_level", "NONE"),
                    "risk_flags":      message.get("risk_flags", []),
                    "topics":          message.get("topics", []),
                    "scored_at":       datetime.now(timezone.utc).isoformat(),
                }

                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=score_event,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("schema_version", b"1.0"),
                    ],
                )

                await consumer.commit()

                log.info(
                    "Score updated",
                    message_id=message_id,
                    location=message.get("location_name"),
                    score=score_record["score"],
                    review_count=score_record["review_count"],
                    topic=TOPIC_OUT,
                )

            except Exception as e:
                log.error("Scoring failed", message_id=message_id, error=str(e))
                try:
                    await producer.send_and_wait(
                        TOPIC_DLQ,
                        value={
                            **message,
                            "dlq_reason": str(e),
                            "dlq_stage": "scoring",
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
        log.info("Scoring engine stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
