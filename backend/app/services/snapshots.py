"""Index-snapshot lifecycle (Part 1 shared foundation).

Rules:
- every indexing run creates a snapshot row (unique id, one repository);
- activation happens atomically only after successful indexing;
- a failed run never replaces the previous active snapshot;
- historical snapshots remain available (never mutated/deleted here);
- repositories without a Git revision use a deterministic manifest hash.
"""

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.repository import Repository
from app.db.models.snapshot import RepositoryIndexSnapshot, SnapshotStatus
from app.exceptions import RepositoryNotFoundError

logger = logging.getLogger(__name__)

PARSER_VERSION = "v1"


def manifest_hash_for(revision: str | None, file_hashes: dict[str, str] | None) -> str:
    """Deterministic manifest hash (fallback when no Git revision exists)."""
    if revision:
        return hashlib.sha256(f"rev:{revision}".encode()).hexdigest()[:64]
    material = "|".join(
        f"{path}:{digest}" for path, digest in sorted((file_hashes or {}).items())
    )
    return hashlib.sha256(f"manifest:{material}".encode()).hexdigest()[:64]


async def begin_snapshot(
    session: AsyncSession,
    repository_id: UUID,
    *,
    revision: str | None,
    file_hashes: dict[str, str] | None = None,
) -> RepositoryIndexSnapshot:
    """Create a new pending/indexing snapshot for one repository."""
    repository = await session.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError
    snapshot = RepositoryIndexSnapshot(
        repository_id=repository_id,
        revision=revision,
        manifest_hash=manifest_hash_for(revision, file_hashes),
        parser_version=PARSER_VERSION,
        embedding_model=settings.MISTRAL_EMBEDDING_MODEL,
        embedding_dimensions=settings.EMBEDDING_DIMENSION,
        status=SnapshotStatus.INDEXING,
        is_active=False,
        started_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    logger.info(
        "snapshot_begun repository_id=%s snapshot_id=%s revision=%s",
        repository_id,
        snapshot.id,
        revision or "manifest",
    )
    return snapshot


async def activate_snapshot(
    session: AsyncSession, snapshot_id: UUID
) -> RepositoryIndexSnapshot:
    """Atomically mark a ready snapshot active (deactivating siblings)."""
    snapshot = await session.get(RepositoryIndexSnapshot, snapshot_id)
    if snapshot is None:
        raise RepositoryNotFoundError
    siblings = (
        await session.execute(
            select(RepositoryIndexSnapshot).where(
                RepositoryIndexSnapshot.repository_id == snapshot.repository_id,
                RepositoryIndexSnapshot.is_active.is_(True),
            )
        )
    ).scalars()
    for sibling in siblings:
        if sibling.id != snapshot.id:
            sibling.is_active = False
    snapshot.status = SnapshotStatus.READY
    snapshot.is_active = True
    snapshot.completed_at = datetime.now(timezone.utc)
    repository = await session.get(Repository, snapshot.repository_id)
    if repository is not None:
        repository.active_snapshot_id = snapshot.id
    await session.commit()
    await session.refresh(snapshot)
    logger.info(
        "snapshot_activated repository_id=%s snapshot_id=%s",
        snapshot.repository_id,
        snapshot.id,
    )
    return snapshot


async def fail_snapshot(
    session: AsyncSession, snapshot_id: UUID, error_message: str | None = None
) -> RepositoryIndexSnapshot:
    """Mark a snapshot failed without touching the active snapshot."""
    snapshot = await session.get(RepositoryIndexSnapshot, snapshot_id)
    if snapshot is None:
        raise RepositoryNotFoundError
    snapshot.status = SnapshotStatus.FAILED
    snapshot.is_active = False
    snapshot.error_message = (error_message or "indexing failed")[:2000]
    snapshot.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(snapshot)
    logger.info(
        "snapshot_failed repository_id=%s snapshot_id=%s",
        snapshot.repository_id,
        snapshot.id,
    )
    return snapshot


async def get_active_snapshot(
    session: AsyncSession, repository_id: UUID
) -> RepositoryIndexSnapshot | None:
    """Return the active snapshot for a repository (None when absent)."""
    rows = (
        await session.execute(
            select(RepositoryIndexSnapshot)
            .where(
                RepositoryIndexSnapshot.repository_id == repository_id,
                RepositoryIndexSnapshot.is_active.is_(True),
            )
            .limit(1)
        )
    ).scalars()
    return next(iter(rows), None)


async def ensure_baseline_snapshot(
    session: AsyncSession,
    repository_id: UUID,
    *,
    revision: str | None = None,
    file_hashes: dict[str, str] | None = None,
) -> RepositoryIndexSnapshot:
    """Backfill-safe baseline: reuse the active snapshot or create+activate one.

    Used for repositories indexed before snapshots existed — no re-embedding,
    no data deletion; creates exactly one baseline row when none is active.
    """
    active = await get_active_snapshot(session, repository_id)
    if active is not None:
        return active
    snapshot = await begin_snapshot(
        session, repository_id, revision=revision, file_hashes=file_hashes
    )
    return await activate_snapshot(session, snapshot.id)
