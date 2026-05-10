"""Analytics endpoints."""
import uuid
from fastapi import APIRouter, Depends, Query
from app.core.deps import get_tenant_id
from app.services.analytics.analytics_service import analytics_service
from app.services.analytics.anomaly_service import anomaly_service
from app.services.analytics.prescriptive_service import prescriptive_service

router = APIRouter()


@router.get("/summary")
async def get_summary(
    location_id: uuid.UUID | None = None,
    platform: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Overall rating and sentiment summary."""
    return await analytics_service.get_summary(
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
        days=days,
    )


@router.get("/trends")
async def get_trends(
    location_id: uuid.UUID | None = None,
    platform: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Rating and sentiment trends over time."""
    return await analytics_service.get_trends(
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
        days=days,
        group_by=group_by,
    )


@router.get("/platforms")
async def get_platform_breakdown(
    location_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Performance breakdown by platform."""
    return await analytics_service.get_platform_breakdown(
        tenant_id=tenant_id,
        location_id=location_id,
        days=days,
    )


@router.get("/anomalies")
async def get_anomalies(
    location_id: uuid.UUID | None = None,
    platform: str | None = None,
    window_days: int = Query(default=7, ge=1, le=30),
    threshold: float = Query(default=0.8, ge=0.1, le=1.0),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Detect rating drops and negative review spikes."""
    rating_drops = await anomaly_service.detect_rating_drop(
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
        window_days=window_days,
        threshold=threshold,
    )
    negative_spikes = await anomaly_service.detect_negative_spike(
        tenant_id=tenant_id,
        location_id=location_id,
        window_days=window_days,
    )
    return {
        "rating_drops": rating_drops,
        "negative_spikes": negative_spikes,
        "total_anomalies": len(rating_drops) + len(negative_spikes),
    }


@router.get("/prescriptive")
async def get_prescriptive(
    location_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """What to improve this month + what is working well."""
    improvements = await prescriptive_service.get_improvement_areas(
        tenant_id=tenant_id,
        location_id=location_id,
        days=days,
    )
    strengths = await prescriptive_service.get_winning_areas(
        tenant_id=tenant_id,
        location_id=location_id,
        days=days,
    )
    return {
        "improvements": improvements,
        "strengths": strengths,
    }
