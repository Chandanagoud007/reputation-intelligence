"""
Search Indexer Worker
Consumes from: reputation.ai.merged
Indexes to:    OpenSearch index rip_{tenant_id}_reviews

What it does:
- Creates per-tenant OpenSearch index if it doesn't exist
- Indexes each merged review with all fields (sentiment, topics, risk, score context)
- Supports full-text search, date range filters, faceted filters by platform/sentiment/location
- Uses bulk indexing for efficiency

Index naming: rip_{tenant_id}_reviews (tenant-isolated)

Run with: python -m app.services.workers.search_indexer
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer
from opensearchpy import AsyncOpenSearch

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN = "reputation.ai.merged"
GROUP_ID = "search-indexer-group"

OPENSEARCH_HOST = "localhost"
OPENSEARCH_PORT = 9200


def get_os_client() -> AsyncOpenSearch:
    return AsyncOpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def index_name(tenant_id: str) -> str:
    return f"rip_{tenant_id.replace('-', '')}_reviews"


INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "message_id":           {"type": "keyword"},
            "tenant_id":            {"type": "keyword"},
            "brand_id":             {"type": "keyword"},
            "brand_name":           {"type": "keyword"},
            "region_id":            {"type": "keyword"},
            "region_name":          {"type": "keyword"},
            "location_id":          {"type": "keyword"},
            "location_name":        {"type": "keyword"},
            "city":                 {"type": "keyword"},
            "state":                {"type": "keyword"},
            "country":              {"type": "keyword"},
            "source_platform":      {"type": "keyword"},
            "source_review_id":     {"type": "keyword"},
            "text_cleaned": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}
            },
            "reviewer_name":        {"type": "text"},
            "rating":               {"type": "float"},
            "sentiment_score":      {"type": "float"},
            "sentiment_confidence": {"type": "float"},
            "sentiment":            {"type": "keyword"},
            "sentiment_model":      {"type": "keyword"},
            "language":             {"type": "keyword"},
            "topics":               {"type": "keyword"},
            "risk_flags":           {"type": "keyword"},
            "risk_level":           {"type": "keyword"},
            "review_date":          {"type": "date"},
            "ingested_at":          {"type": "date"},
            "normalized_at":        {"type": "date"},
            "merged_at":            {"type": "date"},
            "indexed_at":           {"type": "date"},
            "is_duplicate":         {"type": "boolean"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    }
}


async def ensure_index(client: AsyncOpenSearch, tenant_id: str):
    idx = index_name(tenant_id)
    exists = await client.indices.exists(index=idx)
    if not exists:
        await client.indices.create(index=idx, body=INDEX_MAPPING)
        log.info("Created OpenSearch index", index=idx)


def build_document(message: dict) -> dict:
    normalized = message.get("normalized_content", {})
    return {
        "message_id":           message.get("message_id"),
        "tenant_id":            message.get("tenant_id"),
        "brand_id":             message.get("brand_id"),
        "brand_name":           message.get("brand_name"),
        "region_id":            message.get("region_id"),
        "region_name":          message.get("region_name"),
        "location_id":          message.get("location_id"),
        "location_name":        message.get("location_name"),
        "city":                 message.get("city"),
        "state":                message.get("state"),
        "country":              message.get("country"),
        "source_platform":      message.get("source_platform"),
        "source_review_id":     message.get("source_review_id"),
        "text_cleaned":         normalized.get("text_cleaned", ""),
        "reviewer_name":        normalized.get("reviewer_name"),
        "rating":               normalized.get("rating"),
        "language":             normalized.get("language", "en"),
        "review_date":          normalized.get("review_date"),
        "sentiment":            message.get("sentiment"),
        "sentiment_score":      message.get("sentiment_score"),
        "sentiment_confidence": message.get("sentiment_confidence"),
        "sentiment_model":      message.get("sentiment_model"),
        "topics":               message.get("topics", []),
        "risk_flags":           message.get("risk_flags", []),
        "risk_level":           message.get("risk_level", "NONE"),
        "is_duplicate":         message.get("is_duplicate", False),
        "ingested_at":          message.get("ingested_at"),
        "normalized_at":        message.get("normalized_at"),
        "merged_at":            message.get("merged_at"),
        "indexed_at":           datetime.now(timezone.utc).isoformat(),
    }


async def run_worker():
    log.info("Starting search indexer", topic_in=TOPIC_IN)

    client = get_os_client()
    info = await client.info()
    log.info("OpenSearch connected", version=info["version"]["number"])

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

    await consumer.start()
    log.info("Search indexer ready")

    ensured_indices = set()

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")

            log.info("Indexing review", message_id=message_id, tenant_id=tenant_id)

            try:
                if tenant_id not in ensured_indices:
                    await ensure_index(client, tenant_id)
                    ensured_indices.add(tenant_id)

                doc = build_document(message)
                idx = index_name(tenant_id)

                await client.index(index=idx, id=message_id, body=doc)
                await consumer.commit()

                log.info(
                    "Review indexed in OpenSearch",
                    message_id=message_id,
                    index=idx,
                    sentiment=doc.get("sentiment"),
                    topics=doc.get("topics"),
                )

            except Exception as e:
                log.error("Indexing failed", message_id=message_id, error=str(e))

    finally:
        await consumer.stop()
        await client.close()
        log.info("Search indexer stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
