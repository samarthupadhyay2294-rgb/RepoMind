"""LangGraph state (Part 7). Serializable data only — no clients,
sessions, or file handles — so runs checkpoint cleanly."""

from operator import add
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    question: str
    repository_id: str
    session_id: str
    request_type: str
    evidence: list[dict]  # overwritten (budget trim re-sorts; never appended blindly)
    steps_taken: Annotated[list[str], add]
    tool_calls: Annotated[list[dict], add]
    warnings: Annotated[list[str], add]
    step_count: int
    tool_call_count: int
    current_plan: list[dict]
    last_eval_evidence_count: int
    decision: str  # set by evaluate_node: "answer" | "plan"
    sufficient: bool
    answer: str
    citations: list[dict]
    # P2: agent-selected retrieval. True (default) preserves the legacy
    # classify → retrieve edge; False routes classify → plan directly.
    needs_retrieval: bool
    # Part 1: snapshot scoping for this run ("" = pre-snapshot legacy).
    snapshot_id: str
    # Part 1: explicit evidence-budget metadata (never silent truncation).
    evidence_meta: dict
    # P4: machine-readable loop outcome; "" while investigating.
    stop_reason: str
    # P4: consecutive unproductive evaluate rounds (no new evidence and
    # no successful parse). Resets when evidence grows.
    unproductive_rounds: int
    # P4: consecutive judge (LLM JSON) failures. Unlike unproductive_rounds,
    # this is NOT reset by new evidence — the judge must work regardless.
    judge_failures: int


def initial_state(question: str, repository_id: str, session_id: str) -> AgentState:
    return AgentState(
        question=question,
        repository_id=repository_id,
        session_id=session_id,
        request_type="general",
        evidence=[],
        steps_taken=[],
        tool_calls=[],
        warnings=[],
        step_count=0,
        tool_call_count=0,
        current_plan=[],
        last_eval_evidence_count=-1,
        decision="answer",
        sufficient=False,
        answer="",
        citations=[],
        needs_retrieval=True,
        snapshot_id="",
        evidence_meta={},
        stop_reason="",
        unproductive_rounds=0,
        judge_failures=0,
    )
