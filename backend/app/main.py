"""
Reputation Intelligence Platform — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import init_postgres, init_mongo, init_redis, close_connections
from app.api.v1.router import api_router
from app.middleware.tenant import TenantMiddleware
from app.middleware.logging import LoggingMiddleware

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    log.info("Starting Reputation Intelligence Platform", version=settings.APP_VERSION)
    try:
        await init_postgres()
        log.info("PostgreSQL connected")
    except Exception as e:
        log.error("PostgreSQL connection failed", error=str(e))
        raise

    try:
        await init_mongo()
        log.info("MongoDB connected")
    except Exception as e:
        log.error("MongoDB connection failed", error=str(e))
        raise

    try:
        await init_redis()
        log.info("Redis connected")
    except Exception as e:
        log.error("Redis connection failed", error=str(e))
        raise

    log.info("All database connections established")
    yield
    await close_connections()
    log.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AI-powered reputation intelligence platform",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ─── Middleware (order matters — outermost first) ─────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TenantMiddleware)

    # ─── Routes ───────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ─── Prometheus Metrics ───────────────────────────────────────
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    
    # ─── Root health check (for ALB) ──────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
