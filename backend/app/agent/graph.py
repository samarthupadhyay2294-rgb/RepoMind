"""Graph construction (Part 7). Structure is built once; per-request
dependencies travel in ``config["configurable"]["deps"]`` so compiled
graphs are reusable and no client objects enter checkpointed state."""

import logging
from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("classify", nodes.classify_node)
    graph.add_node("retrieve", nodes.retrieve_node)
    graph.add_node("plan", nodes.plan_node)
    graph.add_node("tool_call", nodes.tool_call_node)
    graph.add_node("evaluate", nodes.evaluate_node)
    graph.add_node("answer", nodes.answer_node)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", nodes.route_after_classify, ["retrieve", "plan"]
    )
    graph.add_conditional_edges(
        "retrieve", nodes.route_after_retrieve, ["evaluate", "plan"]
    )
    graph.add_conditional_edges(
        "plan", nodes.route_after_plan, ["tool_call", "evaluate"]
    )
    graph.add_edge("tool_call", "evaluate")
    graph.add_conditional_edges(
        "evaluate", nodes.route_after_evaluate, ["answer", "plan"]
    )
    graph.add_edge("answer", END)
    return graph


def postgres_saver_cm() -> Any | None:
    """Postgres saver context manager when explicitly configured; else None.

    The caller enters it for the duration of the request (setup once per
    entry) and falls back to memory when configuration is absent. A prior
    failed/unusable configuration also yields None with a logged warning.
    """
    if settings.LANGGRAPH_CHECKPOINT_BACKEND != "postgres":
        return None
    if not settings.DATABASE_URL.strip():
        return None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        logger.warning("agent_checkpoint_fallback reason=postgres_package_missing")
        return None
    try:
        return AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
    except Exception as exc:
        logger.warning(
            "agent_checkpoint_fallback reason=postgres_unavailable error=%s",
            type(exc).__name__,
        )
        return None


@lru_cache(maxsize=2)
def _memory_checkpointer() -> MemorySaver:
    return MemorySaver()


def get_checkpointer() -> Any:
    """In-memory checkpointer (dev/test default; postgres is per-request)."""
    return _memory_checkpointer()


def compile_graph(checkpointer: Any | None = None) -> Any:
    return build_graph().compile(
        checkpointer=checkpointer
        if checkpointer is not None
        else _memory_checkpointer()
    )
