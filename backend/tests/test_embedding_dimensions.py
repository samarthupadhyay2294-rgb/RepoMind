"""Embedding↔Qdrant dimension contract (no network access).

Single source of truth: ``settings.EMBEDDING_DIMENSION``. Indexing rejects
wrong-sized vectors before any Qdrant write; ``ensure_collection`` recreates
a stale collection in development and refuses (without destroying anything)
outside development. Sync tests drive async code via ``asyncio.run``.
"""

import asyncio
import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

from app.config import settings
from app.embeddings.groq import GroqEmbeddingProvider, get_embedding_provider
from app.exceptions import EmbeddingError, QdrantError
from app.ingestion.models import IngestedChunk
from app.ingestion.models import IngestionResult
from app.rag.indexing import index_repository
from app.rag.retrieval import retrieve
from app.services.qdrant_service import QdrantService


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def fake_vector(seed: str, dim: int) -> list[float]:
    digest = hashlib.sha256(seed.encode()).digest()
    return [(digest[i % len(digest)] / 255.0) for i in range(dim)]


class FakeEmbeddingClient:
    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [fake_vector(t, self.dim) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return fake_vector(f"query:{text}", self.dim)


class FakeQdrantClient:
    """Sync double tracking collections, points, and deletions."""

    def __init__(self) -> None:
        self.collections: dict[str, int] = {}
        self.points: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.deleted_collections: list[str] = []
        self.indexed_fields: list[tuple[str, Any]] = []

    def get_collection(self, name: str) -> Any:
        if name not in self.collections:
            raise ValueError("missing collection")
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(size=self.collections[name])
                )
            )
        )

    def create_collection(self, collection_name: str, vectors_config: Any) -> None:
        self.collections[collection_name] = vectors_config.size

    def create_payload_index(self, collection_name: str, **kwargs: Any) -> None:
        self.indexed_fields.append((collection_name, kwargs.get("field_name")))

    def delete_collection(self, name: str) -> None:
        self.deleted_collections.append(name)
        self.collections.pop(name, None)
        self.points.clear()

    def upsert(self, collection_name: str, points: list[Any]) -> None:
        for p in points:
            self.points[str(p.id)] = (list(p.vector), dict(p.payload or {}))

    def delete(self, collection_name: str, points_selector: Any) -> None:
        assert isinstance(points_selector, models.FilterSelector)
        wanted = {
            c.match.value
            for c in points_selector.filter.must
            if c.key == "repository_id"
        }
        for pid in [
            pid
            for pid, (_, payload) in self.points.items()
            if payload.get("repository_id") in wanted
        ]:
            self.points.pop(pid, None)

    def _filtered(self, query_filter: Any) -> list[str]:
        out = []
        for pid, (_, payload) in self.points.items():
            if all(payload.get(c.key) == c.match.value for c in query_filter.must):
                out.append(pid)
        return sorted(out)

    def query_points(
        self, collection_name: str, query: list[float], query_filter: Any, limit: int
    ) -> Any:
        assert len(query) == self.collections[collection_name], (
            "query dimension must match the collection"
        )
        hits = [
            SimpleNamespace(id=pid, score=0.9, payload=dict(self.points[pid][1]))
            for pid in self._filtered(query_filter)[:limit]
        ]
        return SimpleNamespace(points=hits)

    def scroll(self, **kwargs: Any) -> tuple[list[Any], Any]:
        return [], None

    def count(self, collection_name: str, count_filter: Any = None) -> Any:
        if count_filter is None:
            return SimpleNamespace(count=len(self.points))
        return SimpleNamespace(count=len(self._filtered(count_filter)))


def make_service(fake: FakeQdrantClient) -> QdrantService:
    return QdrantService(client=fake, collection_name="repomind")


def make_chunk(repo: str = "repo-a", content: str = "def f(): pass") -> IngestedChunk:
    return IngestedChunk(
        repository_id=repo,
        commit_sha="abc123",
        file_path="src/a.py",
        file_hash="filehash",
        language="python",
        chunk_type="code",
        symbol="f",
        start_line=1,
        end_line=2,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )


def make_provider(dim: int) -> GroqEmbeddingProvider:
    return GroqEmbeddingProvider(
        api_key="k", model="m", batch_size=32, client=FakeEmbeddingClient(dim)
    )


# -- configuration contract --------------------------------------------------


def test_dimension_default_matches_provider_model() -> None:
    # mistral-embed emits 1024-dimensional vectors; the setting must agree.
    assert settings.EMBEDDING_DIMENSION == 1024


def test_embedding_provider_is_model_separate_from_groq_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setattr(settings, "MISTRAL_EMBEDDING_MODEL", "mistral-embed")
    provider = get_embedding_provider()
    assert provider.model == "mistral-embed"
    # Groq LLM settings are independent of the embedding path.
    assert settings.GROQ_MODEL != provider.model


def test_embedding_provider_requires_mistral_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "  ")
    with pytest.raises(EmbeddingError, match="MISTRAL_API_KEY"):
        get_embedding_provider()


# -- indexing validation ------------------------------------------------------


def test_indexing_accepts_configured_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 16)
    fake = FakeQdrantClient()
    service = make_service(fake)
    result = run(
        index_repository(
            "repo-a",
            IngestionResult(
                repository_id="repo-a", commit_sha="abc", chunks=[make_chunk()]
            ),
            make_provider(16),
            service,
        )
    )
    assert result.chunks_indexed == 1
    assert fake.collections["repomind"] == 16
    assert len(fake.points) == 1


def test_indexing_rejects_wrong_dimension_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 16)
    fake = FakeQdrantClient()
    service = make_service(fake)
    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        run(
            index_repository(
                "repo-a",
                IngestionResult(
                    repository_id="repo-a", commit_sha="abc", chunks=[make_chunk()]
                ),
                make_provider(32),
                service,
            )
        )
    assert "repomind" not in fake.collections
    assert fake.points == {}


# -- collection policy ----------------------------------------------------------


def test_new_collection_uses_configured_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 16)
    fake = FakeQdrantClient()
    run(make_service(fake).ensure_collection(settings.EMBEDDING_DIMENSION))
    assert fake.collections["repomind"] == 16
    assert ("repomind", "repository_id") in fake.indexed_fields


def test_matching_collection_is_left_alone() -> None:
    fake = FakeQdrantClient()
    fake.collections["repomind"] = 16
    run(make_service(fake).ensure_collection(16))
    assert fake.collections["repomind"] == 16
    assert fake.deleted_collections == []


def test_mismatch_recreates_collection_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    fake = FakeQdrantClient()
    fake.collections["repomind"] = 8
    run(make_service(fake).ensure_collection(16))
    assert fake.deleted_collections == ["repomind"]
    assert fake.collections["repomind"] == 16


def test_mismatch_errors_without_destroying_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    fake = FakeQdrantClient()
    fake.collections["repomind"] = 8
    with pytest.raises(QdrantError, match="vector size"):
        run(make_service(fake).ensure_collection(16))
    assert fake.deleted_collections == []
    assert fake.collections["repomind"] == 8


# -- retrieval + deletion compatibility ------------------------------------------


def test_retrieval_roundtrip_at_configured_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 16)
    fake = FakeQdrantClient()
    service = make_service(fake)
    provider = make_provider(16)
    run(
        index_repository(
            "repo-a",
            IngestionResult(
                repository_id="repo-a", commit_sha="abc", chunks=[make_chunk()]
            ),
            provider,
            service,
        )
    )
    hits = run(retrieve("repo-a", "what does f do?", provider, service))
    assert len(hits) == 1
    assert hits[0].file_path == "src/a.py"


def test_scoped_delete_still_works_after_dimension_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 16)
    fake = FakeQdrantClient()
    service = make_service(fake)
    provider = make_provider(16)
    for repo in ("repo-a", "repo-b"):
        run(
            index_repository(
                repo,
                IngestionResult(
                    repository_id=repo, commit_sha="abc", chunks=[make_chunk(repo)]
                ),
                provider,
                service,
            )
        )
    assert len(fake.points) == 2
    run(service.delete_repository("repo-a"))
    assert "repomind" in fake.collections  # collection itself is kept
    remaining = [payload for _, payload in fake.points.values()]
    assert {p["repository_id"] for p in remaining} == {"repo-b"}
