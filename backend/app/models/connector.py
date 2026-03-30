"""
Connector model — stores OAuth credentials for review platforms.
Includes encrypted token vaulting.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.location import Location


class Connector(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "connectors"
    __table_args__ = {"schema": "tenant_mgmt"}

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # google | yelp | tripadvisor | facebook
    external_id: Mapped[str] = mapped_column(String(255), nullable=True)  # platform business ID
    encrypted_credentials: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False
    )  # AES-encrypted OAuth tokens
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending | active | error | paused
    sync_error: Mapped[str] = mapped_column(String(500), nullable=True)
    sync_frequency_minutes: Mapped[int] = mapped_column(default=60, nullable=False)

    # Relationships
    location: Mapped["Location"] = relationship("Location", back_populates="connectors")

    def __repr__(self):
        return f"<Connector {self.platform} - {self.location_id}>"
