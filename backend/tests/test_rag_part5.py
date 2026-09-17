"""Part 5 tests: embeddings + Qdrant + retrieval. No network access.

Real Gemini/Qdrant are never touched: a fake embedding client and an
in-memory fake Qdrant stand in, while the real provider wrapper, ID /
payload / filter builders, indexing, and retrieval code paths are tested.
Async service calls run via ``asyncio.run`` (no extra test dependency).
"""

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

from app.embeddings.gemini import (
    GeminiEmbeddingProvider,
    batch_texts,
    get_embedding_provider,
)
from app.exceptions import EmbeddingError, QdrantError
from app.ingestion.models import IngestedChunk, IngestionResult
from app.rag.indexing import index_repository, select_chunks_to_index
from app.rag.retrieval import retrieve
from app.services.qdrant_service import (
    MetadataFilter,
    QdrantService,
    ScoredHit,
    build_filter,
    build_payload,
    build_point_id,
)

DIM = 4


def fake_vector(seed: str, dim: int = DIM) -> list[float]:
    digest = hashlib.sha256(seed.encode()).digest()
    return [(b / 255.0) for b in digest[:dim]]


class FakeEmbeddingClient:
    """Mimics GoogleGenerativeAIEmbeddings (sync methods, real batch sizes)."""

    def __init__(
        self,
        dim: int = DIM,
        failures: list[Exception] | None = None,
        short_batch: bool = False,
    ) -> None:
        self.dim = dim
        self.failures = list(failures or [])
        self.short_batch = short_batch
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        if self.failures:
            raise self.failures.pop(0)
        vectors = [fake_vector(t, self.dim) for t in texts]
        return vectors[:-1] if self.short_batch and vectors else vectors

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        if self.failures:
            raise self.failures.pop(0)
        return fake_vector(f"query:{text}", self.dim)


def _matches(payload: dict[str, Any], cond: Any) -> bool:
    match = cond.match
    value = payload.get(cond.key)
    if isinstance(match, models.MatchValue):
        return value == match.value
    if isinstance(match, models.MatchPrefix):
        return isinstance(value, str) and value.startswith(match.prefix)
    raise AssertionError(f"unsupported match in fake: {type(match)}")


class FakeQdrant:
    """In-memory QdrantClient double honoring real models.Filter objects."""

    def __init__(self) -> None:
        self.collections: dict[str, int] = {}
        self.points: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.deleted: list[Any] = []

    # -- collections ----------------------------------------------------
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
        return None

    def delete_collection(self, collection_name: str) -> None:
        self.collections.pop(collection_name, None)
        self.points.clear()

    # -- writes ---------------------------------------------------------
    def upsert(self, collection_name: str, points: list[Any]) -> None:
        for p in points:
            self.points[str(p.id)] = (list(p.vector), dict(p.payload or {}))

    def delete(self, collection_name: str, points_selector: Any) -> None:
        self.deleted.append(points_selector)
        if isinstance(points_selector, models.PointIdsList):
            for pid in points_selector.points:
                self.points.pop(str(pid), None)
        elif isinstance(points_selector, models.FilterSelector):
            for pid in self._filtered(points_selector.filter):
                self.points.pop(pid, None)

    # -- reads ----------------------------------------------------------
    def _filtered(self, query_filter: Any) -> list[str]:
        out = []
        for pid, (_, payload) in self.points.items():
            if all(_matches(payload, c) for c in query_filter.must):
                out.append(pid)
        return sorted(out)

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: Any,
        limit: int,
    ) -> Any:
        hits = [
            SimpleNamespace(id=pid, score=0.9, payload=dict(self.points[pid][1]))
            for pid in self._filtered(query_filter)[:limit]
        ]
        return SimpleNamespace(points=hits)

    def scroll(
        self,
        collection_name: str,
        scroll_filter: Any,
        limit: int,
        offset: Any,
        with_vectors: bool = False,
    ) -> tuple[list[Any], Any]:
        pts = [
            SimpleNamespace(id=pid, payload=dict(self.points[pid][1]))
            for pid in self._filtered(scroll_filter)
        ]
        return pts, None

    def count(self, collection_name: str, count_filter: Any) -> Any:
        return SimpleNamespace(count=len(self._filtered(count_filter)))


def make_chunk(
    repo: str = "repo-a",
    path: str = "src/auth/login.py",
    start: int = 42,
    end: int = 78,
    content: str = "def login(): pass",
    commit: str | None = "abc123",
    language: str = "python",
    chunk_type: str = "code",
    symbol: str | None = "login",
) -> IngestedChunk:
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return IngestedChunk(
        repository_id=repo,
        commit_sha=commit,
        file_path=path,
        file_hash="filehash",
        language=language,
        chunk_type=chunk_type,
        symbol=symbol,
        start_line=start,
        end_line=end,
        content=content,
        content_hash=content_hash,
    )


def make_service(fake: FakeQdrant | None = None) -> tuple[QdrantService, FakeQdrant]:
    fake = fake or FakeQdrant()
    return QdrantService(fake, collection_name="repomind"), fake


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# -- provider -----------------------------------------------------------


def test_provider_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings
    from app.embeddings.groq import GroqEmbeddingProvider
    from app.embeddings.groq import (
        get_embedding_provider as get_groq_embedding_provider,
    )

    with pytest.raises(EmbeddingError, match="MISTRAL_API_KEY"):
        GroqEmbeddingProvider(api_key="  ", model="m")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
    with pytest.raises(EmbeddingError, match="MISTRAL_API_KEY"):
        get_groq_embedding_provider()


def test_provider_batches_and_preserves_order() -> None:
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", batch_size=2, client=FakeEmbeddingClient()
    )
    texts = [f"chunk {i}" for i in range(5)]
    vectors = run(provider.embed_documents(texts))
    assert vectors == [fake_vector(t) for t in texts]
    assert [len(call) for call in provider._client.document_calls] == [2, 2, 1]


def test_provider_empty_batch_no_api_call() -> None:
    client = FakeEmbeddingClient()
    provider = GeminiEmbeddingProvider(api_key="k", model="m", client=client)
    assert run(provider.embed_documents([])) == []
    assert client.document_calls == []


def test_provider_query_embedding() -> None:
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    assert run(provider.embed_query("hello")) == fake_vector("query:hello")
    with pytest.raises(EmbeddingError, match="empty"):
        run(provider.embed_query("  "))


def test_provider_retries_transient_then_succeeds() -> None:
    client = FakeEmbeddingClient(failures=[RuntimeError("503 overloaded")])
    provider = GeminiEmbeddingProvider(api_key="k", model="m", client=client)
    assert run(provider.embed_query("q")) == fake_vector("query:q")
    assert client.query_calls == ["q", "q"]


def test_provider_permanent_failure_surfaced() -> None:
    client = FakeEmbeddingClient(failures=[ValueError("bad request")] * 3)
    provider = GeminiEmbeddingProvider(api_key="k", model="m", client=client)
    with pytest.raises(EmbeddingError, match="request failed"):
        run(provider.embed_query("q"))


def test_provider_short_batch_surfaced() -> None:
    client = FakeEmbeddingClient(short_batch=True)
    provider = GeminiEmbeddingProvider(api_key="k", model="m", client=client)
    with pytest.raises(EmbeddingError, match="returned"):
        run(provider.embed_documents(["a", "b"]))


def test_batch_texts_helper() -> None:
    assert batch_texts(["a", "b", "c"], 2) == [["a", "b"], ["c"]]


# -- IDs / payloads / filters -------------------------------------------


def test_point_id_deterministic() -> None:
    chunk = make_chunk()
    assert build_point_id(chunk) == build_point_id(make_chunk())
    other_repo = make_chunk(repo="repo-b")
    assert build_point_id(chunk) != build_point_id(other_repo)
    changed = make_chunk(content="def login(user): pass")
    assert build_point_id(chunk) != build_point_id(changed)


def test_payload_carries_part4_metadata() -> None:
    payload = build_payload(make_chunk())
    assert payload == {
        "repository_id": "repo-a",
        "commit_sha": "abc123",
        "file_path": "src/auth/login.py",
        "path": "src/auth/login.py",
        "language": "python",
        "symbol": "login",
        "start_line": 42,
        "end_line": 78,
        "chunk_type": "code",
        "content_hash": payload["content_hash"],
        "is_generated": False,
        "content": "def login(): pass",
    }


def test_filter_always_repository_scoped() -> None:
    filt = build_filter("repo-a", MetadataFilter(language="python"))
    keys = [c.key for c in filt.must]
    assert keys[0] == "repository_id"
    assert "language" in keys
    with pytest.raises(QdrantError):
        build_filter("  ")
    prefixed = build_filter("repo-a", MetadataFilter(file_prefix="src/"))
    assert any(isinstance(c.match, models.MatchPrefix) for c in prefixed.must)


# -- Qdrant service ------------------------------------------------------


def test_ensure_collection_and_size_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    service, fake = make_service()
    run(service.ensure_collection(4))
    assert fake.collections["repomind"] == 4
    run(service.ensure_collection(4))  # idempotent
    # Development recreates a stale collection so indexing can proceed.
    monkeypatch.setattr(settings, "APP_ENV", "development")
    run(service.ensure_collection(8))
    assert fake.collections["repomind"] == 8
    # Outside development the stale collection is kept and reported.
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(QdrantError, match="vector size"):
        run(service.ensure_collection(4))
    assert fake.collections["repomind"] == 8


def test_upsert_idempotent_no_duplicates() -> None:
    service, fake = make_service()
    chunks = [make_chunk(), make_chunk(path="src/other.py", content="x = 1")]
    run(service.ensure_collection(DIM))
    run(service.upsert_chunks(chunks, [fake_vector("a"), fake_vector("b")]))
    run(service.upsert_chunks(chunks, [fake_vector("a"), fake_vector("b")]))
    assert len(fake.points) == 2
    assert run(service.count("repo-a")) == 2


def test_search_requires_repository_scope() -> None:
    service, _ = make_service()
    with pytest.raises(QdrantError, match="repository_id"):
        run(service.search(fake_vector("q"), "  ", 5))


def test_repository_isolation_at_filter_layer() -> None:
    service, _ = make_service()
    run(service.ensure_collection(DIM))
    run(
        service.upsert_chunks(
            [make_chunk(repo="repo-a"), make_chunk(repo="repo-b")],
            [fake_vector("a"), fake_vector("b")],
        )
    )
    hits_a = run(service.search(fake_vector("q"), "repo-a", 10))
    assert {h.payload["repository_id"] for h in hits_a} == {"repo-a"}
    assert run(service.count("repo-b")) == 1


def test_delete_repository_scoped() -> None:
    service, fake = make_service()
    run(service.ensure_collection(DIM))
    run(
        service.upsert_chunks(
            [make_chunk(repo="repo-a"), make_chunk(repo="repo-b")],
            [fake_vector("a"), fake_vector("b")],
        )
    )
    run(service.delete_repository("repo-a"))
    assert run(service.count("repo-a")) == 0
    assert run(service.count("repo-b")) == 1
    assert len(fake.points) == 1


def test_delete_commit_scoped() -> None:
    service, _ = make_service()
    run(service.ensure_collection(DIM))
    run(
        service.upsert_chunks(
            [
                make_chunk(repo="repo-a", commit="c1"),
                make_chunk(repo="repo-a", commit="c2", content="other"),
            ],
            [fake_vector("a"), fake_vector("b")],
        )
    )
    run(service.delete_commit("repo-a", "c1"))
    assert run(service.count("repo-a")) == 1


# -- incremental indexing -------------------------------------------------


def test_select_chunks_new_unchanged_changed() -> None:
    unchanged = make_chunk(content="same")
    changed = make_chunk(path="src/other.py", content="v2")
    to_index, skipped = select_chunks_to_index(
        [unchanged, changed], {unchanged.content_hash, "old-hash-for-other"}
    )
    # changed chunk has a new hash → indexed; unchanged → skipped.
    assert [c.file_path for c in to_index] == ["src/other.py"]
    assert skipped == 1
    all_new, none = select_chunks_to_index([unchanged], None)
    assert len(all_new) == 1 and none == 0


def test_index_repository_stats_and_skip_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", DIM)
    service, fake = make_service()
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", batch_size=32, client=FakeEmbeddingClient()
    )
    chunks = [make_chunk(), make_chunk(path="src/b.py", content="b = 2")]
    ingestion = IngestionResult(
        repository_id="repo-a", commit_sha="abc123", chunks=chunks
    )
    result = run(
        index_repository("repo-a", ingestion, provider, service, known_hashes=None)
    )
    assert result.chunks_seen == 2
    assert result.chunks_indexed == 2
    assert result.embeddings_generated == 2
    assert result.embedding_batches == 1

    known = {c.content_hash for c in chunks}
    rerun = run(
        index_repository("repo-a", ingestion, provider, service, known_hashes=known)
    )
    assert rerun.chunks_indexed == 0
    assert rerun.chunks_skipped == 2
    assert len(fake.points) == 2  # no duplicates


def test_index_repository_removes_stale_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", DIM)
    service, fake = make_service()
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    old = [make_chunk(), make_chunk(path="src/gone.py", content="gone")]
    run(
        index_repository(
            "repo-a",
            IngestionResult(repository_id="repo-a", chunks=old),
            provider,
            service,
            remove_stale=False,
        )
    )
    assert len(fake.points) == 2
    new = [make_chunk()]
    result = run(
        index_repository(
            "repo-a",
            IngestionResult(repository_id="repo-a", chunks=new),
            provider,
            service,
        )
    )
    assert result.stale_points_removed == 1
    assert len(fake.points) == 1


# -- retrieval --------------------------------------------------------------


def test_retrieval_returns_structured_evidence() -> None:
    service, _ = make_service()
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    run(service.ensure_collection(DIM))
    run(service.upsert_chunks([make_chunk()], [fake_vector("doc")]))
    results = run(retrieve("repo-a", "Where is authentication?", provider, service))
    assert len(results) == 1
    hit = results[0]
    assert hit.repository_id == "repo-a"
    assert hit.file_path == "src/auth/login.py"
    assert (hit.start_line, hit.end_line) == (42, 78)
    assert hit.content == "def login(): pass"
    assert hit.citation == "src/auth/login.py:42-78"
    assert hit.symbol == "login"
    assert isinstance(hit.score, float)


def test_retrieval_never_searches_without_repository() -> None:
    service, _ = make_service()
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    with pytest.raises(QdrantError, match="repository_id"):
        run(retrieve("", "query", provider, service))
    with pytest.raises(QdrantError, match="query"):
        run(retrieve("repo-a", "  ", provider, service))


def test_retrieval_caps_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "RETRIEVAL_MAX_TOP_K", 3)
    seen: dict[str, Any] = {}

    class SpyService(QdrantService):
        async def search(
            self,
            query_vector: list[float],
            repository_id: str,
            limit: int,
            extra: Any = None,
        ) -> list[ScoredHit]:
            seen["limit"] = limit
            return []

    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    run(retrieve("repo-a", "q", provider, SpyService(FakeQdrant()), top_k=100000))
    assert seen["limit"] == 3


def test_retrieval_drops_cross_repo_hits() -> None:
    class LeakyService(QdrantService):
        async def search(
            self,
            query_vector: list[float],
            repository_id: str,
            limit: int,
            extra: Any = None,
        ) -> list[ScoredHit]:
            chunk = make_chunk(repo="repo-b")
            return [ScoredHit(point_id="x", score=0.99, payload=build_payload(chunk))]

    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    results = run(retrieve("repo-a", "q", provider, LeakyService(FakeQdrant())))
    assert results == []


def test_metadata_filter_reaches_qdrant() -> None:
    service, _ = make_service()
    run(service.ensure_collection(DIM))
    run(
        service.upsert_chunks(
            [
                make_chunk(path="src/a.py", language="python"),
                make_chunk(
                    path="docs/b.md",
                    language="markdown",
                    content="docs here",
                    chunk_type="doc",
                ),
            ],
            [fake_vector("a"), fake_vector("b")],
        )
    )
    hits = run(
        service.search(
            fake_vector("q"), "repo-a", 10, MetadataFilter(language="python")
        )
    )
    assert len(hits) == 1
    assert hits[0].payload["file_path"] == "src/a.py"
    hits = run(
        service.search(
            fake_vector("q"), "repo-a", 10, MetadataFilter(file_prefix="docs/")
        )
    )
    assert len(hits) == 1
    assert hits[0].payload["file_path"] == "docs/b.md"


# -- end-to-end (mocked externals) --------------------------------------------


def test_end_to_end_ingest_index_retrieve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings
    from app.services.ingestion import ingest_directory

    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", DIM)

    root = tmp_path / "fixture_repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (root / "src" / "main.py").write_text(
        "def main():\n    print('hi')\n", encoding="utf-8"
    )
    (root / "src" / "auth.py").write_text(
        "def authenticate(user):\n    return True\n", encoding="utf-8"
    )
    (root / "tests" / "test_auth.py").write_text(
        "def test_authenticate():\n    assert True\n", encoding="utf-8"
    )

    ingestion = ingest_directory(root, repository_id="fixture", commit_sha="sha9")
    assert ingestion.chunks_created >= 4

    service, _ = make_service()
    provider = GeminiEmbeddingProvider(
        api_key="k", model="m", client=FakeEmbeddingClient()
    )
    index_result = run(index_repository("fixture", ingestion, provider, service))
    assert index_result.chunks_indexed == ingestion.chunks_created
    assert index_result.chunks_failed == 0

    results = run(
        retrieve("fixture", "Where is authentication handled?", provider, service)
    )
    assert results, "expected evidence for the fixture repository"
    assert all(r.repository_id == "fixture" for r in results)
    assert all(r.citation for r in results)
