"""dependency_graph: bounded static import analysis (never executes code).

Purpose: answer "what does X import?" / "what depends on Y?" for Python
(AST) and JavaScript/TypeScript (regex over import/require/export-from).
Only repo-relative targets that resolve to real files become edges;
anything else is one shared "external:<name>" node per name — no network,
no installs, no resolution outside the repository.
Inputs: repository_id (via context), path? (start file or scan whole repo).
Output: DependencyGraph with capped nodes/edges + truncated flag.
Limits: MAX_DEPENDENCY_NODES, MAX_DEPENDENCY_EDGES, MAX_DEPENDENCY_DEPTH.
"""

import ast
import logging
import re
import time
from pathlib import Path

from app.config import settings
from app.exceptions import ToolError
from app.ingestion import discovery
from app.ingestion.language import detect_language
from app.tools._common import read_text_bounded, rel_posix, resolve_tool_path
from app.tools.context import ToolContext
from app.tools.models import DependencyEdge, DependencyGraph, DependencyNode

logger = logging.getLogger(__name__)

_JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+|require\s*\()\s*['"]([^'"]+)['"]"""
)
_PY_MAX_PARSE_BYTES = 524288


def _python_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _js_imports(source: str) -> list[str]:
    return [m.group(1) for m in _JS_IMPORT.finditer(source)]


def _resolve_target(ctx: ToolContext, importer: str, raw: str) -> str | None:
    """Map a raw import to a repo-relative file, else None (external)."""
    if raw.startswith("."):
        bases = [(Path(importer).parent / raw).as_posix()]
    else:
        # Root-relative absolute import (``from src.auth import x``) or bare
        # module (``import os``) — only the former resolves to a file.
        dotted = raw.replace(".", "/")
        bases = [dotted, f"src/{dotted}"]
    candidates: list[str] = []
    for base in bases:
        candidates += [base, base + ".py", base + ".ts", base + ".js", base + ".tsx"]
        candidates += [f"{base}/__init__.py", f"{base}/index.ts", f"{base}/index.js"]
    for candidate in candidates:
        try:
            resolved = resolve_tool_path(ctx, candidate)
        except ToolError:
            continue
        if resolved.is_file():
            return rel_posix(ctx, resolved)
    return None


def dependency_graph(ctx: ToolContext, path: str | None = None) -> DependencyGraph:
    """Build the static import graph for one file (BFS) or the whole repo."""
    started = time.monotonic()
    max_nodes = max(1, settings.MAX_DEPENDENCY_NODES)
    max_edges = max(1, settings.MAX_DEPENDENCY_EDGES)
    max_depth = max(0, settings.MAX_DEPENDENCY_DEPTH)

    if path is not None:
        resolved = resolve_tool_path(ctx, path, must_be_file=True)
        seeds = [rel_posix(ctx, resolved)]
    else:
        seeds = [
            item.rel
            for item in discovery.discover_files(ctx.root).files
            if item.language in ("python", "javascript", "typescript")
        ]
    nodes: dict[str, DependencyNode] = {}
    edges: list[DependencyEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    truncated = False

    def add_node(node_id: str, external: bool = False) -> bool:
        if node_id in nodes:
            return True
        if len(nodes) >= max_nodes:
            return False
        nodes[node_id] = DependencyNode(id=node_id, external=external)
        return True

    def add_edge(source: str, target: str) -> bool:
        if (source, target) in seen_edges:
            return True
        if len(edges) >= max_edges:
            return False
        seen_edges.add((source, target))
        edges.append(DependencyEdge(source=source, target=target))
        return True

    def imports_of(rel: str) -> list[str]:
        try:
            resolved = resolve_tool_path(ctx, rel, must_be_file=True)
        except ToolError:
            return []
        language = detect_language(Path(rel).name)
        if language not in ("python", "javascript", "typescript"):
            return []
        try:
            text = read_text_bounded(resolved, rel, _PY_MAX_PARSE_BYTES)
        except ToolError:
            return []
        if language == "python":
            return _python_imports(text)
        return _js_imports(text)

    # Whole-repo scan: every seed at depth 0 (no transitive walk needed —
    # each file's own imports are edges; transitives appear as their own rows).
    queue: list[tuple[str, int]] = [(seed, 0) for seed in seeds]
    queued: set[str] = set(seeds)
    while queue:
        rel, depth = queue.pop(0)
        if not add_node(rel):
            truncated = True
            break
        if depth > max_depth:
            continue
        for raw in imports_of(rel):
            target = _resolve_target(ctx, rel, raw)
            node_id = target if target is not None else f"external:{raw}"
            if not add_node(node_id, external=target is None):
                truncated = True
                break
            if not add_edge(rel, node_id):
                truncated = True
                break
            if target is not None and target not in queued and depth < max_depth:
                queued.add(target)
                queue.append((target, depth + 1))
        if truncated:
            break
    logger.info(
        "tool_completed tool=dependency_graph repository_id=%s nodes=%d edges=%d truncated=%s duration_ms=%.1f",
        ctx.repository_id,
        len(nodes),
        len(edges),
        truncated,
        (time.monotonic() - started) * 1000,
    )
    return DependencyGraph(
        repository_id=ctx.repository_id,
        nodes=list(nodes.values()),
        edges=edges,
        truncated=truncated,
    )
