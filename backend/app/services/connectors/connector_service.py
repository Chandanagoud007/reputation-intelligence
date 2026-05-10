"""
Connector Service
Manages platform connector credentials using the token vault.
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.token_vault import store_oauth_tokens, retrieve_oauth_tokens
from app.models.brand import Brand
from app.models.connector import Connector
from app.models.location import Location
from app.models.region import Region


class ConnectorService:
    """Service for managing platform connectors with encrypted credentials."""

    async def get_tenant_location(
        self,
        db: AsyncSession,
        location_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Location | None:
        """Return a location only when it belongs to the current tenant."""
        result = await db.execute(
            select(Location)
            .join(Region, Location.region_id == Region.id)
            .join(Brand, Region.brand_id == Brand.id)
            .where(Location.id == location_id, Brand.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_connectors(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        platform: str | None = None,
    ) -> list[Connector]:
        """List connectors scoped to the current tenant."""
        stmt = (
            select(Connector)
            .join(Location, Connector.location_id == Location.id)
            .join(Region, Location.region_id == Region.id)
            .join(Brand, Region.brand_id == Brand.id)
            .where(Brand.tenant_id == tenant_id)
            .order_by(Connector.created_at.desc())
        )
        if location_id:
            stmt = stmt.where(Connector.location_id == location_id)
        if platform:
            stmt = stmt.where(Connector.platform == platform)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_connector(
        self,
        db: AsyncSession,
        connector_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Connector | None:
        """Return a connector only when it belongs to the current tenant."""
        result = await db.execute(
            select(Connector)
            .join(Location, Connector.location_id == Location.id)
            .join(Region, Location.region_id == Region.id)
            .join(Brand, Region.brand_id == Brand.id)
            .where(Connector.id == connector_id, Brand.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def create_connector(
        self,
        db: AsyncSession,
        location_id: uuid.UUID,
        platform: str,
        external_id: str,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: int | None = None,
        scope: str | None = None,
    ) -> Connector:
        """Create a new connector with encrypted OAuth credentials."""

        # Encrypt tokens before storing
        encrypted_creds = store_oauth_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
        )

        connector = Connector(
            location_id=location_id,
            platform=platform,
            external_id=external_id,
            encrypted_credentials=encrypted_creds,
            is_active=True,
            sync_status="pending",
        )
        db.add(connector)
        await db.commit()
        await db.refresh(connector)
        return connector

    async def update_connector_status(
        self,
        db: AsyncSession,
        connector: Connector,
        *,
        is_active: bool,
        sync_status: str,
    ) -> Connector:
        """Pause or resume a connector without touching stored credentials."""
        connector.is_active = is_active
        connector.sync_status = sync_status
        connector.sync_error = None

        await db.commit()
        await db.refresh(connector)
        return connector

    async def delete_connector(
        self,
        db: AsyncSession,
        connector: Connector,
    ) -> None:
        """Delete a connector and its encrypted credentials."""
        await db.delete(connector)
        await db.commit()

    async def get_connector_tokens(
        self,
        db: AsyncSession,
        connector_id: uuid.UUID,
    ) -> dict:
        """Retrieve and decrypt OAuth tokens for a connector."""
        result = await db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        return retrieve_oauth_tokens(connector.encrypted_credentials)

    async def update_tokens(
        self,
        db: AsyncSession,
        connector_id: uuid.UUID,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: int | None = None,
    ) -> Connector:
        """Update OAuth tokens for an existing connector."""
        result = await db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        # Get existing credentials and update tokens
        existing = retrieve_oauth_tokens(connector.encrypted_credentials)
        existing.update({
            "access_token": access_token,
            "refresh_token": refresh_token or existing.get("refresh_token"),
            "expires_at": expires_at or existing.get("expires_at"),
        })

        from app.core.token_vault import encrypt_token
        connector.encrypted_credentials = encrypt_token(existing)
        connector.last_synced = datetime.utcnow()

        await db.commit()
        await db.refresh(connector)
        return connector


connector_service = ConnectorService()
