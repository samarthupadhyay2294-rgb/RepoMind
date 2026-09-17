"""Overview API: fetch latest overview, trigger generation.

Flag off → 403 OVERVIEW_DISABLED (chat/graph unaffected). Generation is
synchronous (same design as indexing): no new queue infrastructure.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner_id
from app.db.session import get_db_session
from app.exceptions import AppError
from app.overview import service as overview_service
from app.overview.schemas import OverviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repositories", tags=["overview"])


class GenerateRequest(BaseModel):
    snapshot_id: str | None = None


class ArchitectureMapResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    snapshot_active: bool = True
    components: list[dict] = Field(default_factory=list)
    data_flows: list[dict] = Field(default_factory=list)
    entry_points: list[dict] = Field(default_factory=list)


@router.get("/{repository_id}/architecture-map", response_model=ArchitectureMapResponse)
async def get_architecture_map(
    repository_id: UUID,
    snapshot_id: str | None = Query(None),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> ArchitectureMapResponse:
    """Lightweight component/flow map derived from the latest overview.

    No duplicate dependency dataset: the full symbol graph stays behind
    the Part 2 graph endpoints; this returns architecture-level nodes only.
    """
    overview_service.require_overview_enabled()
    snapshot, is_active = await overview_service.resolve_snapshot(
        session, owner_id, repository_id, snapshot_id
    )
    row = await overview_service.latest_overview(session, repository_id, snapshot.id)
    if row is None:
        raise AppError(
            "No overview for this snapshot yet. Generate one first.",
            code="OVERVIEW_NOT_FOUND",
            status_code=404,
        )
    return ArchitectureMapResponse(
        repository_id=str(repository_id),
        snapshot_id=str(snapshot.id),
        snapshot_active=is_active,
        components=[dict(c) for c in (row.components or [])],
        data_flows=[dict(f) for f in (row.data_flows or [])],
        entry_points=[dict(e) for e in (row.entry_points or [])],
    )


@router.get("/{repository_id}/overview", response_model=OverviewResponse)
async def get_overview(
    repository_id: UUID,
    snapshot_id: str | None = Query(None),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> OverviewResponse:
    overview_service.require_overview_enabled()
    snapshot, is_active = await overview_service.resolve_snapshot(
        session, owner_id, repository_id, snapshot_id
    )
    row = await overview_service.latest_overview(session, repository_id, snapshot.id)
    if row is None:
        raise AppError(
            "No overview for this snapshot yet. Generate one first.",
            code="OVERVIEW_NOT_FOUND",
            status_code=404,
        )
    return OverviewResponse(
        **overview_service.row_to_response(row, snapshot_active=is_active)
    )


@router.post("/{repository_id}/overview:generate", response_model=OverviewResponse)
async def generate_overview(
    repository_id: UUID,
    payload: GenerateRequest | None = None,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> OverviewResponse:
    overview_service.require_overview_enabled()
    snapshot_id = (payload.snapshot_id if payload else None) or None
    row = await overview_service.generate_overview(
        session, owner_id, repository_id, snapshot_id
    )
    _, is_active = await overview_service.resolve_snapshot(
        session, owner_id, repository_id, snapshot_id
    )
    return OverviewResponse(
        **overview_service.row_to_response(row, snapshot_active=is_active)
    )
