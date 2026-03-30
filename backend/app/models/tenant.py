"""
Tenant model — top level of the multi-tenant hierarchy.
Tenant → Brand → Region → Location
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.user import User


class Tenant(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "tenant_mgmt"}

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(
        String(50), nullable=False, default="starter"
    )  # starter | pro | enterprise
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=True)
    max_locations: Mapped[int] = mapped_column(default=5, nullable=False)
    max_users: Mapped[int] = mapped_column(default=10, nullable=False)

    # Relationships
    brands: Mapped[list["Brand"]] = relationship("Brand", back_populates="tenant", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tenant {self.slug}>"
