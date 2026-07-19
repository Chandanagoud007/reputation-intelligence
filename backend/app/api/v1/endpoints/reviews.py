"""Review query endpoints."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from opensearchpy import AsyncOpenSearch
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from app.core.deps import get_tenant_id
from app.services.ingestion.review_store import review_store

router = APIRouter()


# ── Search client singletons ─────────────────────────────────────────────────
_os_client = None
_qdrant_client = None
_embed_model = None


def get_os_client():
    global _os_client
    if _os_client is None:
        _os_client = AsyncOpenSearch(
            hosts=[{"host": "localhost", "port": 9200}],
            http_compress=True, use_ssl=False, verify_certs=False, ssl_show_warn=False,
        )
    return _os_client


def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(host="localhost", port=6333)
    return _qdrant_client


def get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def _index_name(tenant_id) -> str:
    return f"rip_{str(tenant_id).replace('-', '')}_reviews"


def _collection_name(tenant_id) -> str:
    return f"reviews_{str(tenant_id).replace('-', '_')}"


class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 20


class ReviewListResponse(BaseModel):
    reviews: list[dict[str, Any]]


# ── Phase 1: MongoDB-backed list (kept for backward compatibility) ───────────
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


# ── Phase 2: OpenSearch full-text + faceted search ────────────────────────────
@router.get("/search")
async def search_reviews(
    query: str | None = None,
    sentiment: str | None = None,
    platform: str | None = None,
    risk_level: str | None = None,
    size: int = Query(default=50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """
    Full-text + faceted search over OpenSearch.
    Powers the dashboard's review feed with filters.
    """
    client = get_os_client()
    index  = _index_name(tenant_id)

    must_clauses = []
    if query:
        must_clauses.append({"match": {"text_cleaned": query}})
    if sentiment:
        must_clauses.append({"term": {"sentiment": sentiment}})
    if platform:
        must_clauses.append({"term": {"source_platform": platform}})
    if risk_level:
        must_clauses.append({"term": {"risk_level": risk_level}})

    body = {
        "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
        "sort": [{"review_date": {"order": "desc"}}],
        "size": size,
    }

    try:
        result = await client.search(index=index, body=body)
    except Exception:
        return []

    hits = result.get("hits", {}).get("hits", [])
    return [hit["_source"] for hit in hits]


# ── Phase 2: Qdrant semantic search ───────────────────────────────────────────
@router.post("/semantic-search")
async def semantic_search_reviews(
    payload: SemanticSearchRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """
    Semantic search via Qdrant — finds reviews by meaning, not exact keywords.
    e.g. "complaints about hygiene" matches reviews mentioning cockroaches,
    dirty tables, etc. even without the word "hygiene".
    """
    qdrant = get_qdrant_client()
    model  = get_embed_model()
    collection = _collection_name(tenant_id)

    try:
        existing = [c.name for c in qdrant.get_collections().collections]
        if collection not in existing:
            return []

        vector = model.encode(payload.query, normalize_embeddings=True).tolist()
        results = qdrant.search(
            collection_name=collection,
            query_vector=vector,
            limit=payload.limit,
        )
        return [
            {
                "message_id":       r.payload.get("message_id"),
                "text_cleaned":     r.payload.get("text_cleaned"),
                "rating":           r.payload.get("rating"),
                "sentiment":        r.payload.get("sentiment"),
                "sentiment_score":  r.payload.get("sentiment_score"),
                "topics":           r.payload.get("topics", []),
                "risk_level":       r.payload.get("risk_level", "NONE"),
                "risk_flags":       r.payload.get("risk_flags", []),
                "source_platform":  r.payload.get("source_platform"),
                "location_name":    r.payload.get("location_name"),
                "brand_name":       r.payload.get("brand_name"),
                "review_date":      r.payload.get("review_date"),
                "reviewer_name":    None,
                "similarity_score": round(r.score, 4),
            }
            for r in results
        ]
    except Exception:
        return []


# ── Phase 1: Excel export (unchanged) ─────────────────────────────────────────
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

@router.get("/topics")
async def get_topic_breakdown(
    location_id: str | None = None,
    size: int = Query(default=200, ge=1, le=1000),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """
    Returns topic mention counts aggregated from OpenSearch.
    Powers the Topics Mentioned chart on the dashboard.
    """
    client = get_os_client()
    index  = _index_name(tenant_id)

    filter_clauses = []
    if location_id:
        filter_clauses.append({"term": {"location_id": location_id}})

    body = {
        "size": 0,
        "query": {"bool": {"filter": filter_clauses}} if filter_clauses else {"match_all": {}},
        "aggs": {
            "topics": {
                "terms": {
                    "field": "topics",
                    "size": size,
                    "min_doc_count": 5,
                    "order": {"_count": "desc"},
                }
            }
        }
    }

    try:
        result = await client.search(index=index, body=body)
        buckets = result.get("aggregations", {}).get("topics", {}).get("buckets", [])
        return [{"topic": b["key"], "count": b["doc_count"]} for b in buckets]
    except Exception:
        return []