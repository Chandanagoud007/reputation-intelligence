"""
Bulk Review Loader v2
Handles multiple source schemas:
  - Standard review format (app_store, google_play, trustpilot etc.)
  - YouTube comment format (commentId, author, text, publishedAt)
  - Social media format (twitter, instagram, facebook, linkedin)
"""
import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.kafka_producer import init_kafka_producer, close_kafka_producer, publish_review

log = structlog.get_logger()

DEFAULT_TENANT_ID = "209d4d08-89a1-4a9f-a4c0-b2d843fe0b2e"

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def normalize_platform(source: str) -> str:
    mapping = {
        "app_store": "app_store", "ios": "app_store",
        "play_store": "google_play", "google_play": "google_play", "android": "google_play",
        "youtube": "youtube", "twitter": "twitter", "instagram": "instagram",
        "facebook": "facebook", "linkedin": "linkedin",
        "trustpilot": "trustpilot", "glassdoor": "glassdoor",
        "zomato": "zomato", "swiggy": "swiggy",
    }
    return mapping.get(source.lower(), source.lower())


def detect_schema(record: dict) -> str:
    if "commentId" in record:
        return "youtube_comment"
    if "tweetId" in record or "tweet_id" in record:
        return "twitter"
    if "postId" in record or "post_id" in record:
        return "social"
    if "reviewId" in record or "rating" in record:
        return "standard_review"
    if "text" in record and "author" in record and "rating" not in record:
        return "youtube_comment"
    return "generic"


def map_record(record: dict, platform: str) -> dict:
    schema = detect_schema(record)

    if schema == "youtube_comment":
        return {
            "source_platform":  platform,
            "source_review_id": record.get("commentId") or str(uuid.uuid4()),
            "rating":           3.0,
            "text":             record.get("text", ""),
            "reviewer_name":    record.get("author"),
            "review_date":      record.get("publishedAt") or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "topic_hint": record.get("videoTitle"),
                "video_id":   record.get("videoId"),
                "like_count": record.get("likeCount", 0),
                "schema":     schema,
            },
        }

    if schema in ("twitter", "social"):
        return {
            "source_platform":  platform,
            "source_review_id": (record.get("tweetId") or record.get("postId") or
                                  record.get("tweet_id") or record.get("post_id") or str(uuid.uuid4())),
            "rating":           3.0,
            "text":             record.get("text") or record.get("content", ""),
            "reviewer_name":    record.get("author") or record.get("userName") or record.get("username"),
            "review_date":      record.get("date") or record.get("publishedAt") or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "topic_hint": record.get("title"),
                "like_count": record.get("likeCount", 0),
                "schema":     schema,
            },
        }

    return {
        "source_platform":  platform,
        "source_review_id": record.get("reviewId") or str(uuid.uuid4()),
        "rating":           float(record.get("rating", 3.0)),
        "text":             record.get("content") or record.get("text", ""),
        "reviewer_name":    record.get("userName") or record.get("author"),
        "review_date":      record.get("date") or record.get("publishedAt") or datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "topic_hint":  record.get("title"),
            "app_version": record.get("appVersion"),
            "schema":      schema,
        },
    }


async def ensure_hierarchy(db: AsyncSession, tenant_id: str, brand_name: str, platform: str) -> dict:
    brand_slug = brand_name.lower().replace(" ", "-")

    result = await db.execute(
        text("SELECT id FROM tenant_mgmt.brands WHERE tenant_id = :tid AND slug = :slug"),
        {"tid": tenant_id, "slug": brand_slug},
    )
    row = result.fetchone()
    if row:
        brand_id = str(row.id)
    else:
        brand_id = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO tenant_mgmt.brands (id, tenant_id, name, slug, is_active, metadata, created_at, updated_at) VALUES (:id, :tid, :name, :slug, true, '{}', now(), now())"),
            {"id": brand_id, "tid": tenant_id, "name": brand_name, "slug": brand_slug},
        )
        log.info("Created brand", brand=brand_name)

    result = await db.execute(
        text("SELECT id FROM tenant_mgmt.regions WHERE brand_id = :bid AND slug = 'default-region'"),
        {"bid": brand_id},
    )
    row = result.fetchone()
    if row:
        region_id = str(row.id)
    else:
        region_id = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO tenant_mgmt.regions (id, brand_id, name, slug, country, is_active, metadata, created_at, updated_at) VALUES (:id, :bid, 'Default Region', 'default-region', 'IN', true, '{}', now(), now())"),
            {"id": region_id, "bid": brand_id},
        )

    location_name = f"{brand_name} — {platform}"
    result = await db.execute(
        text("SELECT id FROM tenant_mgmt.locations WHERE region_id = :rid AND name = :name"),
        {"rid": region_id, "name": location_name},
    )
    row = result.fetchone()
    if row:
        location_id = str(row.id)
    else:
        location_id = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO tenant_mgmt.locations (id, region_id, name, address, city, state, country, postal_code, timezone, is_active, metadata, created_at, updated_at) VALUES (:id, :rid, :name, 'Virtual', NULL, NULL, 'IN', NULL, 'Asia/Kolkata', true, '{}', now(), now())"),
            {"id": location_id, "rid": region_id, "name": location_name},
        )
        log.info("Created location", location=location_name)

    await db.commit()
    return {"brand_id": brand_id, "region_id": region_id, "location_id": location_id, "location_name": location_name}


async def load_file(filepath: str, brand_name: str, tenant_id: str, rate: int):
    log.info("Loading file", filepath=filepath, brand=brand_name, rate=rate)

    with open(filepath, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        log.warning("File is empty")
        return

    raw_platform = records[0].get("source", "unknown")
    platform = normalize_platform(raw_platform)
    schema = detect_schema(records[0])
    log.info("File info", platform=platform, schema=schema, total=len(records))

    async with AsyncSessionLocal() as db:
        hierarchy = await ensure_hierarchy(db, tenant_id, brand_name, platform)
    log.info("Hierarchy ready", **hierarchy)

    await init_kafka_producer()
    delay = 1.0 / rate if rate > 0 else 0
    published = failed = skipped = 0

    try:
        for record in records:
            mapped = map_record(record, platform)
            if not mapped["text"].strip():
                skipped += 1
                continue
            try:
                await publish_review(tenant_id=tenant_id, brand_id=hierarchy["brand_id"],
                                     location_id=hierarchy["location_id"], **mapped)
                published += 1
                if published % 500 == 0:
                    log.info("Progress", published=published, total=len(records))
            except Exception as e:
                failed += 1
                log.error("Publish failed", error=str(e))
            if delay:
                await asyncio.sleep(delay)
    finally:
        await close_kafka_producer()

    log.info("Load complete", published=published, failed=failed, skipped=skipped, total=len(records))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",   required=True)
    parser.add_argument("--brand",  required=True)
    parser.add_argument("--tenant", default=DEFAULT_TENANT_ID)
    parser.add_argument("--rate",   type=int, default=50)
    args = parser.parse_args()
    asyncio.run(load_file(args.file, args.brand, args.tenant, args.rate))

if __name__ == "__main__":
    main()
