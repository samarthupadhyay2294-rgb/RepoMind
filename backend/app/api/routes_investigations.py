"""Debug investigation API: create runs, fetch results.

Flag off → 403 INVESTIGATION_DISABLED (chat/graph/overview unaffected).
Runs execute the shared bounded agent loop synchronously (same design as
indexing/overview generation): no new queue infrastructure.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner_id
from app.db.session import get_db_session
from app.investigations import service as inv_service
from app.investigations.schemas import InvestigationCreate, InvestigationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repositories", tags=["investigations"])


@router.post("/{repository_id}/investigations", response_model=InvestigationResponse)
async def create_investigation(
    repository_id: UUID,
    payload: InvestigationCreate,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationResponse:
    inv_service.require_investigator_enabled()
    row = await inv_service.run_investigation(session, owner_id, repository_id, payload)
    _, actions = await inv_service.get_investigation(
        session, owner_id, repository_id, row.id
    )
    _, is_active = await inv_service.resolve_snapshot(
        session, owner_id, repository_id, payload.snapshot_id
    )
    return InvestigationResponse(
        **inv_service.row_to_response(row, actions, snapshot_active=is_active)
    )


@router.get(
    "/{repository_id}/investigations/{run_id}", response_model=InvestigationResponse
)
async def get_investigation(
    repository_id: UUID,
    run_id: UUID,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationResponse:
    inv_service.require_investigator_enabled()
    row, actions = await inv_service.get_investigation(
        session, owner_id, repository_id, run_id
    )
    _, is_active = await inv_service.resolve_snapshot(
        session, owner_id, repository_id, str(row.snapshot_id)
    )
    return InvestigationResponse(
        **inv_service.row_to_response(row, actions, snapshot_active=is_active)
    )
