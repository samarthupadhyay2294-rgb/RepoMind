"""read_file / list_directory: confined, bounded repository browsing.

Purpose: read exact line ranges (citable as file:lines) and explore
repository structure without dumping whole trees into agent context.
Inputs: repository_id (via context), path, start_line?/end_line?,
        recursive?, max_entries?.
Output: ReadFileResult / ListDirectoryResult with truncation flags.
Limits: MAX_READ_FILE_BYTES, MAX_READ_LINES, MAX_READ_OUTPUT_CHARS,
        MAX_DIRECTORY_ENTRIES. Recursive listing is depth-capped.
Security: Part 4 safe_join confinement (traversal + symlink escapes
rejected); secret/binary files never returned as text.
Failures: bad range, missing path, binary, too large, traversal rejected.
"""

import logging
import time
from pathlib import Path

from app.config import settings
from app.exceptions import ToolError
from app.ingestion.paths import is_within
from app.tools._common import read_text_bounded, rel_posix, resolve_tool_path
from app.tools.context import ToolContext
from app.tools.models import (
    DirectoryEntry,
    ListDirectoryResult,
    ReadFileResult,
)

logger = logging.getLogger(__name__)

_RECURSIVE_MAX_DEPTH = 5


def read_file(
    ctx: ToolContext,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> ReadFileResult:
    """Read a line range of one repository file (whole file if unasked)."""
    resolved = resolve_tool_path(ctx, path, must_be_file=True)
    rel = rel_posix(ctx, resolved)
    text = read_text_bounded(resolved, rel, settings.MAX_READ_FILE_BYTES)
    lines = text.splitlines()
    total = len(lines)
    first = start_line if start_line is not None else 1
    last = end_line if end_line is not None else total
    if first < 1 or last < 1 or first > last:
        raise ToolError(
            f"Invalid line range {first}-{last} for {rel}.",
            code="TOOL_INVALID_RANGE",
        )
    if first > total:
        raise ToolError(
            f"Line range {first}-{last} exceeds {total} lines in {rel}.",
            code="TOOL_INVALID_RANGE",
        )
    last = min(last, total)
    if last - first + 1 > settings.MAX_READ_LINES:
        last = first + settings.MAX_READ_LINES - 1
        truncated_by_lines = True
    else:
        truncated_by_lines = False
    content = "\n".join(lines[first - 1 : last])
    truncated = truncated_by_lines
    if len(content) > settings.MAX_READ_OUTPUT_CHARS:
        content = content[: settings.MAX_READ_OUTPUT_CHARS]
        truncated = True
    logger.info(
        "tool_completed tool=read_file repository_id=%s lines=%d truncated=%s",
        ctx.repository_id,
        last - first + 1,
        truncated,
    )
    return ReadFileResult(
        repository_id=ctx.repository_id,
        file_path=rel,
        start_line=first,
        end_line=last,
        content=content,
        truncated=truncated,
    )


def list_directory(
    ctx: ToolContext,
    path: str = ".",
    recursive: bool = False,
    max_entries: int | None = None,
) -> ListDirectoryResult:
    """List one directory (non-recursive by default); sorted, bounded."""
    started = time.monotonic()
    rel_arg = path.strip() or "."
    if rel_arg in (".", "./"):
        resolved = ctx.root
        rel = "."
    else:
        resolved = resolve_tool_path(ctx, rel_arg)
        rel = rel_posix(ctx, resolved)
    if not resolved.is_dir():
        raise ToolError(
            f"Directory not found: {rel_arg}", code="TOOL_NOT_FOUND", status_code=404
        )
    limit = (
        settings.MAX_DIRECTORY_ENTRIES
        if max_entries is None
        else max(1, min(max_entries, settings.MAX_DIRECTORY_ENTRIES))
    )
    entries: list[DirectoryEntry] = []
    truncated = False

    def visit(directory: Path, depth: int) -> bool:
        try:
            children = sorted(
                directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError as exc:
            raise ToolError(
                f"Directory cannot be listed: {rel_arg}", code="TOOL_UNREADABLE"
            ) from exc
        for child in children:
            if len(entries) >= limit:
                return True
            if child.is_symlink() and not is_within(ctx.root, child):
                continue  # escaping links are invisible, never followed
            child_rel = rel_posix(ctx, child)
            if child.is_dir():
                entries.append(
                    DirectoryEntry(name=child.name, path=child_rel, type="directory")
                )
                if recursive and depth < _RECURSIVE_MAX_DEPTH:
                    if visit(child, depth + 1):
                        return True
            elif child.is_file():
                entries.append(
                    DirectoryEntry(name=child.name, path=child_rel, type="file")
                )
        return False

    truncated = visit(resolved, 0)
    logger.info(
        "tool_completed tool=list_directory repository_id=%s entries=%d duration_ms=%.1f",
        ctx.repository_id,
        len(entries),
        (time.monotonic() - started) * 1000,
    )
    return ListDirectoryResult(
        repository_id=ctx.repository_id,
        path=rel,
        entries=entries,
        truncated=truncated,
    )
