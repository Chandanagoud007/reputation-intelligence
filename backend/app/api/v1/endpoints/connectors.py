"""Platform connector management endpoints."""
import uuid
from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_tenant_id
from app.models.connector import Connector
from app.services.connectors.connector_service import connector_service
from app.services.ingestion.sync_service import ingestion_sync_service

router = APIRouter()


class ConnectorPlatform(StrEnum):
    GOOGLE_BUSINESS = "google_business"
    PLAY_STORE = "play_store"
    TRUSTPILOT = "trustpilot"
    GLASSDOOR = "glassdoor"


class ConnectorCreateRequest(BaseModel):
    location_id: uuid.UUID
    platform: ConnectorPlatform
    external_id: str = Field(..., min_length=1, max_length=255)
    access_token: str = Field(..., min_length=1)
    refresh_token: str | None = None
    expires_at: int | None = None
    scope: str | None = None
    sync_frequency_minutes: int = Field(default=60, ge=5, le=1440)


class ConnectorResponse(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    platform: str
    external_id: str | None
    is_active: bool
    sync_status: str
    sync_error: str | None
    sync_frequency_minutes: int
    last_synced: datetime | None
    created_at: datetime
    updated_at: datetime


class EnqueueSyncResponse(BaseModel):
    queued: int


def _to_response(connector: Connector) -> ConnectorResponse:
    return ConnectorResponse(
        id=connector.id,
        location_id=connector.location_id,
        platform=connector.platform,
        external_id=connector.external_id,
        is_active=connector.is_active,
        sync_status=connector.sync_status,
        sync_error=connector.sync_error,
        sync_frequency_minutes=connector.sync_frequency_minutes,
        last_synced=connector.last_synced,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
    )


@router.get("/", response_model=list[ConnectorResponse])
async def list_connectors(
    location_id: uuid.UUID | None = None,
    platform: ConnectorPlatform | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List platform connectors for the current tenant."""
    connectors = await connector_service.list_connectors(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform.value if platform else None,
    )
    return [_to_response(connector) for connector in connectors]


@router.post("/", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ConnectorCreateRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a connector and store OAuth credentials in the encrypted vault."""
    location = await connector_service.get_tenant_location(
        db,
        location_id=payload.location_id,
        tenant_id=tenant_id,
    )
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found for tenant",
        )

    connector = await connector_service.create_connector(
        db,
        location_id=payload.location_id,
        platform=payload.platform.value,
        external_id=payload.external_id,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        expires_at=payload.expires_at,
        scope=payload.scope,
    )
    connector.sync_frequency_minutes = payload.sync_frequency_minutes
    await db.commit()
    await db.refresh(connector)
    return _to_response(connector)


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single connector for the current tenant."""
    connector = await connector_service.get_connector(db, connector_id, tenant_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    return _to_response(connector)


@router.post("/{connector_id}/pause", response_model=ConnectorResponse)
async def pause_connector(
    connector_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Pause incremental sync for a connector."""
    connector = await connector_service.get_connector(db, connector_id, tenant_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    connector = await connector_service.update_connector_status(
        db,
        connector,
        is_active=False,
        sync_status="paused",
    )
    return _to_response(connector)


@router.post("/{connector_id}/resume", response_model=ConnectorResponse)
async def resume_connector(
    connector_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Resume incremental sync for a connector."""
    connector = await connector_service.get_connector(db, connector_id, tenant_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    connector = await connector_service.update_connector_status(
        db,
        connector,
        is_active=True,
        sync_status="pending",
    )
    return _to_response(connector)


@router.post("/{connector_id}/sync", response_model=EnqueueSyncResponse)
async def enqueue_connector_sync(
    connector_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Queue an immediate sync job for one connector."""
    connector = await connector_service.get_connector(db, connector_id, tenant_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    if not connector.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connector is paused",
        )

    await ingestion_sync_service.enqueue_connector(connector, tenant_id)
    connector.sync_status = "queued"
    connector.sync_error = None
    await db.commit()
    return EnqueueSyncResponse(queued=1)


@router.post("/sync/due", response_model=EnqueueSyncResponse)
async def enqueue_due_connector_syncs(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Queue sync jobs for due connectors in the current tenant."""
    queued = await ingestion_sync_service.enqueue_due_connectors(db, tenant_id=tenant_id)
    return EnqueueSyncResponse(queued=queued)


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a connector and its stored credentials."""
    connector = await connector_service.get_connector(db, connector_id, tenant_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    await connector_service.delete_connector(db, connector)
