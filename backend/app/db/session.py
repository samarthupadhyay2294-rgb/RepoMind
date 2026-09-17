"""Async SQLAlchemy engine/session layer for Supabase PostgreSQL.

Engine creation is lazy: importing the app or hitting /health never requires
a configured database. Routes that need the DB raise a clear DatabaseError
when DATABASE_URL is missing instead of leaking a driver traceback.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.exceptions import DatabaseError

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def normalize_database_url(url: str) -> str:
    """Map Supabase-style URLs to the asyncpg dialect SQLAlchemy needs.
    
    For development, if DATABASE_URL is empty or not set, defaults to SQLite
    for local development without requiring external database configuration.
    """
    url = url.strip()
    if not url:
        # Default to SQLite for development when DATABASE_URL is not configured
        return "sqlite+aiosqlite:///./repomind.db"
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    # SQLite URLs are already in the correct format for aiosqlite
    return url


def is_database_configured() -> bool:
    return bool(normalize_database_url(settings.DATABASE_URL))


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        normalized = normalize_database_url(settings.DATABASE_URL)
        if not normalized:
            raise DatabaseError("DATABASE_URL is not configured.")
        options: dict[str, Any] = {"pool_pre_ping": True}
        if normalized.startswith("postgresql"):
            # Conservative sizing for Supabase connection limits.
            options.update(pool_size=5, max_overflow=10)
        elif normalized.startswith("sqlite"):
            # SQLite doesn't support connection pooling
            options.update(pool_size=1, max_overflow=0)
        logger.info("Creating async database engine.")
        _engine = create_async_engine(normalized, **options)
        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine


async def reset_engine() -> None:
    """Dispose the cached engine (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed."""
    get_engine()  # Raises DatabaseError when unconfigured.
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
