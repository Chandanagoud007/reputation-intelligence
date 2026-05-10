"""
Location model — bottom level of hierarchy.
Tenant → Brand → Region → Location
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.region import Region
    from app.models.connector import Connector


class Location(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "locations"
    __table_args__ = {"schema": "tenant_mgmt"}

    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.regions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="US", nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=True)
    website: Mapped[str] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relationships
    region: Mapped["Region"] = relationship("Region", back_populates="locations")
    connectors: Mapped[list["Connector"]] = relationship("Connector", back_populates="location", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Location {self.name}>"
