"""Qdrant vector-store boundary (Part 5).

Only module allowed to touch ``qdrant_client``. Application code uses
:class:`QdrantService` plus the pure helpers (:func:`build_point_id`,
:func:`build_payload`, :func:`build_filter`) so IDs, payloads, and
repository scoping stay consistent and unit-testable without a server.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.exceptions import QdrantError
from app.ingestion.models import IngestedChunk

logger = logging.getLogger(__name__)

_UPSERT_BATCH_SIZE = 128
_SCROLL_LIMIT = 1024

# Every repository-scoped read (scroll/count/filtered search) filters on
# this payload key. Hosted Qdrant rejects filtered reads without a keyword
# index ("Index required but not found"), so ensure_collection builds it.
_REPOSITORY_ID_INDEX_FIELD = "repository_id"


@dataclass
class StoredPoint:
    point_id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass
class ScoredHit:
    point_id: str
    score: float
    payload: dict[str, Any]


@dataclass
class MetadataFilter:
    commit_sha: str | None = None
    snapshot_id: str | None = None
    language: str | None = None
    file_path: str | None = None
    file_prefix: str | None = None
    chunk_type: str | None = None


def build_point_id(chunk: IngestedChunk) -> str:
    """Deterministic UUID for a chunk (same chunk → same ID).

    Derived from repository + commit + path + lines + content hash, so
    re-indexing is idempotent and different repositories never collide.
    """
    stable = "|".join(
        [
            chunk.repository_id,
            chunk.commit_sha or "",
            chunk.file_path,
            str(chunk.start_line),
            str(chunk.end_line),
            chunk.content_hash,
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"repomind:{stable}"))


def build_payload(chunk: IngestedChunk) -> dict[str, Any]:
    """Qdrant payload carrying Part 4 metadata + content for citations."""
    payload: dict[str, Any] = {
        "repository_id": chunk.repository_id,
        "commit_sha": chunk.commit_sha,
        "file_path": chunk.file_path,
        "language": chunk.language,
        "symbol": chunk.symbol,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "chunk_type": chunk.chunk_type,
        "content_hash": chunk.content_hash,
        "content": chunk.content,
    }
    # Part 1 snapshot isolation: new writes carry snapshot scope plus
    # graph/overview-ready metadata. Legacy points without snapshot_id
    # remain readable via the server-side backfill mapping in retrieval.
    snapshot_id = getattr(chunk, "snapshot_id", None)
    if snapshot_id:
        payload["snapshot_id"] = snapshot_id
    payload.setdefault("path", chunk.file_path)
    payload.setdefault("is_generated", False)
    return payload


def build_filter(repository_id: str, extra: MetadataFilter | None = None) -> Any:
    """Qdrant filter ALWAYS scoped to ``repository_id`` (isolation)."""
    if not repository_id.strip():
        raise QdrantError("repository_id is required for Qdrant filtering.")
    from qdrant_client import models

    must: list[Any] = [
        models.FieldCondition(
            key="repository_id", match=models.MatchValue(value=repository_id)
        )
    ]
    if extra is not None:
        if extra.commit_sha is not None:
            must.append(
                models.FieldCondition(
                    key="commit_sha",
                    match=models.MatchValue(value=extra.commit_sha),
                )
            )
        if extra.snapshot_id is not None:
            must.append(
                models.FieldCondition(
                    key="snapshot_id",
                    match=models.MatchValue(value=extra.snapshot_id),
                )
            )
        if extra.language is not None:
            must.append(
                models.FieldCondition(
                    key="language", match=models.MatchValue(value=extra.language)
                )
            )
        if extra.file_path is not None:
            must.append(
                models.FieldCondition(
                    key="file_path",
                    match=models.MatchValue(value=extra.file_path),
                )
            )
        if extra.file_prefix is not None:
            must.append(
                models.FieldCondition(
                    key="file_path",
                    match=models.MatchPrefix(prefix=extra.file_prefix),
                )
            )
        if extra.chunk_type is not None:
            must.append(
                models.FieldCondition(
                    key="chunk_type",
                    match=models.MatchValue(value=extra.chunk_type),
                )
            )
    return models.Filter(must=must)


def _is_missing_collection(exc: Exception) -> bool:
    """True when Qdrant reports the collection does not exist.

    Deleting vectors for a never-indexed repository must succeed: there
    is nothing to remove. Only this narrow case is tolerated — every
    other failure (connection, auth, timeouts) still raises.
    """
    if getattr(exc, "status_code", None) == 404:
        return True
    message = str(exc).lower()
    return (
        "not found" in message
        or "does not exist" in message
        or "doesn't exist" in message
    )


class QdrantService:
    """Thin async wrapper around a ``QdrantClient`` (injectable for tests)."""

    def __init__(self, client: Any, collection_name: str | None = None) -> None:
        self._client = client
        self._collection = collection_name or settings.QDRANT_COLLECTION_NAME

    @property
    def collection_name(self) -> str:
        return self._collection

    @classmethod
    def from_settings(cls) -> "QdrantService":
        if not settings.QDRANT_URL.strip():
            raise QdrantError("QDRANT_URL is not configured.")
        from qdrant_client import QdrantClient

        try:
            client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
            )
        except Exception as exc:
            raise QdrantError("Could not connect to Qdrant.") from exc
        return cls(client)

    async def ensure_collection(self, vector_size: int) -> None:
        """Create the collection if missing; handle size mismatch explicitly.

        A size mismatch means the collection was built for a different
        embedding model — its vectors are unusable with the current one, so
        blind upserts are refused. In development the stale collection is
        deleted and recreated at the expected size (affected repositories
        must be re-indexed); outside development a clear migration error is
        raised and nothing is destroyed.
        """
        from qdrant_client import models

        def _create() -> None:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE
                ),
            )

        def _ensure_payload_index() -> None:
            for field_name in (
                _REPOSITORY_ID_INDEX_FIELD,
                "snapshot_id",
            ):
                try:
                    self._client.create_payload_index(
                        collection_name=self._collection,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                except Exception as exc:
                    message = str(exc).lower()
                    if "already exists" in message or "already exist" in message:
                        continue
                    if field_name != _REPOSITORY_ID_INDEX_FIELD:
                        # snapshot_id index is best-effort on older servers;
                        # snapshot scoping still filters correctly without it.
                        logger.warning(
                            "qdrant_snapshot_index_skipped collection=%s error=%s",
                            self._collection,
                            type(exc).__name__,
                        )
                        continue
                    raise QdrantError(
                        "Could not create the repository_id payload index."
                    ) from exc

        def _run() -> str:
            try:
                existing = self._client.get_collection(self._collection)
            except Exception:
                existing = None
            if existing is not None:
                params = getattr(existing, "config", None)
                vec = getattr(params, "params", None)
                vectors = getattr(vec, "vectors", None) if vec else None
                current = getattr(vectors, "size", None)
                if current is not None and current != vector_size:
                    if settings.APP_ENV != "development":
                        raise QdrantError(
                            f"Qdrant collection {self._collection!r} has vector "
                            f"size {current}, expected {vector_size}. Recreate "
                            f"the collection and re-index repositories."
                        )
                    logger.warning(
                        "qdrant_collection_recreating collection=%s "
                        "old_size=%d new_size=%d",
                        self._collection,
                        current,
                        vector_size,
                    )
                    self._client.delete_collection(self._collection)
                    _create()
                    _ensure_payload_index()
                    return "recreated"
                _ensure_payload_index()
                return "ready"
            _create()
            _ensure_payload_index()
            return "created"

        try:
            outcome = await asyncio.to_thread(_run)
        except QdrantError:
            raise
        except Exception as exc:
            raise QdrantError("Could not prepare Qdrant collection.") from exc
        logger.info(
            "qdrant_collection_ready collection=%s vector_size=%d outcome=%s",
            self._collection,
            vector_size,
            outcome,
        )

    async def upsert_chunks(
        self, chunks: list[IngestedChunk], vectors: list[list[float]]
    ) -> int:
        """Idempotent batch upsert. Returns the number of points written."""
        if len(chunks) != len(vectors):
            raise QdrantError("Chunks and vectors length mismatch.")
        if not chunks:
            return 0
        from qdrant_client import models

        points = [
            models.PointStruct(
                id=build_point_id(chunk),
                vector=vector,
                payload=build_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        count = 0

        def _run() -> None:
            nonlocal count
            for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                batch = points[i : i + _UPSERT_BATCH_SIZE]
                self._client.upsert(collection_name=self._collection, points=batch)
                count += len(batch)

        try:
            await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant upsert failed.") from exc
        logger.info(
            "qdrant_points_upserted collection=%s count=%d",
            self._collection,
            count,
        )
        return count

    async def search(
        self,
        query_vector: list[float],
        repository_id: str,
        limit: int,
        extra: MetadataFilter | None = None,
    ) -> list[ScoredHit]:
        """Vector search scoped to one repository (never global)."""
        if not repository_id.strip():
            raise QdrantError("repository_id is required for search.")
        capped = max(1, min(limit, settings.RETRIEVAL_MAX_TOP_K))
        query_filter = build_filter(repository_id, extra)

        def _run() -> list[ScoredHit]:
            points: list[Any] = []
            if hasattr(self._client, "query_points"):
                response = self._client.query_points(
                    collection_name=self._collection,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=capped,
                )
                points = list(getattr(response, "points", []))
            else:  # older qdrant-client API
                points = list(
                    self._client.search(
                        collection_name=self._collection,
                        query_vector=query_vector,
                        query_filter=query_filter,
                        limit=capped,
                    )
                )
            return [
                ScoredHit(
                    point_id=str(p.id),
                    score=float(p.score),
                    payload=dict(p.payload or {}),
                )
                for p in points
            ]

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant search failed.") from exc

    async def list_point_ids(self, repository_id: str) -> set[str]:
        """All point IDs currently indexed for a repository (stale cleanup)."""
        query_filter = build_filter(repository_id)

        def _run() -> set[str]:
            ids: set[str] = set()
            offset: Any = None
            while True:
                points, offset = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=query_filter,
                    limit=_SCROLL_LIMIT,
                    offset=offset,
                    with_vectors=False,
                )
                ids.update(str(p.id) for p in points)
                if offset is None:
                    break
            return ids

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant scroll failed.") from exc

    async def delete_point_ids(self, point_ids: set[str] | list[str]) -> None:
        ids: list[Any] = [str(pid) for pid in point_ids]
        if not ids:
            return
        from qdrant_client import models

        def _run() -> None:
            self._client.delete(
                collection_name=self._collection,
                points_selector=models.PointIdsList(points=ids),
            )

        try:
            await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant delete failed.") from exc
        logger.info(
            "qdrant_points_deleted collection=%s count=%d",
            self._collection,
            len(ids),
        )

    async def delete_repository(self, repository_id: str) -> None:
        """Delete every vector for one repository (scoped — never global).

        Single server-side filter delete: no scroll/download of points,
        so deletion works for unindexed repositories and never touches
        other repositories' vectors. A missing collection (or zero
        matching points) is idempotent success — there is nothing to
        remove. Genuine failures still raise :class:`QdrantError`.
        """
        if not repository_id.strip():
            raise QdrantError("repository_id is required.")
        from qdrant_client import models

        query_filter = build_filter(repository_id)

        def _run() -> None:
            self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(filter=query_filter),
            )

        try:
            await asyncio.to_thread(_run)
        except Exception as exc:
            if _is_missing_collection(exc):
                logger.info(
                    "qdrant_delete_no_collection collection=%s repository_id=%s",
                    self._collection,
                    repository_id,
                )
                return
            raise QdrantError("Qdrant delete failed.") from exc
        logger.info(
            "qdrant_repository_deleted collection=%s repository_id=%s",
            self._collection,
            repository_id,
        )

    async def delete_commit(self, repository_id: str, commit_sha: str) -> None:
        """Delete vectors for one repository commit (scoped)."""
        if not repository_id.strip() or not commit_sha.strip():
            raise QdrantError("repository_id and commit_sha are required.")
        from qdrant_client import models

        query_filter = build_filter(
            repository_id, MetadataFilter(commit_sha=commit_sha)
        )

        def _run() -> None:
            self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(filter=query_filter),
            )

        try:
            await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant delete failed.") from exc

    async def count(self, repository_id: str) -> int:
        """Number of indexed points for one repository."""
        query_filter = build_filter(repository_id)

        def _run() -> int:
            result = self._client.count(
                collection_name=self._collection,
                count_filter=query_filter,
            )
            return int(result.count)

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise QdrantError("Qdrant count failed.") from exc


# Re-exported field list so indexing/retrieval stay in sync with payloads.
PAYLOAD_FIELDS: tuple[str, ...] = (
    "repository_id",
    "snapshot_id",
    "commit_sha",
    "file_path",
    "path",
    "language",
    "symbol",
    "start_line",
    "end_line",
    "chunk_type",
    "content_hash",
    "is_generated",
    "content",
)
