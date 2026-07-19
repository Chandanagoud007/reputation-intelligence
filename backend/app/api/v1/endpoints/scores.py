"""
Scores endpoint — reads current reputation scores from PostgreSQL.
New file: app/api/v1/endpoints/scores.py
"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_tenant_id

router = APIRouter()


@router.get("/")
async def list_scores(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Current reputation score per location for the tenant.
    Powers the dashboard's location score cards.
    """
    result = await db.execute(
        text("""
            SELECT
                rs.location_id,
                l.name AS location_name,
                b.name AS brand_name,
                r.name AS region_name,
                rs.score,
                rs.rating_avg,
                rs.sentiment_avg,
                rs.review_count,
                rs.positive_count,
                rs.negative_count,
                rs.neutral_count
            FROM analytics.reputation_scores rs
            JOIN tenant_mgmt.locations l ON rs.location_id = l.id
            JOIN tenant_mgmt.regions r ON l.region_id = r.id
            JOIN tenant_mgmt.brands b ON r.brand_id = b.id
            WHERE rs.tenant_id = :tenant_id AND rs.scope = 'location'
            ORDER BY rs.score ASC
        """),
        {"tenant_id": str(tenant_id)},
    )
    rows = result.fetchall()

    return [
        {
            "location_id":    str(row.location_id),
            "location_name":  row.location_name,
            "brand_name":     row.brand_name,
            "region_name":    row.region_name,
            "score":          round(row.score, 2),
            "rating_avg":     round(row.rating_avg, 2),
            "sentiment_avg":  round(row.sentiment_avg, 3),
            "review_count":   row.review_count,
            "positive_count": row.positive_count,
            "negative_count": row.negative_count,
            "neutral_count":  row.neutral_count,
        }
        for row in rows
    ]
