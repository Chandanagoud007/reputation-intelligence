"""Health check endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check():
    return {"status": "ok", "service": "reputation-intelligence-api"}


@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}
