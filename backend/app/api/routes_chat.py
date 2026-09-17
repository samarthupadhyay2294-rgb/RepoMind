"""Repository chat. Grounded read-only answers with file/line citations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import get_chat_trace, run_chat
from app.api.deps import get_current_owner_id
from app.db.session import get_db_session
from app.schemas.chat import ChatRequest, ChatResponse, ChatTraceResponse
from app.services import repositories as repository_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    repository = await repository_service.get_repository(
        session, owner_id, payload.repository_id
    )
    return await run_chat(repository, payload.question, session_id=payload.session_id)


@router.get("/{session_id}", response_model=ChatTraceResponse)
async def chat_trace(
    session_id: str = Path(min_length=1, max_length=64),
    repository_id: UUID = Query(...),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> ChatTraceResponse:
    repository = await repository_service.get_repository(
        session, owner_id, repository_id
    )
    return await get_chat_trace(repository, session_id)
