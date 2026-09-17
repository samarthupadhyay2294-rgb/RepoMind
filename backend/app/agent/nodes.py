"""LangGraph nodes (Part 7). Dependencies arrive via
``config["configurable"]["deps"]`` (:class:`AgentDeps`) so the graph
structure is fixed while each request injects its own context — and tests
inject fakes. Nodes never touch the filesystem or Qdrant directly; all
repository access flows through Part 5 retrieval and Part 6 tools."""

import asyncio
import inspect
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent import prompts
from app.agent.injection import scan_evidence
from app.agent.models import (
    REQUEST_TYPES,
    SIMPLE_REQUEST_TYPES,
    Evaluation,
    InvestigationPlan,
    InvestigationStep,
    RequestClassification,
)
from app.agent.state import AgentState
from app.config import settings
from app.rag.models import RetrievalResult
from app.services.llm_models import LLMError
from app.tools.context import ToolContext
from app.tools.registry import (
    TOOLS,
    available_tool_names,
    capability_error,
    is_validation_available,
)

logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"`([^`\s:]+):(\d+)-(\d+)`")


@dataclass
class AgentDeps:
    """Per-request dependencies (never stored in graph state)."""

    invoke_llm: Callable[[str], str]
    retrieve: Callable[..., Awaitable[list[RetrievalResult]]]
    tool_context: ToolContext
    warnings: list[str] = field(default_factory=list)


def _deps(config: RunnableConfig) -> AgentDeps:
    return config["configurable"]["deps"]  # type: ignore[no-any-return]


def _parse_json_object(text: str) -> dict | None:
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _llm_json(invoke: Callable[[str], str], prompt: str) -> tuple[dict | None, bool]:
    """Parse one LLM JSON response.

    Returns ``(parsed, llm_failed)``: ``llm_failed`` is True only when the
    model call itself raised :class:`LLMError` (vs. unparseable output),
    so callers can distinguish provider outages from bad JSON (P4).
    """
    try:
        return _parse_json_object(invoke(prompt)), False
    except LLMError:
        return None, True


def _budget_chars(state: AgentState) -> int:
    return len(state["question"]) + sum(
        len(str(item.get("content", ""))) for item in state["evidence"]
    )


def enforce_evidence_budget(
    evidence: list[dict], warnings: list[str]
) -> tuple[list[dict], list[str]]:
    """Deduplicate then trim to AGENT_MAX_EVIDENCE_ITEMS/CHARS (top relevance first)."""
    max_items = max(1, settings.AGENT_MAX_EVIDENCE_ITEMS)
    max_chars = max(1024, settings.AGENT_MAX_EVIDENCE_CHARS)
    deduped: dict[tuple[str, str, int, int], dict] = {}
    for item in evidence:
        key = (
            str(item.get("repository_id", "")),
            str(item.get("file_path", "")),
            int(item.get("start_line", 1) or 1),
            int(item.get("end_line", 1) or 1),
        )
        current = deduped.get(key)
        if current is None or float(item.get("relevance_score", 0.0)) > float(
            current.get("relevance_score", 0.0)
        ):
            deduped[key] = item
    extra_warnings = list(warnings)
    if len(deduped) < len(evidence):
        extra_warnings.append(
            f"Removed {len(evidence) - len(deduped)} duplicate evidence item(s)."
        )
    ranked = sorted(
        deduped.values(),
        key=lambda e: (-float(e.get("relevance_score", 0.0)), str(e.get("file_path"))),
    )
    kept = ranked[:max_items]
    if len(ranked) > len(kept):
        extra_warnings.append(
            f"Evidence trimmed to {max_items} items; lower-relevance items dropped."
        )
    total = sum(len(str(e.get("content", ""))) for e in kept)
    if total > max_chars:
        remaining = max_chars
        for item in kept:
            content = str(item.get("content", ""))
            item["content"] = content[:remaining]
            remaining -= len(item["content"])
            if remaining <= 0:
                break
        extra_warnings.append("Evidence content truncated to fit the evidence budget.")
    return kept, extra_warnings


def injection_warnings(new_items: list[dict], repository_id: str) -> list[str]:
    """One summary warning per batch when evidence matches injection patterns."""
    hits = scan_evidence(new_items)
    if not hits:
        return []
    # Log counts only — never repository content.
    logger.warning(
        "agent_injection_flagged repository_id=%s items=%d",
        repository_id,
        len(hits),
    )
    locations = sorted(hits)[:5]
    suffix = "..." if len(hits) > 5 else ""
    return [
        f"{len(hits)} evidence item(s) matched possible prompt-injection pattern(s) "
        f"({', '.join(locations)}{suffix}); treated as data only."
    ]


# -- classify ---------------------------------------------------------------


async def classify_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    started = time.monotonic()
    parsed, _llm_failed = await asyncio.to_thread(
        _llm_json, deps.invoke_llm, prompts.classify_prompt(state["question"])
    )
    request_type = "general"
    # P2: default True preserves the legacy classify → retrieve edge whenever
    # the model omits the field or classification fails outright.
    needs_retrieval = True
    if parsed:
        try:
            classification = RequestClassification(**parsed)
            candidate = classification.request_type
            request_type = candidate if candidate in REQUEST_TYPES else "general"
            needs_retrieval = bool(classification.needs_retrieval)
        except Exception:
            request_type = "general"
    warnings = (
        ["Question classification fell back to 'general'."]
        if request_type == "general" and parsed is None
        else []
    )
    route = "retrieve" if needs_retrieval else "plan"
    logger.info(
        "agent_step node=classify repository_id=%s request_type=%s "
        "needs_retrieval=%s duration_ms=%.1f",
        state["repository_id"],
        request_type,
        needs_retrieval,
        (time.monotonic() - started) * 1000,
    )
    return {
        "request_type": request_type,
        "needs_retrieval": needs_retrieval,
        "warnings": warnings,
        "steps_taken": [
            f"classified as {request_type}",
            f"retrieval decision: {route} (agent-selected)",
        ],
    }


# -- retrieve ---------------------------------------------------------------


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    started = time.monotonic()
    top_k = min(settings.RETRIEVAL_TOP_K, settings.RETRIEVAL_MAX_TOP_K)
    warnings: list[str] = []
    evidence: list[dict] = []
    
    # For repository_improvement requests, use multiple focused queries
    if state.get("request_type") == "repository_improvement":
        focused_queries = [
            "architecture and main components",
            "error handling and validation",
            "tests and test coverage",
            "security and authentication",
            "configuration and environment",
            "API routes and endpoints",
        ]
        per_query_k = max(1, top_k // len(focused_queries))
        for query in focused_queries:
            try:
                results = await deps.retrieve(
                    repository_id=state["repository_id"],
                    query=query,
                    top_k=per_query_k,
                )
                for hit in results:
                    from app.evidence.redaction import redact_text as _redact_retrieval

                    redacted_content, was_redacted = _redact_retrieval(
                        hit.content[: settings.AGENT_MAX_TOOL_OUTPUT_CHARS]
                    )
                    evidence.append(
                        {
                            "source_type": "retrieval",
                            "repository_id": hit.repository_id,
                            "file_path": hit.file_path,
                            "start_line": hit.start_line,
                            "end_line": hit.end_line,
                            "content": redacted_content,
                            "relevance_score": float(hit.score) * 0.9,  # Slightly lower for focused queries
                            "tool_name": None,
                            "redacted": was_redacted,
                        }
                    )
            except Exception as exc:
                logger.warning(
                    "agent_retrieval_failed repository_id=%s query=%s error=%s",
                    state["repository_id"],
                    query[:50],
                    type(exc).__name__,
                )
        warnings.append(f"Used {len(focused_queries)} focused retrieval queries for repository improvement.")
    else:
        # Standard single-query retrieval for other request types
        try:
            results = await deps.retrieve(
                repository_id=state["repository_id"],
                query=state["question"],
                top_k=top_k,
            )
        except Exception as exc:
            logger.warning(
                "agent_retrieval_failed repository_id=%s error=%s",
                state["repository_id"],
                type(exc).__name__,
            )
            warnings.append("Semantic retrieval is unavailable; continuing with tools.")
            results = []
        for hit in results:
            from app.evidence.redaction import redact_text as _redact_retrieval

            redacted_content, was_redacted = _redact_retrieval(
                hit.content[: settings.AGENT_MAX_TOOL_OUTPUT_CHARS]
            )
            evidence.append(
                {
                    "source_type": "retrieval",
                    "repository_id": hit.repository_id,
                    "file_path": hit.file_path,
                    "start_line": hit.start_line,
                    "end_line": hit.end_line,
                    "content": redacted_content,
                    "relevance_score": float(hit.score),
                    "tool_name": None,
                    "redacted": was_redacted,
                }
            )
    
    kept, warnings = enforce_evidence_budget([*state["evidence"], *evidence], warnings)
    warnings.extend(injection_warnings(evidence, state["repository_id"]))
    snapshot_id = state.get("snapshot_id", "")
    if snapshot_id:
        for item in kept:
            if not item.get("snapshot_id"):
                item["snapshot_id"] = snapshot_id
    logger.info(
        "agent_step node=retrieve repository_id=%s chunks=%d duration_ms=%.1f",
        state["repository_id"],
        len(evidence),
        (time.monotonic() - started) * 1000,
    )
    return {
        "evidence": kept,
        "warnings": warnings,
        "steps_taken": [f"retrieved {len(evidence)} chunks"],
    }


# -- plan -------------------------------------------------------------------


async def plan_node(state: AgentState, config: RunnableConfig) -> dict:
    started = time.monotonic()
    max_steps = max(1, settings.AGENT_MAX_STEPS)
    max_calls = max(1, settings.AGENT_MAX_TOOL_CALLS)
    warnings: list[str] = []
    if state["step_count"] >= max_steps or state["tool_call_count"] >= max_calls:
        warnings.append("Investigation budget reached; answering from evidence.")
        return {
            "current_plan": [],
            "step_count": state["step_count"] + 1,
            "warnings": warnings,
            "steps_taken": ["plan skipped: budget reached"],
        }
    deps = _deps(config)
    allowed = available_tool_names()
    summary = prompts.evidence_summary_block(state["evidence"], 6000)
    parsed, llm_failed = await asyncio.to_thread(
        _llm_json,
        deps.invoke_llm,
        prompts.plan_prompt(state["question"], state["request_type"], summary, allowed),
    )
    steps: list[dict] = []
    if parsed:
        try:
            raw_steps = parsed.get("steps", [])
            if isinstance(raw_steps, list):
                for entry in raw_steps:
                    # Tolerate the documented {"tool": ...} alias before
                    # schema validation so one alias can't sink the plan.
                    if isinstance(entry, dict) and "action" not in entry:
                        entry = {**entry, "action": entry.get("tool", "")}
            plan = InvestigationPlan(
                steps=raw_steps if isinstance(raw_steps, list) else []
            )
            for raw in plan.steps[:3]:
                coerced = coerce_plan_step(
                    raw.model_dump() if isinstance(raw, InvestigationStep) else raw
                )
                if coerced is None:
                    continue
                # P6: never hand the dispatcher a tool the deployment disabled.
                if coerced["action"] not in (*allowed, "semantic_retrieval"):
                    warnings.append(
                        f"Planner selected unavailable tool "
                        f"'{coerced['action']}'; step skipped."
                    )
                    continue
                steps.append(coerced)
        except Exception:
            steps = []
    if llm_failed:
        warnings.append("Planner model call failed; continuing without a plan.")
    logger.info(
        "agent_step node=plan repository_id=%s steps=%d duration_ms=%.1f",
        state["repository_id"],
        len(steps),
        (time.monotonic() - started) * 1000,
    )
    return {
        "current_plan": steps,
        "step_count": state["step_count"] + 1,
        "warnings": warnings,
        "steps_taken": [f"planned {len(steps)} steps"],
    }


# -- tool call --------------------------------------------------------------


_TOOL_TARGETS = {
    "search_code": "query",
    "read_file": "path",
    "list_directory": "path",
    "get_symbol": "symbol",
    "git_log": "path",
    "git_blame": "path",
    "find_references": "symbol",
    "dependency_graph": "path",
    "run_validation": "validation_id",
}


def _build_tool_args(action: str, target: object) -> dict | None:
    """Map a planner step onto validated tool kwargs (None → reject)."""
    if action not in TOOLS:
        return None
    if action in ("list_directory", "git_log", "dependency_graph") and not target:
        return {}
    if not isinstance(target, str) or not target.strip():
        return None
    cleaned = target.strip()
    if len(cleaned) > settings.MAX_SEARCH_QUERY_LENGTH:
        return None
    key = _TOOL_TARGETS[action]
    return {key: cleaned}


# -- structured tool arguments (P3) ------------------------------------------
#
# Specs are derived from the real tool signatures (``TOOLS[name].run``
# minus the leading ``ctx``), so the planner interface tracks the actual
# tool definitions. Unknown keys, missing required args, wrong types, and
# out-of-range integers reject the step before anything executes.
# Filesystem confinement stays inside the tools (safe_join / ToolContext);
# this layer only guarantees well-formed arguments.

_FORBIDDEN_ARG_KEYS = frozenset({"ctx", "context", "repository_id", "owner_id"})


def _tool_param_specs() -> dict[str, dict[str, tuple[bool, Any]]]:
    """{tool: {param: (required, annotation)}} from live tool signatures."""
    specs: dict[str, dict[str, tuple[bool, Any]]] = {}
    for name, tool_spec in TOOLS.items():
        params: dict[str, tuple[bool, Any]] = {}
        for pname, param in inspect.signature(tool_spec.run).parameters.items():
            if pname == "ctx":
                continue
            required = param.default is inspect.Parameter.empty
            params[pname] = (required, param.annotation)
        specs[name] = params
    return specs


_TOOL_PARAM_SPECS = _tool_param_specs()


def _check_int(name: str, value: object, minimum: int, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def resolve_tool_args(action: str, raw_args: object) -> dict | None:
    """Validate structured planner args for ``action`` (None → reject)."""
    if action not in TOOLS or not isinstance(raw_args, dict):
        return None
    spec = _TOOL_PARAM_SPECS[action]
    cleaned: dict[str, Any] = {}
    for key, value in raw_args.items():
        if key in _FORBIDDEN_ARG_KEYS or key not in spec:
            return None
        if value is None:
            continue  # absent optional; required-None fails below
        required, _annotation = spec[key]
        if key in ("start_line", "end_line", "max_results", "max_entries"):
            limit = (
                settings.MAX_READ_LINES
                if key in ("start_line", "end_line")
                else (
                    settings.MAX_SEARCH_RESULTS
                    if key == "max_results"
                    else settings.MAX_DIRECTORY_ENTRIES
                )
            )
            if not _check_int(key, value, 1, limit):
                return None
            cleaned[key] = value
        elif key == "recursive":
            if not isinstance(value, bool):
                return None
            cleaned[key] = value
        else:  # string-ish params: query/path/symbol/language/...
            if not isinstance(value, str) or not value.strip():
                return None
            text = value.strip()
            if len(text) > settings.MAX_SEARCH_QUERY_LENGTH or "\x00" in text:
                return None
            cleaned[key] = text
    for pname, (required, _annotation) in spec.items():
        if required and pname not in cleaned:
            return None
    if (
        "start_line" in cleaned
        and "end_line" in cleaned
        and cleaned["end_line"] < cleaned["start_line"]
    ):
        return None
    return cleaned


def coerce_plan_step(raw: object) -> dict | None:
    """Normalize one raw planner step to a storable dict (None → reject).

    Accepts legacy ``{action, target, purpose}`` and structured
    ``{action|tool, args, purpose}``. Structured ``args`` win when both
    forms are present; unknown actions are rejected here.
    """
    if not isinstance(raw, dict):
        return None
    action = raw.get("action") or raw.get("tool")
    if not isinstance(action, str) or not action.strip():
        return None
    action = action.strip()
    raw_args = raw.get("args")
    args_dict: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
    raw_target = raw.get("target", "")
    target = raw_target if isinstance(raw_target, str) else ""
    if action == "semantic_retrieval":
        return {
            "action": action,
            "target": target,
            "purpose": str(raw.get("purpose", ""))[:500],
            "args": args_dict,
        }
    if action not in TOOLS:
        return None
    try:
        step = InvestigationStep(
            action=action,
            target=target,
            purpose=str(raw.get("purpose", ""))[:500],
            args=args_dict,
        )
    except Exception:
        return None
    return step.model_dump()


# -- prose citation support check (P1) ----------------------------------------


def find_unsupported_refs(
    answer: str,
    evidence: list[dict],
    repository_id: str,
    snapshot_id: str | None = None,
) -> list[str]:
    """Backticked ``path:start-end`` refs in prose lacking evidence overlap.

    A ref is supported only when some evidence item matches the same
    repository, the same file path, and an overlapping line range —
    the same rule :func:`validate_citations` enforces. Evidence from
    another repository never satisfies a citation. Returns the exact
    unsupported tokens (deduplicated, in order).
    """
    from app.evidence.citations import find_unsupported_prose_refs as _find

    return _find(answer, evidence, repository_id, snapshot_id)


def scrub_unsupported_refs(answer: str, unsupported: list[str]) -> str:
    """Remove unsupported citation tokens from prose (deterministic repair)."""
    scrubbed = answer
    for token in unsupported:
        scrubbed = scrubbed.replace(token, "")
    return re.sub(r"[ \t]{2,}", " ", scrubbed)


def _normalize_tool_result(
    tool_name: str, repository_id: str, result: object
) -> list[dict]:
    cap = max(1024, settings.AGENT_MAX_TOOL_OUTPUT_CHARS)
    from app.evidence.redaction import redact_text as _redact

    def item(
        file_path: str, start: int, end: int, content: str, score: float = 0.5
    ) -> dict:
        redacted_content, was_redacted = _redact(content[:cap])
        return {
            "source_type": "tool",
            "repository_id": repository_id,
            "file_path": file_path,
            "start_line": max(1, start),
            "end_line": max(1, end),
            "content": redacted_content,
            "relevance_score": score,
            "tool_name": tool_name,
            "redacted": was_redacted,
        }

    evidence: list[dict] = []

    def get(name: str) -> Any:
        return getattr(result, name, None)

    matches = get("matches")
    if isinstance(matches, list):  # search/get_symbol/find_references
        for match in matches:
            snippet = (
                getattr(match, "snippet", None)
                or getattr(match, "signature", None)
                or ""
            )
            evidence.append(
                item(
                    str(getattr(match, "file_path", "")),
                    int(getattr(match, "start_line", 1) or 1),
                    int(getattr(match, "end_line", 1) or 1),
                    str(snippet),
                )
            )
        return evidence
    if tool_name == "read_file":
        return [
            item(
                str(get("file_path") or ""),
                int(get("start_line") or 1),
                int(get("end_line") or 1),
                str(get("content") or ""),
                0.9,
            )
        ]
    if tool_name == "list_directory":
        entries = get("entries") or []
        content = "\n".join(
            f"{e.type} {e.path}"
            for e in entries[:100]  # type: ignore[union-attr]
        )
        return [item(str(get("path") or ""), 1, 1, content)]
    if tool_name in ("git_log",):
        commits = get("commits") or []
        content = "\n".join(
            f"{c.commit_sha[:8]} {c.author}: {c.message}"  # type: ignore[union-attr]
            for c in commits
        )
        return [item("", 1, 1, content)]
    if tool_name == "git_blame":
        lines = get("lines") or []
        content = "\n".join(
            f"{line.line} {line.commit_sha[:8]} {line.author}: {line.summary}"  # type: ignore[union-attr]
            for line in lines
        )
        return [item(str(get("file_path") or ""), 1, 1, content)]
    if tool_name == "dependency_graph":
        edges = get("edges") or []
        content = "\n".join(
            f"{e.source} -> {e.target}"  # type: ignore[union-attr]
            for e in edges
        )
        return [item("", 1, 1, content)]
    if tool_name == "run_validation":
        return [
            item(
                "",
                1,
                1,
                f"[{get('validation_id')}] exit={get('exit_code')} "
                f"timed_out={get('timed_out')}\n{get('output')}",
            )
        ]
    return evidence


async def _planned_retrieval(deps: AgentDeps, state: AgentState, step: dict) -> dict:
    """Execute a planner-requested semantic retrieval (P2).

    Returns ``{"evidence": [...], "record": {...}, "warning": str}``.
    ``repository_id`` always comes from graph state — a planner-supplied
    value is stripped with a warning and never honored.
    """
    record = {
        "tool_name": "semantic_retrieval",
        "arguments": {},
        "ok": False,
        "result_count": 0,
        "warning": "",
        "duration_ms": 0.0,
    }
    step_args = step.get("args")
    raw: dict[str, Any] = step_args if isinstance(step_args, dict) else {}
    warning = ""
    if "repository_id" in raw:
        warning = (
            "Planner-supplied repository_id ignored; retrieval stayed "
            "scoped to the chat repository."
        )
    query = raw.get("query", state["question"])
    if not isinstance(query, str) or not query.strip():
        record["warning"] = "rejected"
        return {
            "evidence": [],
            "record": record,
            "warning": "Rejected unsafe plan step: semantic_retrieval.",
        }
    query = query.strip()
    if len(query) > settings.MAX_SEARCH_QUERY_LENGTH:
        record["warning"] = "rejected"
        return {
            "evidence": [],
            "record": record,
            "warning": "Rejected unsafe plan step: semantic_retrieval.",
        }
    top_k = raw.get(
        "top_k", min(settings.RETRIEVAL_TOP_K, settings.RETRIEVAL_MAX_TOP_K)
    )
    if (
        not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or not 1 <= top_k <= max(1, settings.RETRIEVAL_MAX_TOP_K)
    ):
        record["warning"] = "rejected"
        return {
            "evidence": [],
            "record": record,
            "warning": "Rejected unsafe plan step: semantic_retrieval.",
        }
    record["arguments"] = {"query": query[:200], "top_k": top_k}
    started = time.monotonic()
    try:
        results = await deps.retrieve(
            repository_id=state["repository_id"],
            query=query,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning(
            "agent_planned_retrieval_failed repository_id=%s error=%s",
            state["repository_id"],
            type(exc).__name__,
        )
        record["warning"] = type(exc).__name__
        record["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
        return {
            "evidence": [],
            "record": record,
            "warning": "Planned semantic retrieval failed; continuing with other evidence.",
        }
    cap = max(1024, settings.AGENT_MAX_TOOL_OUTPUT_CHARS)
    from app.evidence.redaction import redact_text as _redact_planned

    evidence = []
    for hit in results:
        redacted_content, was_redacted = _redact_planned(hit.content[:cap])
        evidence.append(
            {
                "source_type": "retrieval",
                "repository_id": hit.repository_id,
                "file_path": hit.file_path,
                "start_line": hit.start_line,
                "end_line": hit.end_line,
                "content": redacted_content,
                "relevance_score": float(hit.score),
                "tool_name": "semantic_retrieval",
                "redacted": was_redacted,
            }
        )
    record["ok"] = True
    record["result_count"] = len(evidence)
    record["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        "agent_tool_completed tool=semantic_retrieval repository_id=%s duration_ms=%.1f",
        state["repository_id"],
        record["duration_ms"],
    )
    return {"evidence": evidence, "record": record, "warning": warning}


async def tool_call_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    ctx = deps.tool_context
    max_calls = max(1, settings.AGENT_MAX_TOOL_CALLS)
    seen = {
        (
            record.get("tool_name"),
            json.dumps(record.get("arguments", {}), sort_keys=True, default=str),
        )
        for record in state["tool_calls"]
    }
    new_evidence: list[dict] = []
    records: list[dict] = []
    warnings: list[str] = []
    calls = 0
    for step in state["current_plan"]:
        if state["tool_call_count"] + calls >= max_calls:
            warnings.append("Tool-call budget reached; skipping remaining steps.")
            break
        action = str(step.get("action", ""))
        # Unknown tools fail closed with a structured capability error the
        # evaluator can react to (never executed, never silent).
        if action not in (*TOOLS, "semantic_retrieval"):
            err = capability_error(action)
            warnings.append(f"Step skipped ({err['code']}): {err['message']}")
            records.append(
                {
                    "tool_name": action,
                    "arguments": {},
                    "ok": False,
                    "result_count": 0,
                    "warning": err["code"],
                    "duration_ms": 0.0,
                }
            )
            continue
        # P2: agent-selected semantic retrieval (same Qdrant path as the
        # fixed retrieve node; repository_id always comes from state).
        if action == "semantic_retrieval":
            outcome = await _planned_retrieval(deps, state, step)
            if outcome["warning"]:
                warnings.append(outcome["warning"])
            records.append(outcome["record"])
            new_evidence.extend(outcome["evidence"])
            if outcome["record"]["ok"]:
                calls += 1
            continue
        # P6: disabled validation must fail closed with a capability error,
        # never reach the tool implementation.
        if action == "run_validation" and not is_validation_available():
            message = (
                "run_validation is not available: ENABLED_VALIDATIONS is "
                "empty, so the tool refuses every call. Step skipped."
            )
            warnings.append(message)
            records.append(
                {
                    "tool_name": action,
                    "arguments": {},
                    "ok": False,
                    "result_count": 0,
                    "warning": "disabled",
                    "duration_ms": 0.0,
                }
            )
            continue
        # P3: structured args win; legacy single-target mapping otherwise.
        raw_args = step.get("args")
        if isinstance(raw_args, dict) and raw_args:
            args = resolve_tool_args(action, raw_args)
        else:
            args = _build_tool_args(action, step.get("target", ""))
        if args is None:
            warnings.append(f"Rejected unsafe plan step: {action}.")
            records.append(
                {
                    "tool_name": action,
                    "arguments": {},
                    "ok": False,
                    "result_count": 0,
                    "warning": "rejected",
                    "duration_ms": 0.0,
                }
            )
            continue
        key = (action, json.dumps(args, sort_keys=True, default=str))
        if key in seen:
            warnings.append(f"Skipped duplicate tool call: {action}.")
            continue
        seen.add(key)
        started = asyncio.get_event_loop().time()
        try:
            result = await asyncio.to_thread(TOOLS[action].run, ctx, **args)
            duration_ms = (asyncio.get_event_loop().time() - started) * 1000
            logger.info(
                "agent_tool_completed tool=%s repository_id=%s duration_ms=%.1f",
                action,
                state["repository_id"],
                duration_ms,
            )
            items = _normalize_tool_result(action, state["repository_id"], result)
            new_evidence.extend(items)
            records.append(
                {
                    "tool_name": action,
                    "arguments": args,
                    "ok": True,
                    "result_count": len(items),
                    "warning": "",
                    "duration_ms": round(duration_ms, 1),
                }
            )
            calls += 1
        except Exception as exc:
            duration_ms = (asyncio.get_event_loop().time() - started) * 1000
            logger.warning(
                "agent_tool_failed tool=%s repository_id=%s duration_ms=%.1f error=%s",
                action,
                state["repository_id"],
                duration_ms,
                type(exc).__name__,
            )
            warnings.append(f"Tool {action} failed; continuing with other evidence.")
            records.append(
                {
                    "tool_name": action,
                    "arguments": args,
                    "ok": False,
                    "result_count": 0,
                    "warning": type(exc).__name__,
                    "duration_ms": round(duration_ms, 1),
                }
            )
    kept, warnings = enforce_evidence_budget(
        [*state["evidence"], *new_evidence], warnings
    )
    warnings.extend(injection_warnings(new_evidence, state["repository_id"]))
    snapshot_id = state.get("snapshot_id", "")
    if snapshot_id:
        # Stamp the run's snapshot scope (server-selected, never planner
        # supplied); pre-existing evidence without a scope stays readable.
        for item in kept:
            if not item.get("snapshot_id"):
                item["snapshot_id"] = snapshot_id
    return {
        "evidence": kept,
        "tool_calls": records,
        "tool_call_count": state["tool_call_count"] + calls,
        "current_plan": [],
        "warnings": warnings,
        "steps_taken": [f"tool calls: {calls}"],
    }


# -- evaluate ---------------------------------------------------------------


# P4: consecutive unproductive evaluate rounds tolerated before stopping.
# One bad round (tool miss, unparseable JSON) must not end the investigation,
# but the loop always terminates via these caps plus the hard step/tool caps.
MAX_UNPRODUCTIVE_ROUNDS = 2


async def evaluate_node(state: AgentState, config: RunnableConfig) -> dict:
    started = time.monotonic()
    max_steps = max(1, settings.AGENT_MAX_STEPS)
    max_calls = max(1, settings.AGENT_MAX_TOOL_CALLS)
    warnings: list[str] = []
    evidence_count = len(state["evidence"])
    unproductive = int(state.get("unproductive_rounds", 0) or 0)
    judge_failures = int(state.get("judge_failures", 0) or 0)
    if evidence_count > int(state.get("last_eval_evidence_count", -1)):
        unproductive = 0  # fresh evidence resets the counter

    def _stop(
        reason: str, sufficient: bool, note: str, extra: list[str] | None = None
    ) -> dict:
        if extra:
            warnings.extend(extra)
        logger.info(
            "agent_stop repository_id=%s reason=%s sufficient=%s duration_ms=%.1f",
            state["repository_id"],
            reason,
            sufficient,
            (time.monotonic() - started) * 1000,
        )
        return {
            "sufficient": sufficient,
            "decision": "answer",
            "warnings": warnings,
            "steps_taken": [f"evaluated: {note}", f"stop: {reason}"],
            "last_eval_evidence_count": evidence_count,
            "stop_reason": reason,
            "unproductive_rounds": unproductive,
            "judge_failures": judge_failures,
        }

    def _continue(
        note: str, extra: list[str] | None = None, rounds: int | None = None
    ) -> dict:
        if extra:
            warnings.extend(extra)
        logger.info(
            "agent_step node=evaluate repository_id=%s sufficient=%s duration_ms=%.1f",
            state["repository_id"],
            False,
            (time.monotonic() - started) * 1000,
        )
        return {
            "sufficient": False,
            "decision": "plan",
            "warnings": warnings,
            "steps_taken": [f"evaluated: {note}"],
            "last_eval_evidence_count": evidence_count,
            "stop_reason": "",
            "unproductive_rounds": unproductive if rounds is None else rounds,
            "judge_failures": judge_failures,
        }

    # Hard safety limits first (P4: preserved, now named).
    if state["step_count"] >= max_steps:
        return _stop(
            "max_iterations",
            True,
            "budget reached",
            ["Investigation budget reached (max iterations); answering from evidence."],
        )
    if state["tool_call_count"] >= max_calls:
        return _stop(
            "max_tool_calls",
            True,
            "budget reached",
            ["Investigation budget reached (max tool calls); answering from evidence."],
        )
    if _budget_chars(state) > max(1024, settings.AGENT_TOKEN_BUDGET):
        return _stop(
            "budget_exhausted",
            True,
            "budget reached",
            [
                "Investigation budget reached (evidence budget); answering from evidence."
            ],
        )
    # No evidence yet: tools may still find something — keep going unless
    # repeated rounds stay empty.
    if not state["evidence"]:
        unproductive += 1
        if unproductive >= MAX_UNPRODUCTIVE_ROUNDS:
            records = state.get("tool_calls", [])
            if records and all(not r.get("ok", False) for r in records):
                return _stop(
                    "tool_failure",
                    False,
                    "tools failed",
                    ["All tool calls failed; answering honestly from no evidence."],
                )
            return _stop(
                "no_viable_next_action",
                False,
                "no evidence",
                ["No evidence collected; answering honestly."],
            )
        return _continue(
            "no evidence yet",
            ["No evidence yet; trying repository tools."],
            rounds=unproductive,
        )
    # No new evidence since last time: one stall is tolerated (the planner
    # sees the history and can pick a different tool); repeated stalls stop.
    if evidence_count == int(state.get("last_eval_evidence_count", -1)):
        unproductive += 1
        if unproductive >= MAX_UNPRODUCTIVE_ROUNDS:
            records = state.get("tool_calls", [])
            if records and all(not r.get("ok", False) for r in records):
                return _stop(
                    "tool_failure",
                    False,
                    "tools failed",
                    ["All tool calls failed; answering from available evidence."],
                )
            return _stop(
                "no_viable_next_action",
                False,
                "no progress",
                ["No new evidence after repeated rounds; answering from evidence."],
            )
        return _continue(
            "no progress",
            ["No new evidence this round; trying a different approach."],
            rounds=unproductive,
        )
    deps = _deps(config)
    summary = prompts.evidence_summary_block(state["evidence"], 8000)
    parsed, llm_failed = await asyncio.to_thread(
        _llm_json, deps.invoke_llm, prompts.evaluate_prompt(state["question"], summary)
    )
    sufficient = False
    if parsed:
        try:
            sufficient = Evaluation(**parsed).sufficient
        except Exception:
            parsed = None
    if sufficient:
        judge_failures = 0  # the judge worked; reset the outage counter
        logger.info(
            "agent_stop repository_id=%s reason=answer_sufficient duration_ms=%.1f",
            state["repository_id"],
            (time.monotonic() - started) * 1000,
        )
        return {
            "sufficient": True,
            "decision": "answer",
            "warnings": warnings,
            "steps_taken": ["evaluated: sufficient", "stop: answer_sufficient"],
            "last_eval_evidence_count": evidence_count,
            "stop_reason": "answer_sufficient",
            "unproductive_rounds": unproductive,
            "judge_failures": judge_failures,
        }
    if parsed is None:
        # Judgement itself failed: provider outages accumulate on their own
        # counter (evidence growth must not mask an ailing judge); bad JSON
        # counts as an unproductive round.
        if llm_failed:
            judge_failures += 1
            if judge_failures >= MAX_UNPRODUCTIVE_ROUNDS:
                return _stop(
                    "llm_error",
                    False,
                    "judgement failed",
                    [
                        "Evidence judgement unavailable (model call failed "
                        "repeatedly); answering from evidence."
                    ],
                )
            return _continue(
                "insufficient",
                ["Evidence judgement failed (model call failed); retrying."],
            )
        unproductive += 1
        if unproductive >= MAX_UNPRODUCTIVE_ROUNDS:
            return _stop(
                "no_viable_next_action",
                False,
                "judgement failed",
                ["Evidence judgement unparseable; answering from evidence."],
            )
        return _continue(
            "insufficient",
            ["Evidence judgement unparseable; retrying."],
            rounds=unproductive,
        )
    judge_failures = 0  # parseable verdict keeps the judge healthy
    logger.info(
        "agent_step node=evaluate repository_id=%s sufficient=%s duration_ms=%.1f",
        state["repository_id"],
        sufficient,
        (time.monotonic() - started) * 1000,
    )
    return {
        "sufficient": False,
        "decision": "plan",
        "warnings": warnings,
        "steps_taken": ["evaluated: insufficient"],
        "last_eval_evidence_count": evidence_count,
        "stop_reason": "",
        "unproductive_rounds": unproductive,
        "judge_failures": judge_failures,
    }


# -- answer -----------------------------------------------------------------


def validate_citations(
    answer: str,
    evidence: list[dict],
    repository_id: str,
    snapshot_id: str | None = None,
) -> list[dict]:
    """Keep only citations backed by collected evidence (same repo, overlap)."""
    from app.evidence.citations import CITATION_RE as _RE

    valid: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for match in _RE.finditer(answer):
        path, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        if start < 1 or end < start:
            continue
        key = (path, start, end)
        if key in seen:
            continue
        for item in evidence:
            if str(item.get("repository_id", "")) != repository_id:
                continue
            item_snap = item.get("snapshot_id")
            if (
                snapshot_id is not None
                and item_snap is not None
                and item_snap != snapshot_id
            ):
                continue
            item_path = str(item.get("path", item.get("file_path", "")) or "")
            if (
                item_path == path
                and int(item.get("start_line", 1)) <= end
                and int(item.get("end_line", 1)) >= start
            ):
                seen.add(key)
                valid.append(
                    {
                        "repository_id": repository_id,
                        "file_path": path,
                        "start_line": start,
                        "end_line": end,
                        "source_type": str(item.get("source_type", "")),
                        "reason": "Cited in answer; backed by collected evidence.",
                    }
                )
                break
    return valid


async def answer_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    started = time.monotonic()
    steps_taken = ["answered"]
    # P5: pack highest-relevance evidence first; never drop silently.
    block, meta = prompts.evidence_answer_block_with_meta(state["evidence"], 20000)
    warnings: list[str] = []
    if meta["truncated"]:
        warnings.append(
            f"Evidence truncated for answer: used {meta['items_used']}/"
            f"{meta['items_total']} items ({meta['chars_used']}/"
            f"{meta['chars_total']} chars); highest-relevance evidence kept. "
            "Ask a narrower question or name specific files for the rest."
        )
    # LLM failure here is fatal (controlled 503) — no answer to fabricate.
    answer = await asyncio.to_thread(
        deps.invoke_llm,
        prompts.answer_prompt(state["question"], block, state["request_type"]),
    )
    # P1: the prose itself is validated, not just the citations array.
    run_snapshot = state.get("snapshot_id") or None
    unsupported = find_unsupported_refs(
        answer, state["evidence"], state["repository_id"], run_snapshot
    )
    if unsupported:
        warnings.append(
            f"Answer contained {len(unsupported)} unsupported citation(s); "
            "requesting a grounded rewrite."
        )
        try:
            repaired = await asyncio.to_thread(
                deps.invoke_llm,
                prompts.answer_repair_prompt(
                    state["question"], block, answer, unsupported
                ),
            )
        except LLMError:
            repaired = ""
        if repaired and not find_unsupported_refs(
            repaired, state["evidence"], state["repository_id"], run_snapshot
        ):
            answer = repaired
            steps_taken.append("answer rewrite grounded")
        else:
            if repaired:
                answer = repaired
            unsupported = find_unsupported_refs(
                answer, state["evidence"], state["repository_id"], run_snapshot
            )
            answer = scrub_unsupported_refs(answer, unsupported)
            warnings.append(
                f"Removed {len(unsupported)} unsupported citation(s) from answer prose."
            )
            steps_taken.append("answer citation scrub applied")
    citations = validate_citations(
        answer, state["evidence"], state["repository_id"], run_snapshot
    )
    if not citations and state["evidence"]:
        warnings.append("Answer has no evidence-backed citations.")
    evidence_meta = {
        "evidence_items_total": int(meta["items_total"]),
        "evidence_items_used": int(meta["items_used"]),
        "evidence_truncated": bool(meta["truncated"]),
    }
    logger.info(
        "agent_step node=answer repository_id=%s citations=%d duration_ms=%.1f",
        state["repository_id"],
        len(citations),
        (time.monotonic() - started) * 1000,
    )
    return {
        "answer": answer,
        "citations": citations,
        "warnings": warnings,
        "steps_taken": steps_taken,
        "evidence_meta": evidence_meta,
    }


# -- routing ------------------------------------------------------------------


def route_after_classify(state: AgentState) -> str:
    """P2: the classifier decides whether semantic retrieval is needed.

    Part 1 flag ``AGENT_SELECTABLE_RETRIEVAL=false`` restores the legacy
    fixed-retrieval path (classify → retrieve always) for compatibility.
    """
    if not settings.AGENT_SELECTABLE_RETRIEVAL:
        return "retrieve"
    return "retrieve" if state.get("needs_retrieval", True) else "plan"


def route_after_retrieve(state: AgentState) -> str:
    if state["request_type"] in SIMPLE_REQUEST_TYPES:
        return "evaluate"
    return "plan"


def route_after_plan(state: AgentState) -> str:
    if not state["current_plan"]:
        return "evaluate"
    return "tool_call"


def route_after_evaluate(state: AgentState) -> str:
    decision = state.get("decision", "answer")
    return decision if decision in ("answer", "plan") else "answer"
