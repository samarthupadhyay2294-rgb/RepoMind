"""Repository deletion: filter-scoped Qdrant cleanup, workspace removal.

Regression tests for the "scroll failed" deletion bug: deletion must use
a single repository-scoped filter delete (never scroll), tolerate missing
collections/workspaces, and enforce ownership.

Sync tests driving async services via ``asyncio.run`` (repo convention).
"""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qdrant_client import models
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.repository import Repository, RepositoryStatus, SourceType
from app.exceptions import QdrantError, RepositoryNotFoundError
from app.schemas.repository import RepositoryCreate
from app.services import repositories as repo_service
from app.services.qdrant_service import QdrantService
from tests.conftest import use_owner


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeQdrantClient:
    """Sync fake recording scroll/delete calls with scoped point storage."""

    def __init__(
        self, points: dict[str, dict[str, Any]] | None = None, missing: bool = False
    ) -> None:
        # point_id -> repository_id
        self.points: dict[str, dict[str, Any]] = points or {}
        self.missing = missing
        self.scroll_calls = 0
        self.delete_selectors: list[Any] = []

    def _filtered(self, query_filter: Any) -> list[str]:
        wanted = {c.match.value for c in query_filter.must if c.key == "repository_id"}
        return sorted(
            pid for pid, p in self.points.items() if p["repository_id"] in wanted
        )

    def scroll(self, **kwargs: Any) -> tuple[list[Any], Any]:
        self.scroll_calls += 1
        pts = [
            SimpleNamespace(id=pid, payload=dict(self.points[pid]))
            for pid in self._filtered(kwargs["scroll_filter"])
        ]
        return pts, None

    def delete(self, **kwargs: Any) -> Any:
        if self.missing:
            raise ValueError("Collection repomind not found")
        selector = kwargs["points_selector"]
        self.delete_selectors.append(selector)
        assert isinstance(selector, models.FilterSelector), (
            "repository delete must use a scoped filter delete, not point IDs"
        )
        for pid in self._filtered(selector.filter):
            self.points.pop(pid, None)
        return SimpleNamespace(status="completed")


def make_service(fake: FakeQdrantClient) -> QdrantService:
    return QdrantService(client=fake, collection_name="repomind")


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


def _set_status(
    factory: async_sessionmaker[AsyncSession], rid: Any, status: RepositoryStatus
) -> None:
    async def _go() -> None:
        async with factory() as session:
            repo = await session.get(Repository, rid)
            assert repo is not None
            repo.status = status
            await session.commit()

    run(_go())


class ScopedFake:
    """Service-level fake: scoped store keyed by repository id."""

    def __init__(self) -> None:
        self.points: dict[str, set[str]] = {}
        self.deleted_repos: list[str] = []

    async def delete_repository(self, repository_id: str) -> None:
        self.deleted_repos.append(repository_id)
        self.points.pop(repository_id, None)


# -- QdrantService.delete_repository ----------------------------------------


def test_delete_repository_uses_filter_delete_without_scroll() -> None:
    fake = FakeQdrantClient(
        {"p1": {"repository_id": "repo-a"}, "p2": {"repository_id": "repo-b"}}
    )
    run(make_service(fake).delete_repository("repo-a"))
    assert fake.scroll_calls == 0
    assert len(fake.delete_selectors) == 1
    selector = fake.delete_selectors[0]
    assert isinstance(selector, models.FilterSelector)
    assert {c.key for c in selector.filter.must} == {"repository_id"}
    assert {c.match.value for c in selector.filter.must} == {"repo-a"}
    assert set(fake.points) == {"p2"}


def test_delete_repository_removes_only_that_repository() -> None:
    fake = FakeQdrantClient(
        {
            "a1": {"repository_id": "repo-a"},
            "a2": {"repository_id": "repo-a"},
            "b1": {"repository_id": "repo-b"},
        }
    )
    run(make_service(fake).delete_repository("repo-a"))
    assert set(fake.points) == {"b1"}


def test_delete_repository_without_vectors_succeeds() -> None:
    fake = FakeQdrantClient({})
    run(make_service(fake).delete_repository("repo-a"))
    assert len(fake.delete_selectors) == 1


def test_delete_repository_missing_collection_succeeds() -> None:
    fake = FakeQdrantClient(missing=True)
    run(make_service(fake).delete_repository("repo-never-indexed"))
    assert fake.delete_selectors == []


def test_delete_repository_genuine_failure_raises() -> None:
    class ExplodingClient(FakeQdrantClient):
        def delete(self, **kwargs: Any) -> Any:
            raise ConnectionError("qdrant down")

    with pytest.raises(QdrantError, match="Qdrant delete failed"):
        run(make_service(ExplodingClient()).delete_repository("repo-a"))


def test_delete_repository_blank_id_rejected() -> None:
    with pytest.raises(QdrantError):
        run(make_service(FakeQdrantClient()).delete_repository("  "))


# -- service-level deletion --------------------------------------------------


def test_delete_indexed_repository_removes_db_row_and_vectors(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", "/tmp/repomind-nope")
    gone = _create(session_factory, "owner-A", "gone")
    keep = _create(session_factory, "owner-A", "keep")
    fake = ScopedFake()
    fake.points = {str(keep): {"k1"}, str(gone): {"g1", "g2"}}

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "owner-A", gone, qdrant=fake)  # type: ignore[arg-type]

    run(_go())
    assert fake.deleted_repos == [str(gone)]
    assert fake.points == {str(keep): {"k1"}}
    assert _get(session_factory, gone) is None
    assert _get(session_factory, keep) is not None


def test_delete_failed_repository_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", "/tmp/repomind-nope")
    rid = _create(session_factory, "owner-A", "broken")
    _set_status(session_factory, rid, RepositoryStatus.FAILED)

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(
                session, "owner-A", rid, qdrant=ScopedFake()
            )  # type: ignore[arg-type]

    run(_go())
    assert _get(session_factory, rid) is None


def test_delete_removes_workspace(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.ingestion import workspace_for

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    rid = _create(session_factory, "owner-A", "with-workspace")
    workspace = workspace_for(rid)
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("hello")
    assert workspace.exists()

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(
                session, "owner-A", rid, qdrant=ScopedFake()
            )  # type: ignore[arg-type]

    run(_go())
    assert _get(session_factory, rid) is None
    assert not workspace.exists()
    assert not workspace.parent.exists()


def test_delete_without_workspace_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    rid = _create(session_factory, "owner-A", "no-workspace")

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(
                session, "owner-A", rid, qdrant=ScopedFake()
            )  # type: ignore[arg-type]

    run(_go())
    assert _get(session_factory, rid) is None


def test_delete_other_owner_repository_is_not_found(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    rid = _create(session_factory, "owner-A", "mine")
    fake = ScopedFake()
    fake.points = {str(rid): {"v1"}}

    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(session, "owner-B", rid, qdrant=fake)  # type: ignore[arg-type]

    with pytest.raises(RepositoryNotFoundError):
        run(_go())
    assert fake.deleted_repos == []
    assert _get(session_factory, rid) is not None


def test_delete_unknown_id_is_not_found(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _go() -> None:
        async with session_factory() as session:
            await repo_service.delete_repository(
                session,
                "owner-A",
                uuid.uuid4(),
                qdrant=ScopedFake(),  # type: ignore[arg-type]
            )

    with pytest.raises(RepositoryNotFoundError):
        run(_go())


# -- API-level deletion -------------------------------------------------------


def test_api_delete_then_get_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    use_owner("owner-A")
    created = client.post(
        "/api/v1/repositories",
        json={"name": "doomed", "source_type": "local", "local_path": "/tmp/x"},
    ).json()
    assert client.delete(f"/api/v1/repositories/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/repositories/{created['id']}").status_code == 404


def test_api_delete_other_owner_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "QDRANT_URL", "")
    use_owner("owner-A")
    created = client.post(
        "/api/v1/repositories",
        json={"name": "mine", "source_type": "local", "local_path": "/tmp/x"},
    ).json()
    use_owner("owner-B")
    response = client.delete(f"/api/v1/repositories/{created['id']}")
    assert response.status_code == 404
    use_owner("owner-A")
    assert client.get(f"/api/v1/repositories/{created['id']}").status_code == 200
