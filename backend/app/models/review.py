"""
MongoDB Review document schema.
Normalized review structure across all platforms.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReviewAuthor(BaseModel):
    name: str
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None


class ReviewSentiment(BaseModel):
    label: str  # positive | negative | neutral | mixed
    score: float  # -1.0 to 1.0
    positive_score: float
    negative_score: float
    neutral_score: float
    emotions: dict[str, float] = {}
    topics: list[str] = []
    provider: str  # aws_comprehend | anthropic | vader_local


class Review(BaseModel):
    """Normalized review document stored in MongoDB."""

    # Identity
    tenant_id: UUID
    location_id: UUID
    platform: str  # google | yelp | tripadvisor | facebook
    external_id: str  # platform's unique review ID

    # Review content
    rating: float  # 1.0 to 5.0
    title: Optional[str] = None
    content: str
    language: str = "en"
    author: ReviewAuthor

    # Owner response
    owner_reply: Optional[str] = None
    owner_reply_at: Optional[datetime] = None

    # Sentiment (populated after NLP processing)
    sentiment: Optional[ReviewSentiment] = None
    is_analyzed: bool = False

    # Metadata
    review_url: Optional[str] = None
    published_at: datetime
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {UUID: str, datetime: lambda v: v.isoformat()}


class ReviewCreate(BaseModel):
    """Used when ingesting a new review."""
    tenant_id: UUID
    location_id: UUID
    platform: str
    external_id: str
    rating: float
    title: Optional[str] = None
    content: str
    language: str = "en"
    author: ReviewAuthor
    published_at: datetime
    review_url: Optional[str] = None


class ReviewUpdate(BaseModel):
    """Used when updating an existing review."""
    owner_reply: Optional[str] = None
    owner_reply_at: Optional[datetime] = None
    sentiment: Optional[ReviewSentiment] = None
    is_analyzed: Optional[bool] = None
