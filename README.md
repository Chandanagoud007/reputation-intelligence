# Reputation Intelligence Platform

An event-driven, multi-tenant SaaS system that collects customer reviews from across the internet, processes them through an AI pipeline, and delivers live reputation scores, risk alerts, and semantic search through a React dashboard.

---

## What it does

- Ingests reviews from App Store, Google Play, YouTube, Twitter, Instagram, Facebook, LinkedIn, Trustpilot, Glassdoor, and more
- Runs every review through normalization, deduplication, sentiment analysis (RoBERTa), topic classification, and risk detection
- Computes reputation scores per location, updated in real time as reviews flow in
- Fires configurable alerts when scores drop or risk events are detected
- Semantic search — find reviews by meaning, not just keywords (powered by Qdrant)

---

## Architecture

```
Connectors → Ingestion Gateway → Kafka → Normalize → Dedup → Entity Resolve
→ [Sentiment | Topic | Risk] → Merge → Scoring → Alerts → Dispatch
                                      ↓           ↓
                               OpenSearch      ClickHouse
                               Qdrant          PostgreSQL
                               MinIO
```

Every stage is an independent worker. No service talks directly to another — everything flows through Kafka.

---

## Tech stack

| Layer | Technology |
|---|---|
| Message backbone | Apache Kafka |
| API | FastAPI + JWT + RBAC |
| Relational DB | PostgreSQL |
| Analytics | ClickHouse |
| Full-text search | OpenSearch |
| Semantic search | Qdrant |
| Cache / dedup | Redis |
| Raw archive | MinIO |
| Sentiment | RoBERTa + VADER |
| Summarization | Claude API |
| Frontend | React + Tailwind CSS |
| Infrastructure | Docker Compose |

---

## Prerequisites

- Docker Desktop
- Python 3.11+
- Node.js 20+

---

## Quickstart

### 1. Start infrastructure

```bash
cd infrastructure/local
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
# or: source .venv/bin/activate                  # Mac/Linux

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values (DB, Redis, Kafka URLs are pre-configured for Docker Compose).

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Workers

On Windows, double-click `start_workers.bat`. On Mac/Linux run each worker in a separate terminal:

```bash
python -m app.services.workers.normalize_worker
python -m app.services.workers.dedup_worker
python -m app.services.workers.entity_resolve_worker
python -m app.services.workers.sentiment_worker
python -m app.services.workers.topic_worker
python -m app.services.workers.risk_worker
python -m app.services.workers.merge_worker
python -m app.services.workers.scoring_engine
python -m app.services.workers.alert_engine
python -m app.services.workers.search_indexer
python -m app.services.workers.vector_indexer
python -m app.services.workers.analytics_writer
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**

---

## Loading review data

```bash
python -m app.scripts.bulk_loader --file reviews.json --brand "Brand Name" --rate 50
```

Supports: App Store, Google Play, YouTube, Twitter, Instagram, Facebook, LinkedIn.

---

## Service URLs

| Service | URL |
|---|---|
| Dashboard | http://127.0.0.1:5173 |
| API docs | http://127.0.0.1:8000/api/docs |
| Kafka UI | http://localhost:8080 |
| Qdrant UI | http://localhost:6333/dashboard |
| MinIO Console | http://localhost:9001 |
| OpenSearch | http://localhost:5601 |
