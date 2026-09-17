"""Shared tool internals: path confinement, bounded reads, line scanning.

All repository-relative paths funnel through :func:`resolve_tool_path`
(Part 4 ``safe_join`` + symlink-containment), raising structured
``ToolError``s instead of ingestion errors.
"""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from app.config import settings
from app.exceptions import IngestionError, ToolError
from app.ingestion import filters
from app.ingestion.paths import is_within, safe_join
from app.tools.context import ToolContext

logger = logging.getLogger(__name__)


def resolve_tool_path(
    ctx: ToolContext, rel: str, *, must_be_file: bool = False
) -> Path:
    """Confine a tool-supplied path inside the repository (traversal/symlink-safe)."""
    if not rel.strip():
        raise ToolError("Path must not be empty.", code="TOOL_INVALID_PATH")
    try:
        resolved = safe_join(ctx.root, rel)
    except IngestionError as exc:
        logger.warning(
            "tool_path_rejected repository_id=%s input=%s",
            ctx.repository_id,
            rel[:200],
        )
        raise ToolError(str(exc), code="TOOL_PATH_REJECTED") from exc
    if resolved.is_symlink() and not is_within(ctx.root, resolved):
        logger.warning(
            "tool_path_rejected repository_id=%s symlink_escape", ctx.repository_id
        )
        raise ToolError(
            f"Path escapes the repository workspace: {rel}",
            code="TOOL_PATH_REJECTED",
        )
    if must_be_file and not resolved.is_file():
        raise ToolError(
            f"File not found: {rel}", code="TOOL_NOT_FOUND", status_code=404
        )
    return resolved


def rel_posix(ctx: ToolContext, path: Path) -> str:
    return path.resolve().relative_to(ctx.root.resolve()).as_posix()


def read_text_bounded(path: Path, rel: str, limit_bytes: int) -> str:
    """Read a text file up to ``limit_bytes``; rejects binary/unreadable."""
    if filters.looks_binary(path):
        raise ToolError(f"Binary file is not readable: {rel}", code="TOOL_BINARY_FILE")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolError(
            f"File not found: {rel}", code="TOOL_NOT_FOUND", status_code=404
        ) from exc
    if size > limit_bytes:
        raise ToolError(
            f"File exceeds {limit_bytes} bytes: {rel}", code="TOOL_FILE_TOO_LARGE"
        )
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(
            f"File cannot be read as text: {rel}", code="TOOL_UNREADABLE"
        ) from exc


def iter_match_lines(
    lines: list[str], pattern: re.Pattern[str]
) -> Iterator[tuple[int, str]]:
    for lineno, line in enumerate(lines, start=1):
        if pattern.search(line):
            yield lineno, line.rstrip("\n")


def snippet_around(
    lines: list[str], lineno: int, radius: int = 2
) -> tuple[int, int, str]:
    start = max(1, lineno - radius)
    end = min(len(lines), lineno + radius)
    return start, end, "".join(lines[start - 1 : end])[:2000]


def cap_limit(value: int | None, default: int, maximum: int) -> int:
    if value is None:
        return min(default, maximum)
    return max(1, min(value, maximum))


def max_search_results() -> int:
    return max(1, settings.MAX_SEARCH_RESULTS)
