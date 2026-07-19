"""
Dashboard endpoints — reads from Phase 2 Kafka pipeline outputs.
Serves the React dashboard with scores, reviews, and alerts.
"""
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_tenant_id

router = APIRouter()

OPENSEARCH_URL = "http://localhost:9200"


# ── Scores ────────────────────────────────────────────────────────────────────
@router.get("/scores")
async def get_scores(
    location_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Current reputation scores per location for this tenant."""
    query = """
        SELECT
            rs.location_id, l.name as location_name,
            rs.brand_id, b.name as brand_name,
            rs.score, rs.rating_avg, rs.sentiment_avg, rs.review_count,
            rs.positive_count, rs.negative_count, rs.neutral_count,
            rs.updated_at
        FROM analytics.reputation_scores rs
        JOIN tenant_mgmt.locations l ON rs.location_id = l.id
        JOIN tenant_mgmt.brands b ON rs.brand_id = b.id
        WHERE rs.tenant_id = :tenant_id AND rs.scope = 'location'
    """
    params = {"tenant_id": str(tenant_id)}
    if location_id:
        query += " AND rs.location_id = :location_id"
        params["location_id"] = str(location_id)
    query += " ORDER BY rs.updated_at DESC"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return {
        "scores": [
            {
                "location_id":    str(r.location_id),
                "location_name":  r.location_name,
                "brand_id":       str(r.brand_id),
                "brand_name":     r.brand_name,
                "score":          round(r.score, 2),
                "rating_avg":     round(r.rating_avg, 2),
                "sentiment_avg":  round(r.sentiment_avg, 3),
                "review_count":   r.review_count,
                "positive_count": r.positive_count,
                "negative_count": r.negative_count,
                "neutral_count":  r.neutral_count,
                "updated_at":     r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    }


# ── Score history (ClickHouse) ───────────────────────────────────────────────
@router.get("/scores/history")
async def get_score_history(
    location_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Score trend over time for a location, from ClickHouse."""
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(
            host="localhost", port=8123,
            username="rip_user", password="rip_pass",
            database="rip_analytics",
        )
        result = client.query(f"""
            SELECT score, review_count, sentiment_avg, calculated_at
            FROM reputation_scores
            WHERE tenant_id = '{tenant_id}' AND location_id = '{location_id}'
              AND calculated_at >= now() - INTERVAL {days} DAY
            ORDER BY calculated_at ASC
        """)
        return {
            "history": [
                {
                    "score":         row[0],
                    "review_count":  row[1],
                    "sentiment_avg": row[2],
                    "calculated_at": row[3].isoformat(),
                }
                for row in result.result_rows
            ]
        }
    except Exception as e:
        return {"history": [], "error": str(e)}


# ── Reviews (OpenSearch) ──────────────────────────────────────────────────────
@router.get("/reviews")
async def get_reviews(
    location_id: uuid.UUID | None = None,
    sentiment: str | None = None,
    risk_level: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Review feed from OpenSearch, with full-text search and filters."""
    index = f"rip_{str(tenant_id).replace('-', '')}_reviews"

    must_clauses = []
    if search:
        must_clauses.append({"match": {"text_cleaned": search}})
    if location_id:
        must_clauses.append({"term": {"location_id": str(location_id)}})
    if sentiment:
        must_clauses.append({"term": {"sentiment": sentiment}})
    if risk_level:
        must_clauses.append({"term": {"risk_level": risk_level}})

    query_body = {
        "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
        "sort": [{"review_date": {"order": "desc"}}],
        "from": (page - 1) * page_size,
        "size": page_size,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{OPENSEARCH_URL}/{index}/_search", json=query_body)
            if response.status_code == 404:
                return {"reviews": [], "total": 0}
            data = response.json()

        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {}).get("value", 0)

        return {
            "reviews": [hit["_source"] for hit in hits],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        return {"reviews": [], "total": 0, "error": str(e)}


# ── Semantic search (Qdrant) ─────────────────────────────────────────────────
@router.get("/reviews/semantic-search")
async def semantic_search_reviews(
    query: str,
    limit: int = Query(default=10, ge=1, le=50),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Semantic search using vector similarity in Qdrant."""
    try:
        from qdrant_client import QdrantClient
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        vector = model.encode(query, normalize_embeddings=True).tolist()

        qdrant = QdrantClient(host="localhost", port=6333)
        collection = f"reviews_{str(tenant_id).replace('-', '_')}"

        results = qdrant.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
        )

        return {
            "results": [
                {
                    "score": r.score,
                    **r.payload,
                }
                for r in results
            ]
        }
    except Exception as e:
        return {"results": [], "error": str(e)}


# ── Alerts ────────────────────────────────────────────────────────────────────
@router.get("/alerts/inbox")
async def get_alert_inbox(
    severity: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Recent alerts from ClickHouse alert_events."""
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(
            host="localhost", port=8123,
            username="rip_user", password="rip_pass",
            database="rip_analytics",
        )
        query = f"""
            SELECT alert_id, rule_name, location_name, severity,
                   risk_level, risk_flags, score, fired_at
            FROM alert_events
            WHERE tenant_id = '{tenant_id}'
        """
        if severity:
            query += f" AND severity = '{severity}'"
        query += f" ORDER BY fired_at DESC LIMIT {limit}"

        result = client.query(query)
        return {
            "alerts": [
                {
                    "alert_id":     row[0],
                    "rule_name":    row[1],
                    "location_name": row[2],
                    "severity":     row[3],
                    "risk_level":   row[4],
                    "risk_flags":   row[5],
                    "score":        row[6],
                    "fired_at":     row[7].isoformat(),
                }
                for row in result.result_rows
            ]
        }
    except Exception as e:
        return {"alerts": [], "error": str(e)}


# ── Topic & sentiment breakdown ───────────────────────────────────────────────
@router.get("/insights/topics")
async def get_topic_breakdown(
    location_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Topic frequency breakdown from ClickHouse review_events."""
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(
            host="localhost", port=8123,
            username="rip_user", password="rip_pass",
            database="rip_analytics",
        )
        query = f"""
            SELECT topic, count(*) as cnt
            FROM (
                SELECT arrayJoin(topics) as topic
                FROM review_events
                WHERE tenant_id = '{tenant_id}'
                  AND ingested_at >= now() - INTERVAL {days} DAY
                {"AND location_id = '" + str(location_id) + "'" if location_id else ""}
            )
            GROUP BY topic
            ORDER BY cnt DESC
        """
        result = client.query(query)
        return {
            "topics": [{"topic": row[0], "count": row[1]} for row in result.result_rows]
        }
    except Exception as e:
        return {"topics": [], "error": str(e)}
