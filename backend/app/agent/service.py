"""Chat orchestration (Part 7): validate → inject deps → run graph → respond.

Production wiring only (real Ollama + Part 5 retrieval + Part 6 context).
Tests bypass this module and drive the graph with fakes via ``config``.
"""

import logging
import time
import uuid
from typing import Any

from app.agent.graph import compile_graph, get_checkpointer, postgres_saver_cm
from app.agent.nodes import AgentDeps
from app.agent.state import initial_state
from app.db.models.repository import Repository
from app.rag.models import RetrievalResult
from app.rag.retrieval import retrieve as rag_retrieve
from app.exceptions import ToolError
from app.schemas.chat import (
    ChatCitation,
    ChatMetrics,
    ChatResponse,
    ChatTraceResponse,
)
from app.services.llm_models import get_primary_chat_model, invoke_chat_model
from app.services.qdrant_service import QdrantService
from app.tools.context import ToolContext, context_for_repository

logger = logging.getLogger(__name__)


def _production_deps(tool_context: ToolContext) -> AgentDeps:
    model = get_primary_chat_model()
    from app.embeddings.groq import get_embedding_provider

    provider = get_embedding_provider()
    qdrant = QdrantService.from_settings()

    async def retrieve(
        repository_id: str, query: str, top_k: int | None = None
    ) -> list[RetrievalResult]:
        return await rag_retrieve(repository_id, query, provider, qdrant, top_k)

    return AgentDeps(
        invoke_llm=lambda prompt: invoke_chat_model(model, prompt),
        retrieve=retrieve,
        tool_context=tool_context,
    )


async def _run_graph(
    repository: Repository,
    question: str,
    session_id: str | None = None,
    deps: AgentDeps | None = None,
) -> tuple[dict[str, Any], str, int, float]:
    """Invoke the agent graph; returns (final_state, session_id, llm_calls, latency_ms).

    Shared by chat and debug investigations so both features run the exact
    same bounded loop — no parallel agent implementation.
    """
    tool_context = context_for_repository(repository)
    sid = (session_id or "").strip() or uuid.uuid4().hex
    agent_deps = deps if deps is not None else _production_deps(tool_context)
    llm_calls = 0
    inner_invoke = agent_deps.invoke_llm

    def _counting_invoke(prompt: str) -> str:
        nonlocal llm_calls
        llm_calls += 1
        return inner_invoke(prompt)

    agent_deps.invoke_llm = _counting_invoke
    config = {"configurable": {"thread_id": sid, "deps": agent_deps}}
    state = initial_state(question.strip(), str(repository.id), sid)
    active_snapshot_id = getattr(repository, "active_snapshot_id", None)
    if active_snapshot_id:
        state["snapshot_id"] = str(active_snapshot_id)
    started = time.monotonic()
    cm = postgres_saver_cm()
    if cm is None:
        final = await compile_graph(get_checkpointer()).ainvoke(state, config=config)
    else:
        try:
            async with cm as saver:
                await saver.setup()
                final = await compile_graph(saver).ainvoke(state, config=config)
        except Exception as exc:
            # Checkpoint failure must not lose the chat: retry in-memory.
            logger.warning(
                "agent_checkpoint_fallback reason=postgres_failed error=%s",
                type(exc).__name__,
            )
            final = await compile_graph(get_checkpointer()).ainvoke(
                state, config=config
            )
    return final, sid, llm_calls, (time.monotonic() - started) * 1000


async def run_chat(
    repository: Repository,
    question: str,
    session_id: str | None = None,
    deps: AgentDeps | None = None,
) -> ChatResponse:
    """Run the investigation graph for one validated repository + question."""
    final, sid, llm_calls, latency_ms = await _run_graph(
        repository, question, session_id, deps
    )
    metrics = ChatMetrics(
        latency_ms=latency_ms,
        llm_calls=llm_calls,
        tool_calls=int(final.get("tool_call_count", 0) or 0),
        # steps_taken is the recorded trace; step_count only advances
        # inside the plan loop, so it undercounts short-circuited runs.
        steps=len(final.get("steps_taken", [])),
    )
    logger.info(
        "chat_completed repository_id=%s session_id=%s llm_calls=%d tool_calls=%d steps=%d latency_ms=%.1f",
        repository.id,
        sid,
        metrics.llm_calls,
        metrics.tool_calls,
        metrics.steps,
        metrics.latency_ms,
    )
    return ChatResponse(
        answer=final.get("answer", ""),
        citations=[ChatCitation(**c) for c in final.get("citations", [])],
        steps_taken=list(final.get("steps_taken", [])),
        warnings=list(final.get("warnings", [])),
        request_type=final.get("request_type", "general"),
        session_id=sid,
        metrics=metrics,
        snapshot_id=final.get("snapshot_id") or None,
        stop_reason=str(final.get("stop_reason", "") or ""),
        evidence_items_total=int(
            final.get("evidence_meta", {}).get("evidence_items_total", 0) or 0
        ),
        evidence_items_used=int(
            final.get("evidence_meta", {}).get("evidence_items_used", 0) or 0
        ),
        evidence_truncated=bool(
            final.get("evidence_meta", {}).get("evidence_truncated", False)
        ),
    )


async def get_chat_trace(repository: Repository, session_id: str) -> ChatTraceResponse:
    """Return the investigation trace for a past session (plan §12).

    Scoped by repository: a session from another repository (or a missing
    one) yields the same 404, revealing nothing about other owners' chats.
    """
    sid = (session_id or "").strip()
    if not sid:
        raise ToolError(
            "session_id is required.", code="CHAT_NOT_FOUND", status_code=404
        )
    config = {"configurable": {"thread_id": sid}}
    values: dict[str, Any] = {}
    cm = postgres_saver_cm()
    if cm is None:
        snapshot = await compile_graph(get_checkpointer()).aget_state(config)
        values = dict(snapshot.values) if snapshot else {}
    else:
        try:
            async with cm as saver:
                snapshot = await compile_graph(saver).aget_state(config)
                values = dict(snapshot.values) if snapshot else {}
        except Exception:
            snapshot = await compile_graph(get_checkpointer()).aget_state(config)
            values = dict(snapshot.values) if snapshot else {}
    if not values or values.get("repository_id") != str(repository.id):
        raise ToolError(
            "Chat session not found.", code="CHAT_NOT_FOUND", status_code=404
        )
    return ChatTraceResponse(
        session_id=sid,
        repository_id=str(repository.id),
        request_type=str(values.get("request_type", "general")),
        steps_taken=list(values.get("steps_taken", [])),
        warnings=list(values.get("warnings", [])),
        citations=[ChatCitation(**c) for c in values.get("citations", [])],
        answer=str(values.get("answer", "")),
    )
