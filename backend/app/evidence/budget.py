"""Evidence budget packing with explicit truncation metadata.

Never silently discards evidence: callers always learn
(evidence_items_total, evidence_items_used, evidence_truncated).
Highest-ranked evidence is kept first; existing token/char safety limits
are preserved.
"""

from __future__ import annotations

from typing import Any

from app.evidence.dedupe import deduplicate_evidence, rank_key


def pack_evidence(
    items: list[dict[str, Any]],
    *,
    max_items: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate, rank, and truncate. Returns (kept, metadata)."""
    deduped, _removed = deduplicate_evidence(list(items))
    total = len(deduped)
    ranked = sorted(deduped, key=rank_key)
    kept = ranked[: max(1, max_items)]
    chars_total = sum(len(str(e.get("content", e.get("excerpt", "")))) for e in ranked)
    chars_used = 0
    final: list[dict[str, Any]] = []
    remaining = max(1024, max_chars)
    for item in kept:
        content = str(item.get("content", item.get("excerpt", "")))
        if chars_used + len(content) > remaining:
            # Preserve provenance with a visible truncation marker.
            cut = dict(item)
            room = max(0, remaining - chars_used)
            cut["content"] = content[:room]
            cut["excerpt"] = content[:room]
            cut["truncated"] = True
            final.append(cut)
            chars_used += len(cut["content"])
            break
        final.append(item)
        chars_used += len(content)
    truncated = len(final) < total or chars_used < chars_total
    meta = {
        "evidence_items_total": total,
        "evidence_items_used": len(final),
        "evidence_truncated": truncated,
        "chars_total": chars_total,
        "chars_used": chars_used,
    }
    return final, meta
