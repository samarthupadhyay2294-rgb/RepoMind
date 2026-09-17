"""Repository-scoped vector retrieval (Part 5 baseline).

Semantic Qdrant search + metadata filtering. Retrieved chunk content is
untrusted repository data: returned as evidence only, never executed.
"""

import logging
import time

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.exceptions import QdrantError
from app.rag.models import RetrievalResult
from app.services.qdrant_service import MetadataFilter, QdrantService

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self, provider: EmbeddingProvider, qdrant: QdrantService) -> None:
        self._provider = provider
        self._qdrant = qdrant

    @staticmethod
    def _scoped_filter(
        extra: MetadataFilter | None, snapshot_id: str | None
    ) -> MetadataFilter | None:
        """Merge the server-selected snapshot scope into the Qdrant filter.

        Client-provided filters are never trusted alone: the snapshot scope
        always comes from the server (active snapshot), never from the LLM
        or the HTTP client.
        """
        if snapshot_id is None:
            return extra
        if extra is None:
            return MetadataFilter(snapshot_id=snapshot_id)
        if extra.snapshot_id is not None and extra.snapshot_id != snapshot_id:
            # Client/caller scope conflict → server wins, loudly.
            raise QdrantError("snapshot scope mismatch for retrieval.")
        return MetadataFilter(
            commit_sha=extra.commit_sha,
            snapshot_id=snapshot_id,
            language=extra.language,
            file_path=extra.file_path,
            file_prefix=extra.file_prefix,
            chunk_type=extra.chunk_type,
        )

    async def search(
        self,
        repository_id: str,
        query: str,
        top_k: int | None = None,
        extra: MetadataFilter | None = None,
        snapshot_id: str | None = None,
    ) -> list[RetrievalResult]:
        """Embed the query and return citation-ready evidence (repo-scoped)."""
        if not repository_id.strip():
            raise QdrantError("repository_id is required for retrieval.")
        if not query.strip():
            raise QdrantError("query must not be empty.")
        scoped_extra = self._scoped_filter(extra, snapshot_id)
        limit = _cap_top_k(top_k)
        started = time.monotonic()
        query_vector = await self._provider.embed_query(query)
        hits = await self._qdrant.search(
            query_vector, repository_id, limit, scoped_extra
        )
        results = [
            RetrievalResult(
                content=str(hit.payload.get("content", "")),
                score=hit.score,
                repository_id=str(hit.payload.get("repository_id", repository_id)),
                file_path=str(hit.payload.get("file_path", "")),
                start_line=int(hit.payload.get("start_line", 1) or 1),
                end_line=int(hit.payload.get("end_line", 1) or 1),
                language=str(hit.payload.get("language", "")),
                symbol=hit.payload.get("symbol"),
                chunk_type=str(hit.payload.get("chunk_type", "")),
                commit_sha=hit.payload.get("commit_sha"),
                content_hash=str(hit.payload.get("content_hash", "")),
                snapshot_id=hit.payload.get("snapshot_id"),
            )
            for hit in hits
            if str(hit.payload.get("repository_id", repository_id)) == repository_id
            and (
                snapshot_id is None
                or hit.payload.get("snapshot_id") in (None, snapshot_id)
            )
        ]
        elapsed_ms = (time.monotonic() - started) * 1000
        # Query text never logged: repository content may be sensitive.
        logger.info(
            "retrieval_completed repository_id=%s count=%d latency_ms=%.1f",
            repository_id,
            len(results),
            elapsed_ms,
        )
        return results


def _cap_top_k(top_k: int | None) -> int:
    default = max(1, settings.RETRIEVAL_TOP_K)
    maximum = max(1, settings.RETRIEVAL_MAX_TOP_K)
    if top_k is None:
        return min(default, maximum)
    return max(1, min(top_k, maximum))


async def retrieve(
    repository_id: str,
    query: str,
    provider: EmbeddingProvider,
    qdrant: QdrantService,
    top_k: int | None = None,
    extra: MetadataFilter | None = None,
    snapshot_id: str | None = None,
) -> list[RetrievalResult]:
    """Convenience wrapper matching the Part 5 output contract."""
    return await Retriever(provider, qdrant).search(
        repository_id, query, top_k, extra, snapshot_id
    )
