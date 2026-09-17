"""Shared fixtures: isolated SQLite per test; never touches real Supabase."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_current_owner_id
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    asyncio.run(engine.dispose())


@pytest.fixture
def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    async def override_session() -> Iterator[AsyncSession]:
        async with session_factory() as session:  # type: ignore[misc]
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_owner(owner_id: str) -> None:
    app.dependency_overrides[get_current_owner_id] = lambda: owner_id
