"""Database layer tests: URL normalization, config, metadata. No network."""

import pytest

from app.config import settings
from app.db.base import Base
from app.db.session import (
    get_engine,
    is_database_configured,
    normalize_database_url,
    reset_engine,
)
from app.exceptions import DatabaseError


def test_normalize_supabase_postgres_url() -> None:
    assert (
        normalize_database_url("postgresql://u:p@host:5432/db")
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+asyncpg://u:p@host:5432/db"
    )


def test_normalize_passes_through_async_and_sqlite() -> None:
    assert (
        normalize_database_url("postgresql+asyncpg://u:p@host/db")
        == "postgresql+asyncpg://u:p@host/db"
    )
    assert (
        normalize_database_url("sqlite+aiosqlite:///./t.db")
        == "sqlite+aiosqlite:///./t.db"
    )
    assert normalize_database_url("  ") == ""


def test_unconfigured_database_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    assert not is_database_configured()
    with pytest.raises(DatabaseError, match="DATABASE_URL is not configured"):
        get_engine()


def test_configured_database_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://u:p@host:5432/db")
    assert is_database_configured()


def test_repository_model_registered_on_shared_base() -> None:
    assert "repositories" in Base.metadata.tables
    table = Base.metadata.tables["repositories"]
    assert set(table.columns.keys()) >= {
        "id",
        "owner_id",
        "name",
        "source_type",
        "source_url",
        "local_path",
        "default_branch",
        "current_commit_sha",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    }


def test_reset_engine_clears_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    asyncio.run(reset_engine())
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    with pytest.raises(DatabaseError):
        get_engine()
