"""Repository business logic. Every user-facing lookup is owner-aware."""

import logging
import os
import shutil
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.repository import Repository, RepositoryStatus
from app.exceptions import (
    DatabaseError,
    QdrantError,
    RepositoryNotFoundError,
    RepositoryValidationError,
)
from app.schemas.repository import RepositoryCreate, RepositoryUpdate
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


async def create_repository(
    session: AsyncSession, owner_id: str, data: RepositoryCreate
) -> Repository:
    local_path = os.path.normpath(data.local_path.strip()) if data.local_path else None
    repository = Repository(
        owner_id=owner_id,
        name=data.name,
        source_type=data.source_type,
        source_url=data.source_url.strip() if data.source_url else None,
        local_path=local_path,
        default_branch=data.default_branch,
        status=RepositoryStatus.PENDING,
    )
    session.add(repository)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise RepositoryValidationError(
            "A repository with this name already exists."
        ) from None
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.warning("Repository create failed error=%s", type(exc).__name__)
        raise DatabaseError from None
    await session.refresh(repository)
    return repository


async def get_repository(
    session: AsyncSession, owner_id: str, repository_id: UUID
) -> Repository:
    repository = await session.get(Repository, repository_id)
    if repository is None or repository.owner_id != owner_id:
        # Same response whether missing or owned by someone else.
        raise RepositoryNotFoundError
    return repository


async def list_repositories(
    session: AsyncSession, owner_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[Repository], int]:
    total = (
        await session.execute(
            select(func.count())
            .select_from(Repository)
            .where(Repository.owner_id == owner_id)
        )
    ).scalar_one()
    items = (
        await session.execute(
            select(Repository)
            .where(Repository.owner_id == owner_id)
            .order_by(Repository.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(items), total


async def update_repository(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    data: RepositoryUpdate,
) -> Repository:
    repository = await get_repository(session, owner_id, repository_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        repository.name = changes["name"].strip()
        if not repository.name:
            raise RepositoryValidationError("name must not be empty")
    if "source_url" in changes:
        repository.source_url = changes["source_url"]
    if "default_branch" in changes:
        repository.default_branch = changes["default_branch"]
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise RepositoryValidationError(
            "A repository with this name already exists."
        ) from None
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.warning("Repository update failed error=%s", type(exc).__name__)
        raise DatabaseError from None
    await session.refresh(repository)
    return repository


async def delete_repository(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    qdrant: QdrantService | None = None,
) -> None:
    """Delete metadata + scoped vectors + workspace (Gap #2).

    Vectors go first: if Qdrant cleanup fails the database row (and its
    vectors) stay intact, so the system never reports a deletion it did
    not perform. ``qdrant=None`` resolves from settings; when Qdrant is
    not configured there is nothing to clean and the step is skipped.
    """
    repository = await get_repository(session, owner_id, repository_id)
    service = qdrant
    if service is None and settings.QDRANT_URL.strip():
        service = QdrantService.from_settings()
    if service is None:
        logger.info(
            "repository_delete_skipped_vectors repository_id=%s reason=qdrant_unconfigured",
            repository_id,
        )
    else:
        try:
            await service.delete_repository(str(repository_id))
        except QdrantError:
            logger.warning(
                "repository_delete_vectors_failed repository_id=%s", repository_id
            )
            raise
    try:
        await session.delete(repository)
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.warning("Repository delete failed error=%s", type(exc).__name__)
        raise DatabaseError from None
    # Best-effort: a leftover workspace is re-derivable and never served.
    # Never fails the deletion — the database record is already gone.
    _remove_workspace_best_effort(repository_id)


def _remove_workspace_best_effort(repository_id: UUID) -> None:
    """Remove the repository's isolated workspace without failing deletion.

    The workspace root is derived from the validated repository UUID via
    :func:`workspace_for` — never from user input — and removal stays
    confined to ``<storage>/<repository-id>/``. A missing workspace is
    success (nothing to remove).
    """
    try:
        from app.services.ingestion import workspace_for

        workspace = workspace_for(repository_id)
        scope = workspace.parent
        # Confinement: scope must be exactly <storage>/<repository-id>.
        if scope.name != str(repository_id):
            logger.warning(
                "repository_workspace_scope_mismatch repository_id=%s",
                repository_id,
            )
            return
        shutil.rmtree(scope, ignore_errors=True)
    except Exception as exc:  # Best-effort cleanup — never fail the delete.
        logger.warning(
            "repository_workspace_cleanup_failed repository_id=%s error=%s",
            repository_id,
            type(exc).__name__,
        )


async def set_repository_status(
    session: AsyncSession,
    repository_id: UUID,
    status: RepositoryStatus,
    error_message: str | None = None,
) -> None:
    """Internal lifecycle transition for future indexing phases (no owner needed)."""
    repository = await session.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError
    repository.status = status
    repository.error_message = error_message
    await session.commit()
