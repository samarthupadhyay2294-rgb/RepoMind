"""Repository CRUD. Registers metadata only — never clones or reads files."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner_id
from app.db.session import get_db_session
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
    RepositoryUpdate,
)
from app.services import indexing_service as indexing_service
from app.services import repositories as repository_service

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    repository = await repository_service.create_repository(session, owner_id, payload)
    return RepositoryResponse.model_validate(repository)


@router.get("", response_model=RepositoryListResponse)
async def list_repositories(
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> RepositoryListResponse:
    items, total = await repository_service.list_repositories(
        session, owner_id, limit=limit, offset=offset
    )
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: UUID,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    repository = await repository_service.get_repository(
        session, owner_id, repository_id
    )
    return RepositoryResponse.model_validate(repository)


@router.patch("/{repository_id}", response_model=RepositoryResponse)
async def update_repository(
    repository_id: UUID,
    payload: RepositoryUpdate,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    repository = await repository_service.update_repository(
        session, owner_id, repository_id, payload
    )
    return RepositoryResponse.model_validate(repository)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: UUID,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await repository_service.delete_repository(session, owner_id, repository_id)


@router.post("/{repository_id}/index", response_model=RepositoryResponse)
async def index_repository(
    repository_id: UUID,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Run the indexing pipeline synchronously; terminal status in response."""
    repository = await indexing_service.run_indexing(session, owner_id, repository_id)
    return RepositoryResponse.model_validate(repository)
