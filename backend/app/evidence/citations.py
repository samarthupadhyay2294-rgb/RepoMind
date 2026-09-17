"""Snapshot-aware citation + prose validation (Part 1 foundation).

Validates BOTH structured citations and source references appearing in
answer prose. A reference is supported only when validated evidence from
the SAME repository_id AND snapshot scope covers the same canonical path
with an overlapping line range. Unsupported references must be rewritten
or removed — never fabricated.
"""

from __future__ import annotations

import re
from typing import Any

CITATION_RE = re.compile(r"`([^`\s:]+):(\d+)-(\d+)`")


def _path_of(item: dict[str, Any]) -> str:
    return str(item.get("path", item.get("file_path", "")) or "")


def _snapshot_of(item: dict[str, Any]) -> Any:
    return item.get("snapshot_id")


def _supported(
    path: str,
    start: int,
    end: int,
    evidence: list[dict[str, Any]],
    repository_id: str,
    snapshot_id: str | None,
) -> bool:
    if start < 1 or end < start:
        return False
    for item in evidence:
        if str(item.get("repository_id", "")) != repository_id:
            continue
        item_snap = _snapshot_of(item)
        if (
            snapshot_id is not None
            and item_snap is not None
            and item_snap != snapshot_id
        ):
            continue
        if _path_of(item) != path:
            continue
        try:
            item_start = int(item.get("start_line", 1) or 1)
            item_end = int(item.get("end_line", item.get("start_line", 1)) or 1)
        except (TypeError, ValueError):
            continue
        if item_start <= end and item_end >= start:
            return True
    return False


def validate_structured_citations(
    citations: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    repository_id: str,
    snapshot_id: str | None = None,
) -> list[dict[str, Any]]:
    """Keep only citations backed by same-repo/snapshot overlapping evidence."""
    valid: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for citation in citations:
        try:
            path = str(citation.get("file_path", citation.get("path", "")))
            start = int(citation.get("start_line", 0))
            end = int(citation.get("end_line", 0))
        except (TypeError, ValueError):
            continue
        key = (path, start, end)
        if key in seen:
            continue
        if _supported(path, start, end, evidence, repository_id, snapshot_id):
            seen.add(key)
            valid.append(citation)
    return valid


def find_unsupported_prose_refs(
    answer: str,
    evidence: list[dict[str, Any]],
    repository_id: str,
    snapshot_id: str | None = None,
) -> list[str]:
    """Backticked ``path:start-end`` prose refs lacking evidence overlap."""
    unsupported: list[str] = []
    seen: set[str] = set()
    for match in CITATION_RE.finditer(answer or ""):
        token = match.group(0)
        if token in seen:
            continue
        seen.add(token)
        path, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        if not _supported(path, start, end, evidence, repository_id, snapshot_id):
            unsupported.append(token)
    return unsupported


def scrub_unsupported_refs(answer: str, unsupported: list[str]) -> str:
    """Remove unsupported citation tokens from prose (deterministic repair)."""
    scrubbed = answer or ""
    for token in unsupported:
        scrubbed = scrubbed.replace(token, "")
    return re.sub(r"[ \t]{2,}", " ", scrubbed)
