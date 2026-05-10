"""Review query endpoints."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import get_tenant_id
from app.services.ingestion.review_store import review_store

router = APIRouter()


class ReviewListResponse(BaseModel):
    reviews: list[dict[str, Any]]


@router.get("/", response_model=ReviewListResponse)
async def list_reviews(
    location_id: uuid.UUID | None = None,
    platform: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """List normalized reviews stored in MongoDB for the current tenant."""
    reviews = await review_store.list_reviews(
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
        limit=limit,
    )
    return ReviewListResponse(reviews=[_json_safe(review) for review in reviews])


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


from fastapi.responses import Response
from app.services.analytics.excel_export_service import excel_export_service


@router.get("/export/excel")
async def export_reviews_excel(
    location_id: uuid.UUID | None = None,
    platform: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Download reviews as a formatted Excel report."""
    excel_bytes = await excel_export_service.generate_report(
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
        days=days,
    )
    filename = f"reputation_report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
