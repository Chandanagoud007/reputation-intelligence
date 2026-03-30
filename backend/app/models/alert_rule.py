"""
Alert rule model — configures when and how alerts are triggered.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin


class AlertRule(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "alert_rules"
    __table_args__ = {"schema": "alerts"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    conditions: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # e.g. {"rating_lte": 2, "sentiment": "negative"}
    channels: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # e.g. {"email": ["a@b.com"], "sms": ["+1..."], "slack": "webhook_url"}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(default=60, nullable=False)

    def __repr__(self):
        return f"<AlertRule {self.name}>"
