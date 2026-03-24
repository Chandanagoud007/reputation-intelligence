"""
Reputation Intelligence Platform — Application Configuration
Loads from environment variables / .env file via pydantic-settings
"""
from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "Reputation Intelligence Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"


    # ─── PostgreSQL ───────────────────────────────────────────────
    DATABASE_URL: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    # ─── MongoDB ──────────────────────────────────────────────────
    MONGO_URI: str
    MONGO_DB: str = "reputation_reviews"

    # ─── Redis ────────────────────────────────────────────────────
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 300

    # ─── RabbitMQ ─────────────────────────────────────────────────
    RABBITMQ_URL: str

    # ─── AWS ──────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_S3_BUCKET: str
    AWS_COMPREHEND_REGION: str = "us-east-1"
    AWS_SES_SENDER_EMAIL: str

    # ─── AI / NLP ─────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""
    SENTIMENT_PROVIDER: Literal["aws_comprehend", "openai", "anthropic", "huggingface"] = "aws_comprehend"
    AI_INSIGHTS_PROVIDER: Literal["openai", "anthropic"] = "anthropic"

    # ─── Review Platform Connectors ───────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    YELP_API_KEY: str = ""
    TRIPADVISOR_API_KEY: str = ""

    # ─── Auth / JWT ───────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Notifications ────────────────────────────────────────────
    SENDGRID_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # ─── Monitoring ───────────────────────────────────────────────
    SENTRY_DSN: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
