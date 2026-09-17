"""Gap #3: indexing endpoint + status flow (fakes; no network/LLM)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import indexing_service as indexing
from tests.conftest import use_owner


class FakeProvider:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeQdrant:
    def __init__(self) -> None:
        self.upserted = 0

    async def ensure_collection(self, vector_size: int) -> None:
        return None

    async def upsert_chunks(
        self, chunks: list[object], vectors: list[list[float]]
    ) -> int:
        self.upserted += len(chunks)
        return len(chunks)

    async def list_point_ids(self, repository_id: str) -> set[str]:
        return set()

    async def delete_point_ids(self, point_ids: set[str] | list[str]) -> None:
        return None


class BrokenProvider(FakeProvider):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend exploded")


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> FakeQdrant:
    import app.embeddings.groq as groq_mod
    from app.config import settings
    from app.services.qdrant_service import QdrantService

    fake = FakeQdrant()
    monkeypatch.setattr(groq_mod, "get_embedding_provider", lambda: FakeProvider())
    monkeypatch.setattr(QdrantService, "from_settings", classmethod(lambda cls: fake))
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 3)
    return fake


def _register_local(client: TestClient, tmp_path: Path, name: str = "demo") -> dict:
    src = tmp_path / name
    src.mkdir(exist_ok=True)
    (src / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    response = client.post(
        "/api/v1/repositories",
        json={"name": name, "source_type": "local", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_index_success_and_status(
    client: TestClient, tmp_path: Path, fakes: FakeQdrant
) -> None:
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    assert created["status"] == "pending"
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "indexed"
    assert body["error_message"] is None
    assert fakes.upserted > 0


def test_index_unknown_repository_is_404(client: TestClient, fakes: FakeQdrant) -> None:
    use_owner("owner-A")
    response = client.post(
        "/api/v1/repositories/123e4567-e89b-12d3-a456-426614174000/index"
    )
    assert response.status_code == 404


def test_index_other_owner_repository_is_404(
    client: TestClient, tmp_path: Path, fakes: FakeQdrant
) -> None:
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    use_owner("owner-B")
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 404


def test_index_failure_marks_failed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.embeddings.groq as groq_mod
    from app.services.qdrant_service import QdrantService

    monkeypatch.setattr(groq_mod, "get_embedding_provider", lambda: BrokenProvider())
    monkeypatch.setattr(
        QdrantService, "from_settings", classmethod(lambda cls: FakeQdrant())
    )
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"]


def test_repeated_indexing_is_idempotent(
    client: TestClient, tmp_path: Path, fakes: FakeQdrant
) -> None:
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    for _ in range(2):
        response = client.post(f"/api/v1/repositories/{created['id']}/index")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "indexed"


def test_index_without_backends_fails_cleanly(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No fakes: real providers raise controlled errors → failed, not 500.
    # Clear ambient credentials so the test is hermetic (developer .env
    # files may otherwise contain working keys).
    from app.config import settings

    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(settings, "QDRANT_URL", "")
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert "MISTRAL_API_KEY" in (body["error_message"] or "")
    assert "backend/.env" in (body["error_message"] or "")


def test_service_sets_terminal_status_on_unexpected_error(
    session_factory,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    fakes: FakeQdrant,
) -> None:
    import asyncio

    import app.services.ingestion as ingestion_mod

    def _boom(repository):  # type: ignore[no-untyped-def]
        raise ValueError("totally unexpected")

    monkeypatch.setattr(ingestion_mod, "ingest_repository", _boom)

    async def _go():  # type: ignore[no-untyped-def]
        from app.db.models.repository import SourceType
        from app.schemas.repository import RepositoryCreate
        from app.services import repositories as repo_service

        async with session_factory() as session:
            repo = await repo_service.create_repository(
                session,
                "o",
                RepositoryCreate(
                    name="x", source_type=SourceType.LOCAL, local_path="/tmp/x"
                ),
            )
            finished = await indexing.run_indexing(session, "o", repo.id)
            assert finished.status.value == "failed"
            assert finished.error_message == "Indexing failed."

    asyncio.run(_go())
