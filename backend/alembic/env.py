"""Alembic environment configuration."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.base import Base

# Import all models so Alembic detects them
from app.models.tenant import Tenant  # noqa
from app.models.brand import Brand  # noqa
from app.models.region import Region  # noqa
from app.models.location import Location  # noqa
from app.models.user import User  # noqa
from app.models.connector import Connector  # noqa
from app.models.alert_rule import AlertRule  # noqa

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(
        url,
        connect_args={"ssl": False},
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
