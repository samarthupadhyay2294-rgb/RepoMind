"""search_code: bounded textual code search inside one repository.

Deterministic substring search over Part 4 discovery output (so ignores,
secret files, binary and size caps all apply). Semantic vector search
stays in Part 5 ``retrieve()`` — callers may pass those hits in via
``semantic_snippets``-style merging in Part 7; this tool never duplicates it.

Purpose: find where code lives ("Where is authenticate_user defined?").
Inputs: repository_id (via context), query, path_prefix?, language?, max_results?
Output: SearchCodeResult with file/line snippets (never whole files).
Limits: MAX_SEARCH_QUERY_LENGTH, MAX_SEARCH_RESULTS.
Failures: empty query, no matches (empty result, not an error).
"""

import logging
import re
import time

from app.config import settings
from app.exceptions import ToolError
from app.ingestion import discovery
from app.tools._common import cap_limit, iter_match_lines, snippet_around
from app.tools.context import ToolContext
from app.tools.models import CodeMatch, SearchCodeResult

logger = logging.getLogger(__name__)


def search_code(
    ctx: ToolContext,
    query: str,
    path_prefix: str | None = None,
    language: str | None = None,
    max_results: int | None = None,
) -> SearchCodeResult:
    """Search one repository for lines containing ``query`` (case-insensitive)."""
    cleaned = query.strip()
    if not cleaned:
        raise ToolError("Search query must not be empty.", code="TOOL_INVALID_QUERY")
    if len(cleaned) > settings.MAX_SEARCH_QUERY_LENGTH:
        raise ToolError(
            f"Query exceeds {settings.MAX_SEARCH_QUERY_LENGTH} characters.",
            code="TOOL_QUERY_TOO_LONG",
        )
    limit = cap_limit(
        max_results, settings.MAX_SEARCH_RESULTS, settings.MAX_SEARCH_RESULTS
    )
    started = time.monotonic()
    pattern = re.compile(re.escape(cleaned), re.IGNORECASE)
    found = discovery.discover_files(ctx.root)
    matches: list[CodeMatch] = []
    total = 0
    truncated = False
    for item in found.files:
        if path_prefix and not item.rel.startswith(path_prefix):
            continue
        if language and item.language != language:
            continue
        try:
            text = item.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines(keepends=True)
        for lineno, _ in iter_match_lines(lines, pattern):
            total += 1
            if len(matches) < limit:
                start, end, snippet = snippet_around(lines, lineno)
                matches.append(
                    CodeMatch(
                        file_path=item.rel,
                        start_line=start,
                        end_line=end,
                        snippet=snippet,
                    )
                )
            else:
                truncated = True
                break
        if truncated:
            break
    logger.info(
        "tool_completed tool=search_code repository_id=%s matches=%d truncated=%s duration_ms=%.1f",
        ctx.repository_id,
        len(matches),
        truncated,
        (time.monotonic() - started) * 1000,
    )
    return SearchCodeResult(
        repository_id=ctx.repository_id,
        matches=matches,
        total_matches=total,
        truncated=truncated,
    )
