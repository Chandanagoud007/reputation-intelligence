"""
Reputation Intelligence Platform — API v1 Router
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    tenants,
    locations,
    reviews,
    analytics,
    alerts,
    connectors,
    insights,
    users,
    health,
)

api_router = APIRouter()

# ─── System ───────────────────────────────────────────────────────
api_router.include_router(health.router,      prefix="/health",     tags=["Health"])

# ─── Auth ─────────────────────────────────────────────────────────
api_router.include_router(auth.router,        prefix="/auth",       tags=["Authentication"])

# ─── Multi-tenant Management ──────────────────────────────────────
api_router.include_router(tenants.router,     prefix="/tenants",    tags=["Tenants"])
api_router.include_router(users.router,       prefix="/users",      tags=["Users"])
api_router.include_router(locations.router,   prefix="/locations",  tags=["Locations"])

# ─── Review Ingestion ─────────────────────────────────────────────
api_router.include_router(connectors.router,  prefix="/connectors", tags=["Platform Connectors"])
api_router.include_router(reviews.router,     prefix="/reviews",    tags=["Reviews"])

# ─── Intelligence & Analytics ─────────────────────────────────────
api_router.include_router(analytics.router,   prefix="/analytics",  tags=["Analytics"])
api_router.include_router(insights.router,    prefix="/insights",   tags=["AI Insights"])

# ─── Alerts ───────────────────────────────────────────────────────
api_router.include_router(alerts.router,      prefix="/alerts",     tags=["Alerts"])
