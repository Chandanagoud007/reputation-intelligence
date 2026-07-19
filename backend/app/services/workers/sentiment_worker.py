"""
Sentiment Worker
Consumes from: reputation.entity.resolved
Produces to:   reputation.ai.classified (partial — adds sentiment fields)
               reputation.dlq (on failure)

Model: cardiffnlp/twitter-roberta-base-sentiment-latest (HuggingFace)
       ~500MB, cached at ./models/roberta-sentiment/ on first run
Fallback: VADER for short text (< 20 tokens)
Batch size: 32, flush interval: 500ms

Run with: python -m app.services.workers.sentiment_worker
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.entity.resolved"
TOPIC_OUT = "reputation.ai.classified"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "sentiment-worker-group"

BATCH_SIZE     = 32
FLUSH_INTERVAL = 0.5   # seconds
MODEL_CACHE    = os.path.join(os.path.dirname(__file__), "models", "roberta-sentiment")
MODEL_NAME     = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# ── Model loader ──────────────────────────────────────────────────────────────
_pipeline = None
_vader    = None


def load_models():
    global _pipeline, _vader

    # Load VADER (always — used as fallback)
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
        log.info("VADER loaded")
    except ImportError:
        log.warning("vaderSentiment not installed — no fallback available")

    # Load RoBERTa
    try:
        from transformers import pipeline as hf_pipeline
        os.makedirs(MODEL_CACHE, exist_ok=True)
        log.info("Loading RoBERTa sentiment model...", model=MODEL_NAME)
        _pipeline = hf_pipeline(
            "sentiment-analysis",
            model=MODEL_NAME,
            tokenizer=MODEL_NAME,
            model_kwargs={"cache_dir": MODEL_CACHE},
            device=-1,          # CPU
            truncation=True,
            max_length=512,
        )
        log.info("RoBERTa sentiment model loaded")
    except Exception as e:
        log.warning("RoBERTa failed to load, will use VADER only", error=str(e))
        _pipeline = None


# ── Inference ─────────────────────────────────────────────────────────────────
LABEL_MAP = {
    # cardiffnlp model labels
    "positive": "positive",
    "negative": "negative",
    "neutral":  "neutral",
    "label_0":  "negative",
    "label_1":  "neutral",
    "label_2":  "positive",
}


def classify_roberta(texts: list[str]) -> list[dict]:
    results = _pipeline(texts, batch_size=32)
    output  = []
    for r in results:
        label = LABEL_MAP.get(r["label"].lower(), "neutral")
        score = r["score"]
        # Convert to -1.0 to 1.0 scale
        if label == "positive":
            sentiment_score = score
        elif label == "negative":
            sentiment_score = -score
        else:
            sentiment_score = 0.0
        output.append({
            "label": label,
            "score": round(sentiment_score, 4),
            "confidence": round(score, 4),
            "model": "roberta",
        })
    return output


def classify_vader(text: str) -> dict:
    scores = _vader.polarity_scores(text)
    compound = scores["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return {
        "label": label,
        "score": round(compound, 4),
        "confidence": round(abs(compound), 4),
        "model": "vader",
    }


def classify_batch(texts: list[str]) -> list[dict]:
    results = []
    roberta_indices = []
    vader_results   = {}

    for i, text in enumerate(texts):
        token_count = len(text.split())
        if token_count < 20 or _pipeline is None:
            vader_results[i] = classify_vader(text)
        else:
            roberta_indices.append(i)

    if roberta_indices and _pipeline:
        roberta_texts   = [texts[i] for i in roberta_indices]
        roberta_outputs = classify_roberta(roberta_texts)
        for idx, output in zip(roberta_indices, roberta_outputs):
            vader_results[idx] = output

    for i in range(len(texts)):
        results.append(vader_results.get(i, {"label": "neutral", "score": 0.0, "confidence": 0.0, "model": "fallback"}))

    return results


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting sentiment worker")
    load_models()

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=BATCH_SIZE,
        session_timeout_ms=60000,
        heartbeat_interval_ms=15000,
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
    log.info("Sentiment worker ready")

    batch        = []
    last_flush   = time.monotonic()

    async def flush_batch(batch):
        if not batch:
            return
        texts   = [m["normalized_content"]["text_cleaned"] for m in batch]
        results = classify_batch(texts)

        for message, sentiment in zip(batch, results):
            message_id = message.get("message_id", "unknown")
            tenant_id  = message.get("tenant_id", "unknown")
            try:
                enriched = {
                    **message,
                    "sentiment": sentiment["label"],
                    "sentiment_score": sentiment["score"],
                    "sentiment_confidence": sentiment["confidence"],
                    "sentiment_model": sentiment["model"],
                    "sentiment_classified_at": datetime.now(timezone.utc).isoformat(),
                }
                await producer.send_and_wait(
                    TOPIC_OUT,
                    value=enriched,
                    key=tenant_id,
                    headers=[
                        ("tenant_id", tenant_id.encode()),
                        ("schema_version", b"1.0"),
                    ],
                )
                await consumer.commit()
                log.info(
                    "Sentiment classified",
                    message_id=message_id,
                    sentiment=sentiment["label"],
                    score=sentiment["score"],
                    model=sentiment["model"],
                )
            except Exception as e:
                log.error("Failed to publish sentiment", message_id=message_id, error=str(e))
                await producer.send_and_wait(
                    TOPIC_DLQ,
                    value={**message, "dlq_reason": str(e), "dlq_stage": "sentiment", "dlq_at": datetime.now(timezone.utc).isoformat()},
                    key=tenant_id,
                )
                await consumer.commit()

    try:
        async for msg in consumer:
            batch.append(msg.value)
            elapsed = time.monotonic() - last_flush

            if len(batch) >= BATCH_SIZE or elapsed >= FLUSH_INTERVAL:
                await flush_batch(batch)
                batch      = []
                last_flush = time.monotonic()

    finally:
        await flush_batch(batch)
        await consumer.stop()
        await producer.stop()
        log.info("Sentiment worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
