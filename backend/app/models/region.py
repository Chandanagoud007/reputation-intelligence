"""
Region model — third level of hierarchy.
Tenant → Brand → Region → Location
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.location import Location


class Region(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "regions"
    __table_args__ = {"schema": "tenant_mgmt"}

    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), default="US", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="regions")
    locations: Mapped[list["Location"]] = relationship("Location", back_populates="region", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Region {self.name}>"
