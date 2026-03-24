#!/usr/bin/env bash
# ================================================================
# Reputation Intelligence Platform — Developer Environment Setup
# Run once after cloning: bash scripts/setup_dev.sh
# ================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

info "=== Reputation Intelligence Platform — Dev Setup ==="

# ─── Prerequisites check ─────────────────────────────────────────
command -v docker        >/dev/null 2>&1 || error "Docker not found. Install from https://docs.docker.com/get-docker/"
command -v docker        >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || error "Docker Compose v2 not found."
command -v python3       >/dev/null 2>&1 || error "Python 3.12+ required"
command -v node          >/dev/null 2>&1 || error "Node.js 20+ required"
command -v git           >/dev/null 2>&1 || error "Git required"

info "All prerequisites found ✓"

# ─── Environment file ─────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — PLEASE update secrets before running!"
else
    info ".env already exists — skipping"
fi

# ─── Python virtual environment ───────────────────────────────────
if [ ! -d "backend/.venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv backend/.venv
fi

info "Installing Python dependencies..."
source backend/.venv/bin/activate
pip install --upgrade pip -q
pip install -r backend/requirements.txt -q
info "Python deps installed ✓"

# Download NLP models
info "Downloading NLP models (NLTK + spaCy)..."
python3 -c "
import nltk
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('vader_lexicon', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
print('NLTK models downloaded')
"
python3 -m spacy download en_core_web_sm -q 2>/dev/null || warn "spaCy model download failed — run manually: python -m spacy download en_core_web_sm"

# ─── Frontend dependencies ────────────────────────────────────────
info "Installing frontend dependencies..."
cd frontend && npm install -q && cd ..
info "Frontend deps installed ✓"

# ─── Docker infrastructure ────────────────────────────────────────
info "Starting Docker infrastructure (Postgres, Mongo, Redis, RabbitMQ)..."
docker compose up -d postgres mongo redis rabbitmq

info "Waiting for services to be healthy..."
sleep 5

# Poll until healthy
for service in postgres mongo redis rabbitmq; do
    for i in {1..30}; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' rep_${service} 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "healthy" ]; then
            info "${service} is healthy ✓"
            break
        fi
        if [ $i -eq 30 ]; then
            warn "${service} health check timed out — check docker logs rep_${service}"
        fi
        sleep 2
    done
done

# ─── Run DB migrations ────────────────────────────────────────────
info "Running database migrations..."
cd backend
source .venv/bin/activate 2>/dev/null || source backend/.venv/bin/activate 2>/dev/null || true
# alembic upgrade head  # Uncomment once alembic is configured
cd ..

info ""
info "================================================================"
info "  Setup complete! Here's how to run the platform:"
info ""
info "  All services:      docker compose up"
info "  Backend only:      cd backend && uvicorn app.main:app --reload"
info "  Frontend only:     cd frontend && npm run dev"
info ""
info "  API docs:          http://localhost:8000/api/docs"
info "  Frontend:          http://localhost:3000"
info "  RabbitMQ UI:       http://localhost:15672"
info "  Grafana:           http://localhost:3001"
info "  Prometheus:        http://localhost:9090"
info "================================================================"
