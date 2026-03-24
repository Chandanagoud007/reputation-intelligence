# Reputation Intelligence Platform

AI-powered, multi-tenant SaaS platform for ingesting, analyzing, and transforming customer reviews into actionable business intelligence.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12 + FastAPI |
| Relational DB | PostgreSQL 15 (tenants, users, locations) |
| Document DB | MongoDB 7 (reviews, analytics) |
| Cache / Sessions | Redis 7 |
| Message Queue | RabbitMQ 3.13 |
| AI / Sentiment | AWS Comprehend · Anthropic Claude · VADER (fallback) |
| Frontend | React 18 + Vite + TypeScript + Tailwind |
| Monitoring | Prometheus + Grafana + Sentry |
| Cloud | AWS (ECS/EKS, S3, SES, Comprehend) |

---

## Quick Start

### Prerequisites
- Docker Desktop (with Compose v2)
- Python 3.12+
- Node.js 20+

### 1. Clone & configure
```bash
git clone <repo-url>
cd reputation-intelligence
cp .env.example .env
# Edit .env and fill in your secrets
```

### 2. One-command setup
```bash
chmod +x infrastructure/scripts/setup_dev.sh
bash infrastructure/scripts/setup_dev.sh
```

### 3. Start everything
```bash
docker compose up
```

---

## Service URLs (local)

| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/api/docs |
| Frontend | http://localhost:3000 |
| RabbitMQ Management | http://localhost:15672 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

---

## Project Structure

```
reputation-intelligence/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/v1/           # Route handlers
│   │   ├── core/             # Config, database connections
│   │   ├── middleware/        # Tenant isolation, logging
│   │   ├── models/           # SQLAlchemy models (PG)
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── connectors/   # Google, Yelp, TripAdvisor ingestion
│   │   │   ├── nlp/          # Sentiment, emotion, topic analysis
│   │   │   └── analytics/    # Aggregation and metrics
│   │   └── utils/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 # React + Vite SPA
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── store/            # Redux slices
│   │   └── services/         # API client
│   └── Dockerfile
├── infrastructure/
│   ├── docker/               # Service init configs
│   ├── scripts/              # Dev setup scripts
│   ├── k8s/                  # Kubernetes manifests
│   └── terraform/            # AWS IaC
├── ml/                       # ML model training & inference
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Development Workflow

```bash
# Backend (with hot reload)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Frontend (with hot reload)
cd frontend
npm run dev

# Run tests
cd backend && pytest
cd frontend && npm test

# DB migrations
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## Phase Roadmap

| Phase | Focus 
|---|---|---|
| 1 | Foundation & Architecture 
| 2 | Platform Connectivity & Ingestion
| 3 | Intelligence & Analytics Layer
| 4 | Dashboards, Alerts & RBAC
| 5 | Stabilization, Reporting & Launch
