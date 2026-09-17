"""Evidence deduplication + ranking (Part 1 foundation).

Overlapping evidence (same repository/snapshot/path with heavily
overlapping line ranges) is merged so duplicate content is never sent to
the LLM twice. Provenance is preserved: the surviving item keeps the
strongest source (direct beats derived) and records merged source tools.
Ranking: directness → relevance → source quality → recency-agnostic order.
"""

from __future__ import annotations

from typing import Any

_DIRECT_KINDS = {"code"}
_SOURCE_QUALITY: dict[str, float] = {
    "read_file": 1.0,
    "semantic_search": 0.8,
    "semantic_retrieval": 0.8,
    "search_code": 0.7,
    "get_symbol": 0.7,
    "find_references": 0.6,
    "graph_neighbors": 0.6,
    "edge_evidence": 0.6,
    "git_blame": 0.5,
    "run_validation": 0.5,
    "list_directory": 0.4,
    "git_log": 0.4,
}


def _confidence(item: dict[str, Any]) -> str:
    return str(item.get("confidence", "derived") or "derived")


def _is_direct(item: dict[str, Any]) -> bool:
    if _confidence(item) == "direct":
        return True
    return str(item.get("source_type", "")) == "tool" and str(
        item.get("tool_name", "")
    ) in ("read_file",)


def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    lo, hi = max(a_start, b_start), min(a_end, b_end)
    overlap = max(0, hi - lo + 1)
    span = max(a_end - a_start + 1, b_end - b_start + 1, 1)
    return overlap / span


def _path_of(item: dict[str, Any]) -> str:
    return str(item.get("path", item.get("file_path", "")) or "")


def rank_key(item: dict[str, Any]) -> tuple:
    """Sort key: directness, relevance, source quality, path (stable)."""
    tool = str(item.get("source_tool", item.get("tool_name", "")) or "")
    return (
        0 if _is_direct(item) else 1,
        -float(item.get("relevance_score", 0.0) or 0.0),
        -_SOURCE_QUALITY.get(tool, 0.5),
        _path_of(item),
        int(item.get("start_line", 1) or 1),
    )


def deduplicate_evidence(
    items: list[dict[str, Any]], *, overlap_threshold: float = 0.5
) -> tuple[list[dict[str, Any]], int]:
    """Merge heavily-overlapping items. Returns (kept, duplicates_removed).

    Only items sharing repository_id, snapshot scope, and path are ever
    merged — cross-repository/snapshot evidence is never combined, and
    unique evidence is never removed.
    """
    kept: list[dict[str, Any]] = []
    removed = 0
    for item in items:
        merged = False
        for existing in kept:
            if existing.get("repository_id") != item.get("repository_id"):
                continue
            if (
                existing.get("snapshot_id") is not None
                or item.get("snapshot_id") is not None
            ) and (existing.get("snapshot_id") != item.get("snapshot_id")):
                continue
            if _path_of(existing) != _path_of(item) or not _path_of(item):
                continue
            ratio = _overlap_ratio(
                int(existing.get("start_line", 1) or 1),
                int(existing.get("end_line", 1) or 1),
                int(item.get("start_line", 1) or 1),
                int(item.get("end_line", 1) or 1),
            )
            if ratio < overlap_threshold:
                continue
            removed += 1
            merged = True
            # Preserve provenance: record merged source tools on the survivor.
            tools = set(existing.get("merged_sources", []) or [])
            incoming_tool = str(
                item.get("source_tool", item.get("tool_name", "")) or ""
            )
            if incoming_tool:
                tools.add(incoming_tool)
            existing_tool = str(
                existing.get("source_tool", existing.get("tool_name", "")) or ""
            )
            if existing_tool:
                tools.add(existing_tool)
            existing["merged_sources"] = sorted(tools)
            # Keep the strongest/direct evidence content.
            if rank_key(item) < rank_key(existing):
                survivor = dict(item)
                survivor["merged_sources"] = sorted(tools)
                kept[kept.index(existing)] = survivor
            else:
                existing["merged_sources"] = sorted(tools)
            break
        if not merged:
            kept.append(item)
    kept.sort(key=rank_key)
    return kept, removed
