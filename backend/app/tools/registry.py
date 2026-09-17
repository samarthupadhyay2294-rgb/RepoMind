"""Central investigation-tool registry (Part 6 → consumed by Part 7).

Plain-function registry on purpose: inputs are typed, outputs are
pydantic models, so Part 7 can wrap each entry in a LangChain
``StructuredTool`` in one line without the tool core depending on
LangChain/LangGraph. No agent loop, planning, or orchestration here.

NOTE (vs prompt §38): LangChain tool decorators are intentionally NOT
used yet — a thin adapter belongs to Part 7 alongside the agent.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.tools import deps, files, git, search, symbols, validation

ToolFn = Callable[..., Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    run: ToolFn


TOOLS: dict[str, ToolSpec] = {
    "search_code": ToolSpec(
        "search_code",
        "Find lines containing a query string in one repository. "
        "Inputs: query, path_prefix?, language?, max_results?.",
        search.search_code,
    ),
    "read_file": ToolSpec(
        "read_file",
        "Read a line range of one repository file. "
        "Inputs: path, start_line?, end_line?.",
        files.read_file,
    ),
    "list_directory": ToolSpec(
        "list_directory",
        "List one repository directory (sorted, bounded). "
        "Inputs: path='.', recursive=False, max_entries?.",
        files.list_directory,
    ),
    "get_symbol": ToolSpec(
        "get_symbol",
        "Find class/function/method definitions by name. "
        "Inputs: symbol, path?, max_results?.",
        symbols.get_symbol,
    ),
    "git_log": ToolSpec(
        "git_log",
        "List recent commits, optionally touching a path. "
        "Inputs: path?, max_entries?. Read-only.",
        git.git_log,
    ),
    "git_blame": ToolSpec(
        "git_blame",
        "Per-line authorship for a bounded range of a file. "
        "Inputs: path, start_line?, end_line?. Read-only.",
        git.git_blame,
    ),
    "find_references": ToolSpec(
        "find_references",
        "Find word-boundary usages of a symbol. Inputs: symbol, max_results?.",
        symbols.find_references,
    ),
    "dependency_graph": ToolSpec(
        "dependency_graph",
        "Static import graph (Python AST, JS/TS imports). Never executes code. "
        "Inputs: path?.",
        deps.dependency_graph,
    ),
    "run_validation": ToolSpec(
        "run_validation",
        "Run one allowlisted check (pytest|ruff_check|mypy) in the workspace. "
        "Inputs: validation_id. No arbitrary commands.",
        validation.run_validation,
    ),
}


def get_tool(name: str) -> ToolSpec:
    """Fetch a registered tool by name (KeyError → unknown to Part 7)."""
    return TOOLS[name]


def tool_names() -> list[str]:
    return sorted(TOOLS)


def is_validation_available() -> bool:
    """True only when the run_validation allowlist enables at least one check.

    ``ENABLED_VALIDATIONS`` empty (the default) means the tool refuses every
    call, so the planner must not be offered it (P6).
    """
    return bool(settings.ENABLED_VALIDATIONS.strip())


def available_tool_names() -> list[str]:
    """Tool names the agent may actually select (P6).

    ``run_validation`` is advertised only when enabled; every other
    registered tool is always available.
    """
    return sorted(
        name for name in TOOLS if name != "run_validation" or is_validation_available()
    )


def capability_error(tool_name: str) -> dict[str, str]:
    """Structured capability error for unknown/disabled tools.

    Returned to the evaluator (never raised): the planner can react to
    ``code`` without parsing free text. No paths or secrets included.
    """
    if tool_name not in TOOLS:
        return {
            "code": "TOOL_UNKNOWN",
            "message": f"Unknown tool '{tool_name}'. Select only advertised tools.",
        }
    if tool_name == "run_validation" and not is_validation_available():
        return {
            "code": "TOOL_DISABLED",
            "message": (
                "run_validation is not available: ENABLED_VALIDATIONS is "
                "empty, so the tool refuses every call."
            ),
        }
    return {"code": "TOOL_OK", "message": ""}
