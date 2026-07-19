"""
Reputation Score model — stores current score per location, region, brand.
Updated by the scoring engine every time a new review is classified.
"""
import uuid
from datetime import datetime
from sqlalchemy import Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimeStampMixin, UUIDMixin


class ReputationScore(Base, UUIDMixin, TimeStampMixin):
    __tablename__ = "reputation_scores"
    __table_args__ = {"schema": "analytics"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.regions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_mgmt.locations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Score components
    score: Mapped[float] = mapped_column(Float, nullable=False)           # 0.0 to 5.0
    rating_avg: Mapped[float] = mapped_column(Float, nullable=False)      # avg raw rating
    sentiment_avg: Mapped[float] = mapped_column(Float, nullable=False)   # avg sentiment score
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)

    # Scope: location | region | brand
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="location")

    # Last review that triggered this score update
    last_review_id: Mapped[str] = mapped_column(String(255), nullable=True)
    last_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<ReputationScore {self.scope} score={self.score:.2f}>"
