"""Tests for incremental agentic improvements (P1–P6). All mocked, no network.

P1 prose citation grounding · P2 agent-selectable retrieval · P3 structured
tool args · P4 loop exit logic · P5 truncation metadata · P6 validation visibility.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agent import prompts
from app.agent.graph import compile_graph
from app.agent.models import InvestigationStep
from app.agent.nodes import (
    MAX_UNPRODUCTIVE_ROUNDS,
    AgentDeps,
    answer_node,
    coerce_plan_step,
    evaluate_node,
    find_unsupported_refs,
    plan_node,
    resolve_tool_args,
    route_after_classify,
    tool_call_node,
    validate_citations,
)
from app.agent.state import initial_state
from app.config import settings as app_settings
from app.rag.models import RetrievalResult
from app.services.llm_models import LLMUnavailableError
from app.tools.context import make_context
from app.tools.registry import available_tool_names, is_validation_available

AUTH_PY = '"""Auth."""\n\n\ndef authenticate(name):\n    """Log in."""\n    return name == "admin"\n'


def ev(
    path: str = "src/auth.py",
    start: int = 4,
    end: int = 6,
    repo: str = "repo-a",
    score: float = 0.9,
) -> dict:
    return {
        "source_type": "tool",
        "repository_id": repo,
        "file_path": path,
        "start_line": start,
        "end_line": end,
        "content": "def authenticate(name):",
        "relevance_score": score,
        "tool_name": "read_file",
    }


def make_deps(
    repo_root: Path,
    llm,
    hits: list[RetrievalResult] | None = None,
    retrieve_exc: Exception | None = None,
    repository_id: str = "repo-a",
) -> AgentDeps:
    async def fake_retrieve(repository_id: str, query: str, top_k: int | None = None):
        if retrieve_exc is not None:
            raise retrieve_exc
        return list(hits or [])

    return AgentDeps(
        invoke_llm=llm,
        retrieve=fake_retrieve,
        tool_context=make_context(repository_id, repo_root),
    )


def run_graph(deps: AgentDeps, question: str, repo: str = "repo-a") -> dict:
    compiled = compile_graph(MemorySaver())
    return asyncio.run(
        compiled.ainvoke(
            initial_state(question, repo, "thread-imp"),
            config={"configurable": {"thread_id": "thread-imp", "deps": deps}},
        )
    )


def run_node(coro) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(AUTH_PY, encoding="utf-8")
    return root


# -- P1: prose citation grounding --------------------------------------------


def test_p1_valid_prose_citation_supported() -> None:
    assert (
        find_unsupported_refs("See `src/auth.py:4-6`.", [ev()], "repo-a") == []
    )


def test_p1_unsupported_file_citation() -> None:
    assert find_unsupported_refs(
        "See `src/other.py:1-2`.", [ev()], "repo-a"
    ) == ["`src/other.py:1-2`"]


def test_p1_unsupported_line_range() -> None:
    # Evidence covers lines 4-6 only; 7-10 does not overlap.
    assert find_unsupported_refs("See `src/auth.py:7-10`.", [ev()], "repo-a") == [
        "`src/auth.py:7-10`"
    ]


def test_p1_partial_overlap_supported() -> None:
    # 6-10 overlaps evidence 4-6 at line 6.
    assert (
        find_unsupported_refs("See `src/auth.py:6-10`.", [ev()], "repo-a") == []
    )


def test_p1_other_repository_never_satisfies() -> None:
    assert find_unsupported_refs(
        "See `src/auth.py:4-6`.", [ev(repo="repo-b")], "repo-a"
    ) == ["`src/auth.py:4-6`"]
    # And validate_citations agrees (defense in depth).
    assert validate_citations("See `src/auth.py:4-6`.", [ev(repo="repo-b")], "repo-a") == []


def test_p1_no_explicit_citations() -> None:
    assert find_unsupported_refs("Auth is handled centrally.", [ev()], "repo-a") == []


def test_p1_answer_rewrite_grounds_prose(repo_root: Path) -> None:
    """Mixed valid+invalid → one repair attempt → clean answer + citations."""

    def llm(prompt: str) -> str:
        if "Previous answer" in prompt:
            return "Fixed: see `src/auth.py:4-6`."
        return "See `src/auth.py:4-6` and `src/other.py:1-2`."

    state = initial_state("Where is auth?", "repo-a", "t")
    state["evidence"] = [ev()]
    out = run_node(
        answer_node(state, {"configurable": {"thread_id": "t", "deps": make_deps(repo_root, llm)}})
    )
    assert "`src/other.py:1-2`" not in out["answer"]
    assert "`src/auth.py:4-6`" in out["answer"]
    assert [c["file_path"] for c in out["citations"]] == ["src/auth.py"]
    assert any("unsupported" in w for w in out["warnings"])
    assert "answer rewrite grounded" in out["steps_taken"]


def test_p1_answer_scrub_when_repair_fails(repo_root: Path) -> None:
    """Unfixable prose → deterministic scrub, valid refs preserved."""

    def llm(prompt: str) -> str:
        return "See `src/auth.py:4-6` and `src/other.py:1-2`."

    state = initial_state("Where is auth?", "repo-a", "t")
    state["evidence"] = [ev()]
    out = run_node(
        answer_node(state, {"configurable": {"thread_id": "t", "deps": make_deps(repo_root, llm)}})
    )
    assert "`src/other.py:1-2`" not in out["answer"]
    assert "`src/auth.py:4-6`" in out["answer"]
    assert any("Removed 1 unsupported" in w for w in out["warnings"])
    assert "answer citation scrub applied" in out["steps_taken"]


def test_p1_repair_llm_error_falls_back_to_scrub(repo_root: Path) -> None:
    calls = {"n": 0}

    def llm(prompt: str) -> str:
        calls["n"] += 1
        if "Previous answer" in prompt:
            raise LLMUnavailableError("Ollama is not reachable at x.")
        return "See `src/auth.py:4-6` and `src/other.py:1-2`."

    state = initial_state("Where is auth?", "repo-a", "t")
    state["evidence"] = [ev()]
    out = run_node(
        answer_node(state, {"configurable": {"thread_id": "t", "deps": make_deps(repo_root, llm)}})
    )
    assert calls["n"] == 2
    assert "`src/other.py:1-2`" not in out["answer"]


# -- P2: agent-selectable retrieval -------------------------------------------


class _Canned:
    def __init__(self, request_type="general", needs_retrieval=None, plans=None,
                 sufficient=True, answer="done"):
        self.request_type = request_type
        self.needs_retrieval = needs_retrieval
        self.plans = list(plans or [])
        self.sufficient = sufficient
        self.answer = answer

    def __call__(self, prompt: str) -> str:
        if "classify repository questions" in prompt:
            body: dict = {"request_type": self.request_type, "confidence": 0.9}
            if self.needs_retrieval is not None:
                body["needs_retrieval"] = self.needs_retrieval
            return json.dumps(body)
        if "plan read-only" in prompt:
            steps = self.plans.pop(0) if self.plans else []
            return json.dumps({"steps": steps})
        if "judge whether" in prompt:
            return json.dumps({"sufficient": self.sufficient, "confidence": 0.9,
                               "missing_information": []})
        return self.answer


def _hit() -> RetrievalResult:
    return RetrievalResult(
        content="def authenticate(name):", score=0.9, repository_id="repo-a",
        file_path="src/auth.py", start_line=4, end_line=6,
    )


def test_p2_retrieval_runs_by_default(repo_root: Path) -> None:
    llm = _Canned(request_type="general", answer="done `src/auth.py:4-6`.")
    final = run_graph(make_deps(repo_root, llm, [_hit()]), "where is auth?")
    assert any(s.startswith("retrieved ") for s in final["steps_taken"])
    assert any("retrieval decision: retrieve" in s for s in final["steps_taken"])


def test_p2_retrieval_skipped_for_inspection_only(repo_root: Path) -> None:
    llm = _Canned(request_type="general", needs_retrieval=False,
                  plans=[[{"action": "list_directory", "target": ".",
                            "purpose": "list files"}]],
                  answer="files listed.")
    final = run_graph(make_deps(repo_root, llm, [_hit()]), "list top-level files")
    assert not any(s.startswith("retrieved ") for s in final["steps_taken"])
    assert any("retrieval decision: plan" in s for s in final["steps_taken"])
    assert any(r.get("tool_name") == "list_directory" for r in final["tool_calls"])
    assert final["answer"]


def test_p2_route_after_classify() -> None:
    assert route_after_classify({"needs_retrieval": True}) == "retrieve"
    assert route_after_classify({"needs_retrieval": False}) == "plan"
    assert route_after_classify({}) == "retrieve"  # safe default


def test_p2_planned_retrieval_enforces_repository_scope(repo_root: Path) -> None:
    seen: dict = {}

    async def spy(repository_id: str, query: str, top_k: int | None = None):
        seen["repository_id"] = repository_id
        return [_hit()]

    deps = AgentDeps(invoke_llm=lambda p: "x",
                     retrieve=spy,
                     tool_context=make_context("repo-a", repo_root))
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [{
        "action": "semantic_retrieval",
        "target": "",
        "purpose": "more evidence",
        "args": {"query": "auth", "top_k": 3, "repository_id": "repo-evil"},
    }]
    out = run_node(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert seen["repository_id"] == "repo-a"
    assert any("repository_id" in w for w in out["warnings"])
    assert out["tool_calls"][0]["ok"] is True
    assert out["evidence"][0]["source_type"] == "retrieval"


def test_p2_planned_retrieval_failure_is_safe(repo_root: Path) -> None:
    deps = make_deps(repo_root, lambda p: "x",
                     retrieve_exc=RuntimeError("qdrant down"))
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [{
        "action": "semantic_retrieval", "target": "", "purpose": "x",
        "args": {"query": "auth"},
    }]
    out = run_node(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert out["evidence"] == []
    assert out["tool_calls"][0]["ok"] is False
    assert any("failed" in w for w in out["warnings"])


# -- P3: structured tool arguments --------------------------------------------


def test_p3_coerce_legacy_and_structured() -> None:
    legacy = coerce_plan_step({"action": "read_file", "target": "a.py"})
    assert legacy is not None and legacy["args"] == {}
    structured = coerce_plan_step(
        {"tool": "read_file",
         "args": {"path": "a.py", "start_line": 2, "end_line": 5}})
    assert structured is not None and structured["action"] == "read_file"
    assert structured["args"] == {"path": "a.py", "start_line": 2, "end_line": 5}
    assert coerce_plan_step({"action": "nope", "target": "x"}) is None
    assert coerce_plan_step("junk") is None


def test_p3_resolve_read_file() -> None:
    assert resolve_tool_args(
        "read_file", {"path": "src/auth.py", "start_line": 20, "end_line": 40}
    ) == {"path": "src/auth.py", "start_line": 20, "end_line": 40}
    assert resolve_tool_args("read_file", {"path": "src/auth.py"}) == {
        "path": "src/auth.py"}
    assert resolve_tool_args("read_file", {"path": "  "}) is None  # blank
    assert resolve_tool_args("read_file", {}) is None  # missing required
    assert resolve_tool_args(
        "read_file", {"path": "a.py", "start_line": 10, "end_line": 5}
    ) is None  # inverted range
    assert resolve_tool_args("read_file", {"path": "a.py", "start_line": 0}) is None
    assert resolve_tool_args("read_file", {"path": "a.py", "bogus": 1}) is None
    assert resolve_tool_args(
        "read_file", {"path": "a.py", "repository_id": "other"}) is None


def test_p3_resolve_search_code() -> None:
    assert resolve_tool_args(
        "search_code",
        {"query": "401 Unauthorized", "path_prefix": "backend/", "language": "python"},
    ) == {"query": "401 Unauthorized", "path_prefix": "backend/", "language": "python"}
    assert resolve_tool_args("search_code", {}) is None
    assert resolve_tool_args("search_code", {"query": "x", "max_results": 0}) is None
    assert resolve_tool_args("search_code", {"query": "x", "max_results": "many"}) is None


def test_p3_resolve_other_tools() -> None:
    assert resolve_tool_args("get_symbol", {"symbol": "authenticate"}) == {
        "symbol": "authenticate"}
    assert resolve_tool_args("get_symbol", {"symbol": "x", "max_results": 5}) == {
        "symbol": "x", "max_results": 5}
    assert resolve_tool_args(
        "git_blame", {"path": "a.py", "start_line": 1, "end_line": 3}) == {
        "path": "a.py", "start_line": 1, "end_line": 3}
    assert resolve_tool_args("git_blame", {}) is None
    assert resolve_tool_args("git_log", {}) == {}
    assert resolve_tool_args("list_directory", {"path": ".", "recursive": True}) == {
        "path": ".", "recursive": True}
    assert resolve_tool_args("list_directory", {"path": ".", "recursive": "yes"}) is None
    assert resolve_tool_args("dependency_graph", {"path": "src"}) == {"path": "src"}
    assert resolve_tool_args("find_references", {"symbol": "f"}) == {"symbol": "f"}
    assert resolve_tool_args("run_validation", {"validation_id": "pytest"}) == {
        "validation_id": "pytest"}


def test_p3_structured_args_execute_end_to_end(repo_root: Path) -> None:
    deps = make_deps(repo_root, lambda p: "x")
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [{
        "action": "read_file", "target": "", "purpose": "inspect",
        "args": {"path": "src/auth.py", "start_line": 4, "end_line": 6},
    }]
    out = run_node(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert out["tool_calls"][0]["ok"] is True
    item = out["evidence"][0]
    assert (item["file_path"], item["start_line"], item["end_line"]) == (
        "src/auth.py", 4, 6)
    assert "authenticate" in item["content"]


def test_p3_investigation_step_model_defaults() -> None:
    step = InvestigationStep(action="search_code", target="q")
    assert step.args == {}
    assert step.model_dump()["args"] == {}


# -- P4: loop exit logic --------------------------------------------------------


def _eval_state(**overrides) -> dict:
    state = initial_state("q?", "repo-a", "t")
    state.update(overrides)
    return state


def test_p4_single_unproductive_round_continues(repo_root: Path) -> None:
    deps = make_deps(repo_root, lambda p: "x")
    cfg = {"configurable": {"thread_id": "t", "deps": deps}}
    state = _eval_state(evidence=[ev()], last_eval_evidence_count=1)
    first = run_node(evaluate_node(state, cfg))
    assert first["decision"] == "plan"
    assert first["stop_reason"] == ""
    assert first["unproductive_rounds"] == 1
    state.update(first)
    second = run_node(evaluate_node(state, cfg))
    assert second["decision"] == "answer"
    assert second["stop_reason"] == "no_viable_next_action"
    assert any("stop: no_viable_next_action" in s for s in second["steps_taken"])


def test_p4_stop_reasons(repo_root: Path) -> None:
    yes = _Canned(sufficient=True)

    def cfg(llm) -> dict:
        return {"configurable": {"thread_id": "t",
                                 "deps": make_deps(repo_root, llm)}}

    out = run_node(evaluate_node(_eval_state(evidence=[ev()]), cfg(yes)))
    assert out["stop_reason"] == "answer_sufficient"
    assert out["decision"] == "answer"

    out = run_node(evaluate_node(
        _eval_state(evidence=[ev()], step_count=app_settings.AGENT_MAX_STEPS),
        cfg(lambda p: "x")))
    assert out["stop_reason"] == "max_iterations"

    out = run_node(evaluate_node(
        _eval_state(evidence=[ev()], tool_call_count=app_settings.AGENT_MAX_TOOL_CALLS),
        cfg(lambda p: "x")))
    assert out["stop_reason"] == "max_tool_calls"


def test_p4_llm_error_stop_reason(repo_root: Path) -> None:
    def down(prompt: str) -> str:
        raise LLMUnavailableError("Ollama is not reachable at x.")

    cfg = {"configurable": {"thread_id": "t", "deps": make_deps(repo_root, down)}}
    # Fresh evidence, first judge failure → retry.
    state = _eval_state(evidence=[ev()], last_eval_evidence_count=0)
    first = run_node(evaluate_node(state, cfg))
    assert first["decision"] == "plan"
    assert first["judge_failures"] == 1
    state.update(first)
    # Tools still produce new evidence, but the judge keeps failing
    # (evidence growth must not mask the outage) → stop with llm_error.
    state["evidence"] = [ev(), ev(path="src/other.py", start=1, end=2)]
    second = run_node(evaluate_node(state, cfg))
    assert second["decision"] == "answer"
    assert second["stop_reason"] == "llm_error"


def test_p4_loop_always_terminates(repo_root: Path) -> None:
    llm = _Canned(request_type="general",
                  plans=[[ {"action": "search_code", "target": "auth",
                             "purpose": "x"} ]] * 1 + [[]] * 20,
                  sufficient=False, answer="stuck.")
    final = run_graph(make_deps(repo_root, llm, [_hit()]), "q?")
    assert any(s.startswith("stop: ") for s in final["steps_taken"])
    assert final["step_count"] <= app_settings.AGENT_MAX_STEPS
    assert final["tool_call_count"] <= app_settings.AGENT_MAX_TOOL_CALLS
    assert MAX_UNPRODUCTIVE_ROUNDS == 2


# -- P5: truncation metadata ------------------------------------------------------


def _big_items(n: int) -> list[dict]:
    items = []
    for i in range(n):
        item = ev(path=f"src/f{i}.py", score=float(n - i))
        item["content"] = "x" * 5000
        items.append(item)
    return items


def test_p5_under_limit_no_truncation() -> None:
    block, meta = prompts.evidence_answer_block_with_meta([ev()], 20000)
    assert meta == {
        "truncated": False, "items_total": 1, "items_used": 1,
        "chars_total": len(block), "chars_used": len(block),
    }
    assert "`src/auth.py:4-6`" in block


def test_p5_over_limit_reports_metadata() -> None:
    items = _big_items(10)
    block, meta = prompts.evidence_answer_block_with_meta(items, 20000)
    assert meta["truncated"] is True
    assert meta["items_total"] == 10
    assert 0 < meta["items_used"] < 10
    assert meta["chars_used"] <= 20000 < meta["chars_total"]


def test_p5_highest_relevance_kept() -> None:
    items = _big_items(10)
    block, meta = prompts.evidence_answer_block_with_meta(items, 20000)
    assert "`src/f0.py:" in block  # highest relevance survives
    assert "`src/f9.py:" not in block  # lowest relevance dropped first


def test_p5_answer_warns_on_truncation(repo_root: Path) -> None:
    state = initial_state("q?", "repo-a", "t")
    state["evidence"] = _big_items(10)
    out = run_node(
        answer_node(state, {"configurable": {"thread_id": "t",
                                             "deps": make_deps(repo_root, lambda p: "short answer")}}))
    assert any("Evidence truncated for answer: used" in w for w in out["warnings"])


# -- P6: validation visibility ------------------------------------------------------


def test_p6_validation_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "ENABLED_VALIDATIONS", "")
    assert is_validation_available() is False
    assert "run_validation" not in available_tool_names()
    assert "search_code" in available_tool_names()


def test_p6_validation_shown_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "ENABLED_VALIDATIONS", "pytest")
    assert is_validation_available() is True
    assert "run_validation" in available_tool_names()


def test_p6_plan_filters_disabled_validation(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "ENABLED_VALIDATIONS", "")
    llm = _Canned(request_type="general",
                  plans=[[ {"action": "run_validation", "target": "pytest",
                             "purpose": "verify"} ]],
                  answer="done.")
    state = initial_state("q?", "repo-a", "t")
    out = run_node(plan_node(state, {"configurable": {"thread_id": "t",
                                                      "deps": make_deps(repo_root, llm)}}))
    assert out["current_plan"] == []
    assert any("unavailable tool" in w for w in out["warnings"])


def test_p6_direct_disabled_validation_refused(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "ENABLED_VALIDATIONS", "")
    deps = make_deps(repo_root, lambda p: "x")
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [{
        "action": "run_validation", "target": "pytest", "purpose": "x",
        "args": {"validation_id": "pytest"},
    }]
    out = run_node(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert out["tool_calls"][0]["ok"] is False
    assert out["tool_calls"][0]["warning"] == "disabled"
    assert any("ENABLED_VALIDATIONS" in w for w in out["warnings"])
