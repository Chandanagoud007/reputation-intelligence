"""
Reputation Intelligence Platform — NLP Sentiment Service
Provider-agnostic: routes to AWS Comprehend, Anthropic Claude, or local VADER
based on SENTIMENT_PROVIDER env setting.
"""
from enum import Enum
from typing import Any

import boto3
import structlog
from anthropic import AsyncAnthropic
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.config import settings

log = structlog.get_logger()


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SentimentResult:
    def __init__(
        self,
        label: SentimentLabel,
        score: float,                   # -1.0 to 1.0
        positive_score: float,
        negative_score: float,
        neutral_score: float,
        emotions: dict[str, float],     # joy, anger, sadness, fear, surprise
        topics: list[str],
        provider: str,
    ):
        self.label = label
        self.score = score
        self.positive_score = positive_score
        self.negative_score = negative_score
        self.neutral_score = neutral_score
        self.emotions = emotions
        self.topics = topics
        self.provider = provider

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "scores": {
                "positive": self.positive_score,
                "negative": self.negative_score,
                "neutral": self.neutral_score,
            },
            "emotions": self.emotions,
            "topics": self.topics,
            "provider": self.provider,
        }


class SentimentService:
    """
    Unified sentiment analysis service.
    Wraps multiple providers behind a single interface.
    """

    def __init__(self):
        self.provider = settings.SENTIMENT_PROVIDER
        self._vader = SentimentIntensityAnalyzer()

        if self.provider == "aws_comprehend":
            self._comprehend = boto3.client(
                "comprehend",
                region_name=settings.AWS_COMPREHEND_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

        if self.provider == "anthropic":
            self._anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def analyze(self, text: str, language: str = "en") -> SentimentResult:
        """Analyze sentiment of a review text."""
        log.debug("Analyzing sentiment", provider=self.provider, text_len=len(text))

        try:
            match self.provider:
                case "aws_comprehend":
                    return await self._analyze_comprehend(text, language)
                case "anthropic":
                    return await self._analyze_anthropic(text)
                case _:
                    return self._analyze_vader(text)
        except Exception as e:
            log.warning("Primary provider failed, falling back to VADER", error=str(e))
            return self._analyze_vader(text)

    async def _analyze_comprehend(self, text: str, language: str) -> SentimentResult:
        """AWS Comprehend analysis."""
        response = self._comprehend.detect_sentiment(Text=text, LanguageCode=language)
        scores = response["SentimentScore"]
        label_map = {
            "POSITIVE": SentimentLabel.POSITIVE,
            "NEGATIVE": SentimentLabel.NEGATIVE,
            "NEUTRAL": SentimentLabel.NEUTRAL,
            "MIXED": SentimentLabel.MIXED,
        }
        label = label_map.get(response["Sentiment"], SentimentLabel.NEUTRAL)
        score = scores["Positive"] - scores["Negative"]

        return SentimentResult(
            label=label,
            score=round(score, 4),
            positive_score=round(scores["Positive"], 4),
            negative_score=round(scores["Negative"], 4),
            neutral_score=round(scores["Neutral"], 4),
            emotions={},  # Comprehend doesn't provide emotions by default
            topics=[],
            provider="aws_comprehend",
        )

    async def _analyze_anthropic(self, text: str) -> SentimentResult:
        """Claude-powered deep sentiment + emotion + topic extraction."""
        prompt = f"""Analyze the sentiment of this customer review. Return ONLY valid JSON.

Review: {text}

Return:
{{
  "label": "positive|negative|neutral|mixed",
  "score": <float -1.0 to 1.0>,
  "positive_score": <float 0.0 to 1.0>,
  "negative_score": <float 0.0 to 1.0>,
  "neutral_score": <float 0.0 to 1.0>,
  "emotions": {{"joy": 0.0, "anger": 0.0, "sadness": 0.0, "fear": 0.0, "surprise": 0.0}},
  "topics": ["topic1", "topic2"]
}}"""

        import json
        response = await self._anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text)
        return SentimentResult(
            label=SentimentLabel(data["label"]),
            score=data["score"],
            positive_score=data["positive_score"],
            negative_score=data["negative_score"],
            neutral_score=data["neutral_score"],
            emotions=data.get("emotions", {}),
            topics=data.get("topics", []),
            provider="anthropic",
        )

    def _analyze_vader(self, text: str) -> SentimentResult:
        """Local VADER fallback — no API calls needed."""
        scores = self._vader.polarity_scores(text)
        compound = scores["compound"]
        if compound >= 0.05:
            label = SentimentLabel.POSITIVE
        elif compound <= -0.05:
            label = SentimentLabel.NEGATIVE
        else:
            label = SentimentLabel.NEUTRAL

        return SentimentResult(
            label=label,
            score=round(compound, 4),
            positive_score=round(scores["pos"], 4),
            negative_score=round(scores["neg"], 4),
            neutral_score=round(scores["neu"], 4),
            emotions={},
            topics=[],
            provider="vader_local",
        )


# Singleton instance
sentiment_service = SentimentService()
