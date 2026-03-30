"""
Reputation Intelligence Platform — Database Connection Management
"""
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ─── PostgreSQL ───────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def init_postgres() -> None:
    print("Connecting to PostgreSQL...")
    # Import all models so SQLAlchemy registers them
    from app.models.tenant import Tenant  # noqa
    from app.models.brand import Brand  # noqa
    from app.models.region import Region  # noqa
    from app.models.location import Location  # noqa
    from app.models.user import User  # noqa
    from app.models.connector import Connector  # noqa
    from app.models.alert_rule import AlertRule  # noqa
    async with engine.connect() as conn:
        from sqlalchemy import text
        await conn.execute(text("SELECT 1"))
    print("PostgreSQL connection established")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── MongoDB ──────────────────────────────────────────────────────────────────

_mongo_client: AsyncIOMotorClient | None = None


async def init_mongo() -> None:
    global _mongo_client
    print(f"Connecting to MongoDB...")
    _mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    await _mongo_client.admin.command("ping")
    print("MongoDB connection established")


def get_mongo_db():
    if _mongo_client is None:
        raise RuntimeError("MongoDB not initialized.")
    return _mongo_client[settings.MONGO_DB]


def get_collection(name: str):
    return get_mongo_db()[name]


# ─── Redis ────────────────────────────────────────────────────────────────────

_redis_client = None


async def init_redis() -> None:
    global _redis_client
    print(f"Connecting to Redis...")
    _redis_client = await from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis_client.ping()
    print("Redis connection established")


def get_redis():
    if _redis_client is None:
        raise RuntimeError("Redis not initialized.")
    return _redis_client


# ─── Shutdown ─────────────────────────────────────────────────────────────────

async def close_connections() -> None:
    global _mongo_client, _redis_client
    if _mongo_client:
        _mongo_client.close()
    if _redis_client:
        await _redis_client.aclose()
    await engine.dispose()
    print("All connections closed")
