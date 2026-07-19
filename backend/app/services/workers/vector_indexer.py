"""
Vector Indexer Worker
Consumes from: reputation.ai.merged
Indexes to:    Qdrant collection reviews_{tenant_id}

What it does:
- Generates 384-dim sentence embeddings using all-MiniLM-L6-v2
- Stores vectors in Qdrant with full review metadata as payload
- Enables semantic search: "find reviews about hygiene" → top-K similar reviews
- Collection per tenant for data isolation

Model: sentence-transformers/all-MiniLM-L6-v2 (~90MB, cached on first run)
Dimensions: 384
Distance: Cosine similarity

Run with: python -m app.services.workers.vector_indexer
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN   = "reputation.ai.merged"
GROUP_ID   = "vector-indexer-group"
MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM = 384

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# ── Model loader ──────────────────────────────────────────────────────────────
_model: SentenceTransformer | None = None

def load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("Loading sentence transformer model", model=MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        log.info("Model loaded", dimensions=VECTOR_DIM)
    return _model

def embed(text: str) -> list[float]:
    model = load_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


# ── Qdrant helpers ────────────────────────────────────────────────────────────
def collection_name(tenant_id: str) -> str:
    return f"reviews_{tenant_id.replace('-', '_')}"

def ensure_collection(client: QdrantClient, tenant_id: str):
    name = collection_name(tenant_id)
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection", collection=name)

def build_payload(message: dict) -> dict:
    normalized = message.get("normalized_content", {})
    return {
        "message_id":      message.get("message_id"),
        "tenant_id":       message.get("tenant_id"),
        "brand_id":        message.get("brand_id"),
        "brand_name":      message.get("brand_name"),
        "location_id":     message.get("location_id"),
        "location_name":   message.get("location_name"),
        "source_platform": message.get("source_platform"),
        "text_cleaned":    normalized.get("text_cleaned", ""),
        "rating":          normalized.get("rating"),
        "sentiment":       message.get("sentiment"),
        "sentiment_score": message.get("sentiment_score"),
        "topics":          message.get("topics", []),
        "risk_level":      message.get("risk_level", "NONE"),
        "risk_flags":      message.get("risk_flags", []),
        "review_date":     normalized.get("review_date"),
        "indexed_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting vector indexer", topic_in=TOPIC_IN)

    # Load model on startup
    load_model()

    # Qdrant client (sync — qdrant_client doesn't need async for single ops)
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    log.info("Qdrant connected")

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=32,
        session_timeout_ms=60000,
        heartbeat_interval_ms=15000,
    )

    await consumer.start()
    log.info("Vector indexer ready")

    ensured_collections = set()

    try:
        async for msg in consumer:
            message    = msg.value
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")
            text       = message.get("normalized_content", {}).get("text_cleaned", "")

            if not text:
                log.warning("Empty text, skipping", message_id=message_id)
                await consumer.commit()
                continue

            log.info("Vectorizing review", message_id=message_id, tenant_id=tenant_id)

            try:
                # Ensure collection exists
                if tenant_id not in ensured_collections:
                    ensure_collection(qdrant, tenant_id)
                    ensured_collections.add(tenant_id)

                # Generate embedding (CPU — runs in thread to not block event loop)
                loop    = asyncio.get_event_loop()
                vector  = await loop.run_in_executor(None, embed, text)

                # Use deterministic point ID from message_id UUID
                point_id = str(uuid.UUID(message_id)) if message_id != "unknown" else str(uuid.uuid4())

                payload = build_payload(message)

                qdrant.upsert(
                    collection_name=collection_name(tenant_id),
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=payload,
                        )
                    ],
                )

                await consumer.commit()

                log.info(
                    "Review vectorized and stored",
                    message_id=message_id,
                    collection=collection_name(tenant_id),
                    vector_dim=len(vector),
                )

            except Exception as e:
                log.error("Vector indexing failed", message_id=message_id, error=str(e))

    finally:
        await consumer.stop()
        log.info("Vector indexer stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
