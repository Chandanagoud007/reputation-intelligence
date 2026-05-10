"""
Zomato Play Store Review Seeder
Pulls real Zomato reviews and ingests them into the platform.
Run with: python -m app.scripts.seed_zomato
"""
import asyncio
import uuid
from datetime import datetime

from google_play_scraper import reviews, Sort
import structlog

log = structlog.get_logger()

# Use your existing tenant and location
TENANT_ID = "f2c42063-d889-4779-b32b-713261580ef6"
LOCATION_ID = "0a04153a-cec6-4909-ad85-42c2cca72c1c"
PACKAGE_NAME = "com.application.zomato"


async def seed_zomato_reviews(count: int = 200):
    from app.core.database import init_mongo, init_postgres, init_redis
    from app.services.ingestion.review_store import review_store
    from app.services.nlp.sentiment import sentiment_service

    await init_postgres()
    await init_mongo()
    await init_redis()

    log.info("Fetching Zomato reviews from Play Store", count=count)

    result, _ = reviews(
        PACKAGE_NAME,
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=count,
    )

    log.info("Fetched reviews", total=len(result))

    enriched = []
    for r in result:
        try:
            content = r.get("content", "").strip()
            if not content:
                continue

            # Analyze sentiment
            sentiment = await sentiment_service.analyze(content, "en")

            review_doc = {
                "tenant_id": TENANT_ID,
                "location_id": LOCATION_ID,
                "platform": "play_store",
                "external_id": r.get("reviewId", str(uuid.uuid4())),
                "rating": float(r.get("score", 3)),
                "title": None,
                "content": content,
                "language": "en",
                "author": {"name": r.get("userName", "Anonymous")},
                "review_url": None,
                "published_at": r.get("at", datetime.utcnow()),
                "sentiment": {
                    "label": sentiment.label.value,
                    "score": sentiment.score,
                    "positive_score": sentiment.positive_score,
                    "negative_score": sentiment.negative_score,
                    "neutral_score": sentiment.neutral_score,
                    "emotions": sentiment.emotions,
                    "topics": sentiment.topics,
                    "provider": sentiment.provider,
                },
                "is_analyzed": True,
            }
            enriched.append(review_doc)

        except Exception as e:
            log.warning("Failed to process review", error=str(e))
            continue

    if enriched:
        changed = await review_store.upsert_many(enriched)
        log.info("Seeding complete", total=len(enriched), changed=changed)
        print(f"\n✅ Seeded {len(enriched)} Zomato reviews ({changed} new/updated)")
    else:
        print("No reviews to seed")


if __name__ == "__main__":
    asyncio.run(seed_zomato_reviews(count=200))
