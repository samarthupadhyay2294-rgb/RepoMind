"""get_symbol / find_references: definition lookup and usage search.

Purpose: locate a class/function/method definition (with signature) and
find where a symbol is referenced — parser-aware where Part 4 supports
it (Python AST via stdlib), safe textual fallback everywhere else.
Inputs: repository_id (via context), symbol, path?, max_results?.
Output: GetSymbolResult / FindReferencesResult (bounded, cited snippets).
Limits: MAX_SEARCH_RESULTS, MAX_REFERENCE_RESULTS.
Security: discovery filters apply (secrets/binary/ignores never scanned);
symbol text is escaped into a word-boundary regex — never eval'd/executed.
Failures: empty symbol, no matches (empty result, not an error).
"""

import ast
import logging
import re
import time

from app.config import settings
from app.exceptions import ToolError
from app.ingestion import discovery
from app.ingestion.language import detect_language
from app.tools._common import (
    cap_limit,
    iter_match_lines,
    read_text_bounded,
    rel_posix,
    resolve_tool_path,
    snippet_around,
)
from app.tools.context import ToolContext
from app.tools.models import (
    FindReferencesResult,
    GetSymbolResult,
    ReferenceMatch,
    SymbolResult,
)

logger = logging.getLogger(__name__)

_FALLBACK_DEF = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:def|class|function|interface|type|struct)\s+([A-Za-z_][A-Za-z0-9_]*)"
)


def _validate_symbol(symbol: str) -> str:
    cleaned = symbol.strip()
    if not cleaned:
        raise ToolError("Symbol must not be empty.", code="TOOL_INVALID_QUERY")
    if len(cleaned) > settings.MAX_SEARCH_QUERY_LENGTH:
        raise ToolError(
            f"Symbol exceeds {settings.MAX_SEARCH_QUERY_LENGTH} characters.",
            code="TOOL_QUERY_TOO_LONG",
        )
    return cleaned


def _python_symbols(source: str) -> list[tuple[str, str, int, int, str]] | None:
    """(name, kind, start, end, signature) via stdlib AST; None if unparseable."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    found: list[tuple[str, str, int, int, str]] = []
    lines = source.splitlines()

    def signature_of(node: ast.AST, lineno: int) -> str:
        try:
            seg = ast.get_source_segment(source, node)
        except Exception:
            seg = None
        first = (seg or lines[lineno - 1] if 0 < lineno <= len(lines) else "").strip()
        return first[:300]

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            end = getattr(node, "end_lineno", None) or node.lineno
            found.append(
                (node.name, "class", node.lineno, end, signature_of(node, node.lineno))
            )
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            end = getattr(node, "end_lineno", None) or node.lineno
            kind = "method" if self.class_stack else "function"
            found.append(
                (node.name, kind, node.lineno, end, signature_of(node, node.lineno))
            )
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_def(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_def(node)

    Visitor().visit(tree)
    return found


def _fallback_symbols(
    lines: list[str], wanted: str
) -> list[tuple[str, str, int, int, str]]:
    out = []
    for lineno, line in enumerate(lines, start=1):
        match = _FALLBACK_DEF.match(line)
        if match and match.group(1) == wanted:
            out.append((wanted, "definition", lineno, lineno, line.strip()[:300]))
    return out


def get_symbol(
    ctx: ToolContext,
    symbol: str,
    path: str | None = None,
    max_results: int | None = None,
) -> GetSymbolResult:
    """Find definitions of ``symbol`` in one repository (AST first, regex fallback)."""
    wanted = _validate_symbol(symbol)
    limit = cap_limit(
        max_results, settings.MAX_SEARCH_RESULTS, settings.MAX_SEARCH_RESULTS
    )
    started = time.monotonic()
    matches: list[SymbolResult] = []
    truncated = False

    if path is not None:
        resolved = resolve_tool_path(ctx, path, must_be_file=True)
        targets = [(resolved, rel_posix(ctx, resolved))]
    else:
        targets = [
            (item.path, item.rel) for item in discovery.discover_files(ctx.root).files
        ]
    for abs_path, rel in targets:
        try:
            text = read_text_bounded(abs_path, rel, settings.MAX_FILE_SIZE_BYTES)
        except ToolError:
            continue
        language = detect_language(abs_path.name)
        parsed = _python_symbols(text) if language == "python" else None
        lines = text.splitlines()
        hits = (
            [s for s in (parsed or []) if s[0] == wanted]
            if parsed is not None
            else [
                (s[0], "definition", s[2], s[3], s[4])
                for s in _fallback_symbols(lines, wanted)
            ]
        )
        for name, kind, start, end, signature in hits:
            if len(matches) >= limit:
                truncated = True
                break
            matches.append(
                SymbolResult(
                    name=name,
                    kind=kind,
                    file_path=rel,
                    start_line=max(1, start),
                    end_line=max(1, end),
                    signature=signature,
                    fallback=parsed is None,
                )
            )
        if truncated:
            break
    logger.info(
        "tool_completed tool=get_symbol repository_id=%s matches=%d duration_ms=%.1f",
        ctx.repository_id,
        len(matches),
        (time.monotonic() - started) * 1000,
    )
    return GetSymbolResult(
        repository_id=ctx.repository_id,
        symbol=wanted,
        matches=matches,
        truncated=truncated,
    )


def find_references(
    ctx: ToolContext,
    symbol: str,
    max_results: int | None = None,
) -> FindReferencesResult:
    """Find word-boundary usages of ``symbol`` across one repository."""
    wanted = _validate_symbol(symbol)
    limit = cap_limit(
        max_results, settings.MAX_REFERENCE_RESULTS, settings.MAX_REFERENCE_RESULTS
    )
    started = time.monotonic()
    pattern = re.compile(rf"\b{re.escape(wanted)}\b")
    matches: list[ReferenceMatch] = []
    total = 0
    truncated = False
    for item in discovery.discover_files(ctx.root).files:
        try:
            text = item.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines(keepends=True)
        for lineno, _ in iter_match_lines(lines, pattern):
            total += 1
            if len(matches) < limit:
                _, end, snippet = snippet_around(lines, lineno, radius=0)
                matches.append(
                    ReferenceMatch(
                        file_path=item.rel,
                        start_line=lineno,
                        end_line=end,
                        snippet=snippet[:500],
                    )
                )
            else:
                truncated = True
                break
        if truncated:
            break
    logger.info(
        "tool_completed tool=find_references repository_id=%s matches=%d duration_ms=%.1f",
        ctx.repository_id,
        len(matches),
        (time.monotonic() - started) * 1000,
    )
    return FindReferencesResult(
        repository_id=ctx.repository_id,
        symbol=wanted,
        matches=matches,
        total_matches=total,
        truncated=truncated,
    )
