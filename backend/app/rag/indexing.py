"""Incremental indexing: Part 4 chunks → Groq embeddings → Qdrant.

Unchanged chunks (by ``content_hash``) are never re-embedded; stale points
from deleted files are removed only after the new state is safely upserted.
"""

import logging
import math

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.exceptions import EmbeddingError
from app.ingestion.models import IngestedChunk, IngestionResult
from app.rag.models import IndexingResult
from app.services.qdrant_service import QdrantService, build_point_id

logger = logging.getLogger(__name__)


def select_chunks_to_index(
    chunks: list[IngestedChunk], known_hashes: set[str] | None
) -> tuple[list[IngestedChunk], int]:
    """Split chunks into (to_index, skipped_count) using content hashes."""
    if not known_hashes:
        return list(chunks), 0
    to_index = [c for c in chunks if c.content_hash not in known_hashes]
    return to_index, len(chunks) - len(to_index)


def _validate_dimensions(vectors: list[list[float]]) -> None:
    """Fail fast when the provider output drifts from the configured dim.

    Runs before any Qdrant mutation: a model change must surface as a loud
    controlled error (→ repository FAILED with a clear message), never as a
    vector-size rejection deep in the upsert or — worse — silent corruption.
    Vectors are never padded, truncated, or reshaped to fit.
    """
    expected = settings.EMBEDDING_DIMENSION
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingError(
                f"Embedding dimension mismatch: expected {expected}, got {len(vector)}."
            )


async def index_repository(
    repository_id: str,
    ingestion_result: IngestionResult,
    provider: EmbeddingProvider,
    qdrant: QdrantService,
    known_hashes: set[str] | None = None,
    remove_stale: bool = True,
    snapshot_id: str | None = None,
) -> IndexingResult:
    """Index one ingestion result; returns per-run statistics."""
    result = IndexingResult(
        repository_id=repository_id,
        commit_sha=ingestion_result.commit_sha,
        files_processed=ingestion_result.files_processed,
        chunks_seen=len(ingestion_result.chunks),
    )
    chunks = [c for c in ingestion_result.chunks if c.repository_id == repository_id]
    if snapshot_id is not None:
        # Stamp the snapshot scope onto every chunk without re-embedding
        # existing data: stamping is metadata-only and idempotent.
        chunks = [c.model_copy(update={"snapshot_id": snapshot_id}) for c in chunks]
    result.chunks_seen = len(chunks)
    to_index, skipped = select_chunks_to_index(chunks, known_hashes)
    result.chunks_skipped = skipped
    if not to_index:
        logger.info(
            "indexing_skipped_unchanged repository_id=%s chunks=%d",
            repository_id,
            len(chunks),
        )
        return result

    texts = [c.content for c in to_index]
    vectors = await provider.embed_documents(texts)
    if len(vectors) != len(to_index):
        result.chunks_failed = len(to_index)
        return result
    result.embeddings_generated = len(vectors)
    batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
    result.embedding_batches = math.ceil(len(vectors) / batch_size)

    _validate_dimensions(vectors)

    await qdrant.ensure_collection(settings.EMBEDDING_DIMENSION)
    await qdrant.upsert_chunks(to_index, vectors)
    result.chunks_indexed = len(to_index)

    if remove_stale:
        # Runs after a successful upsert, scoped to this repository only:
        # indexed points absent from the current ingestion are deleted files.
        current_ids = {build_point_id(c) for c in chunks}
        indexed_ids = await qdrant.list_point_ids(repository_id)
        stale = indexed_ids - current_ids
        if stale:
            await qdrant.delete_point_ids(stale)
            result.stale_points_removed = len(stale)

    logger.info(
        "indexing_completed repository_id=%s indexed=%d skipped=%d failed=%d",
        repository_id,
        result.chunks_indexed,
        result.chunks_skipped,
        result.chunks_failed,
    )
    return result
