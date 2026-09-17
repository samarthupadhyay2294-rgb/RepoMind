"""Gap #2: repository deletion cleans its scoped Qdrant vectors.

Sync tests driving async services via ``asyncio.run`` (repo convention).
"""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.repository import Repository, SourceType
from app.exceptions import QdrantError, RepositoryNotFoundError
from app.schemas.repository import RepositoryCreate
from app.services import repositories as repo_service


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeQdrant:
    """Minimal scoped store: points keyed by repository id."""

    def __init__(self) -> None:
        self.points: dict[str, set[str]] = {}
        self.deleted_repos: list[str] = []

    async def delete_repository(self, repository_id: str) -> None:
        self.deleted_repos.append(repository_id)
        self.points.pop(repository_id, None)


def _create(factory: async_sessionmaker[AsyncSession], owner: str, name: str) -> Any:
    async def _go() -> Any:
        async with factory() as session:
            repo = await repo_service.create_repository(
                session,
                owner,
                RepositoryCreate(
                    name=name, source_type=SourceType.LOCAL, local_path="/tmp/x"
                ),
            )
            return repo.id

    return run(_go())


def _get(factory: async_sessionmaker[AsyncSession], rid: Any) -> Any:
    async def _go() -> Any:
        async with factory() as session:
            return await session.get(Repository, rid)

    return run(_go())


def test_delete_removes_only_own_vectors(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    keep = _create(session_factory, "o", "keep")
    gone = _create(session_factory, "o", "gone")
    fake = FakeQdrant()
    fake.points = {str(keep): {"k1"}, str(gone): {"g1", "g2"}}

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "o", gone, qdrant=fake)  # type: ignore[arg-type]

    run(_go())
    assert fake.deleted_repos == [str(gone)]
    assert fake.points == {str(keep): {"k1"}}
    assert _get(session_factory, gone) is None
    assert _get(session_factory, keep) is not None


def test_repeated_delete_is_404(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    rid = _create(session_factory, "o", "temp")

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "o", rid, qdrant=FakeQdrant())  # type: ignore[arg-type]

    run(_go())

    async def _again() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "o", rid, qdrant=FakeQdrant())  # type: ignore[arg-type]

    with pytest.raises(RepositoryNotFoundError):
        run(_again())


def test_qdrant_failure_keeps_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    rid = _create(session_factory, "o", "fragile")

    class Exploding:
        async def delete_repository(self, repository_id: str) -> None:
            raise QdrantError("boom")

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "o", rid, qdrant=Exploding())  # type: ignore[arg-type]

    with pytest.raises(QdrantError):
        run(_go())
    assert _get(session_factory, rid) is not None


def test_delete_without_qdrant_configured_skips_vectors(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    rid = _create(session_factory, "o", "plain")

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "o", rid)

    run(_go())
    assert _get(session_factory, rid) is None


def test_delete_unknown_id_is_not_found(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(
                session,
                "o",
                uuid.uuid4(),
                qdrant=FakeQdrant(),  # type: ignore[arg-type]
            )

    with pytest.raises(RepositoryNotFoundError):
        run(_go())
