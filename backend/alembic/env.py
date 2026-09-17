"""Async Alembic env: RepoMind -> Alembic -> Supabase PostgreSQL.

Uses the app's DATABASE_URL (normalized to asyncpg). NullPool keeps
migrations compatible with Supabase's pooled endpoint, but prefer the
direct connection string for DDL. Fails with a clear error when unconfigured.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db.base import Base
from app.db.session import normalize_database_url
import app.db.models  # noqa: F401  (register ORM models on Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = normalize_database_url(settings.DATABASE_URL)
if not url:
    raise RuntimeError(
        "DATABASE_URL is not configured. Set it to your Supabase "
        "PostgreSQL connection string, then run: alembic upgrade head"
    )
config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
