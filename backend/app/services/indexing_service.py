"""Synchronous indexing flow (Gap #3, minimal stage).

``run_indexing`` drives the existing pipeline end to end — acquire,
ingest, embed, Qdrant upsert — while moving the repository record through
``pending → indexing → indexed | failed``. It never leaves a repository
stuck in ``indexing``: every exit path writes a terminal status.

Synchronous by design for now: no Celery/Redis, no job table. Progress is
polled via ``GET /api/v1/repositories/{id}`` (the frontend already does
this). The pipeline stages are the same functions an async worker would
call, so a worker can wrap this service later without rewriting them.

There is intentionally no ``GET /jobs/{job_id}`` — with no persistent job
model a job id would be theater. See docs/architecture.md.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.repository import Repository, RepositoryStatus
from app.embeddings.base import EmbeddingProvider
from app.exceptions import AppError
from app.rag.indexing import index_repository as rag_index_repository
from app.services import repositories as repository_service
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


async def run_indexing(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    provider: EmbeddingProvider | None = None,
    qdrant: QdrantService | None = None,
) -> Repository:
    """Index one owned repository; returns it in a terminal status."""
    repository = await repository_service.get_repository(
        session, owner_id, repository_id
    )
    # Resolve the provider before any status change or pipeline work: a
    # missing MISTRAL_API_KEY fails fast with an actionable message instead
    # of surfacing late after ingestion/snapshot side effects. An explicitly
    # injected provider (tests, future workers) skips this check.
    try:
        from app.embeddings.groq import get_embedding_provider

        active_provider = provider or get_embedding_provider()
    except AppError as exc:
        # Prefix the machine-readable code so clients can detect the
        # configuration case without parsing prose. Field, shape, and
        # status semantics of the API are unchanged.
        message = f"[{exc.code}] {exc}"
        await repository_service.set_repository_status(
            session, repository_id, RepositoryStatus.FAILED, message[:500]
        )
        logger.warning(
            "indexing_rejected_missing_embedding_config repository_id=%s",
            repository_id,
        )
        finished = await session.get(Repository, repository_id)
        assert finished is not None
        await session.refresh(finished)
        return finished
    await repository_service.set_repository_status(
        session, repository_id, RepositoryStatus.INDEXING, error_message=None
    )
    snapshot = None
    try:
        from app.services.ingestion import ingest_repository

        active_qdrant = qdrant or QdrantService.from_settings()
        ingestion = ingest_repository(repository)
        # Part 1/2: one immutable snapshot per indexing run.
        from app.services import snapshots as snapshot_service

        snapshot = await snapshot_service.begin_snapshot(
            session,
            repository_id,
            revision=ingestion.commit_sha,
            file_hashes=ingestion.file_hashes,
        )
        for chunk in ingestion.chunks:
            if not chunk.snapshot_id:
                chunk.snapshot_id = str(snapshot.id)
        result = await rag_index_repository(
            str(repository_id), ingestion, active_provider, active_qdrant
        )
        # Part 2: deterministic graph extraction (never fails indexing).
        try:
            await _build_snapshot_graph(session, repository, snapshot.id)
        except Exception:
            logger.warning(
                "graph_extraction_failed repository_id=%s snapshot_id=%s",
                repository_id,
                snapshot.id,
            )
        await snapshot_service.activate_snapshot(session, snapshot.id)
        commit_sha = result.commit_sha or ingestion.commit_sha
        await repository_service.set_repository_status(
            session, repository_id, RepositoryStatus.INDEXED
        )
        if commit_sha:
            fresh = await session.get(Repository, repository_id)
            if fresh is not None:
                fresh.current_commit_sha = commit_sha
                await session.commit()
        logger.info(
            "indexing_succeeded repository_id=%s indexed=%d skipped=%d",
            repository_id,
            result.chunks_indexed,
            result.chunks_skipped,
        )
    except AppError as exc:
        # Controlled failure: message is ours (no secrets/URLs inside).
        # Prefix the machine-readable code (same convention as the
        # fail-fast path above) so clients can distinguish auth,
        # provider-outage, and configuration failures from stored state.
        message = f"[{exc.code}] {exc}"
        if snapshot is not None:
            try:
                from app.services import snapshots as _snap

                await _snap.fail_snapshot(session, snapshot.id, message[:500])
            except Exception:
                pass
        await repository_service.set_repository_status(
            session, repository_id, RepositoryStatus.FAILED, message[:500]
        )
        logger.warning(
            "indexing_failed repository_id=%s error=%s",
            repository_id,
            type(exc).__name__,
        )
    except Exception as exc:  # defensive: status must still land terminal
        if snapshot is not None:
            try:
                from app.services import snapshots as _snap2

                await _snap2.fail_snapshot(session, snapshot.id, "Indexing failed.")
            except Exception:
                pass
        await repository_service.set_repository_status(
            session, repository_id, RepositoryStatus.FAILED, "Indexing failed."
        )
        logger.warning(
            "indexing_failed repository_id=%s error=%s",
            repository_id,
            type(exc).__name__,
        )
    finished = await session.get(Repository, repository_id)
    assert finished is not None  # owned row fetched above; never deleted here
    await session.refresh(finished)
    return finished


async def _build_snapshot_graph(
    session: AsyncSession, repository: Repository, snapshot_id: UUID
) -> None:
    """Extract + persist the Part 2 graph for one snapshot (best-effort)."""
    from app.graph import extractor as graph_extractor
    from app.graph import service as graph_service
    from app.ingestion import discovery
    from app.ingestion.language import detect_language
    from app.tools.context import context_for_repository

    try:
        ctx = context_for_repository(repository)
    except Exception:
        return
    found = discovery.discover_files(ctx.root)
    files: dict[str, tuple[str, str | None]] = {}
    for item in found.files:
        if item.language not in ("python", "javascript", "typescript"):
            # Still index the file node so the graph degrades gracefully.
            try:
                text = item.path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files[item.rel] = (text[:200000], item.language)
            continue
        try:
            text = item.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files[item.rel] = (
            text[:524288],
            item.language or detect_language(item.path.name),
        )
    result = graph_extractor.extract_files(files)
    await graph_service.clear_snapshot_graph(session, repository.id, snapshot_id)
    await graph_service.persist_extraction(
        session, repository_id=repository.id, snapshot_id=snapshot_id, result=result
    )
    await session.commit()
