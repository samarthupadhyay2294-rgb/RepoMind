"""Evidence selection for overview synthesis (Part 3).

Prioritized, bounded, redacted: entry points → routers → manifests →
service/db modules → config → graph-backed excerpts. Uses the shared
EvidenceItem contract and the Part 1 budget packer with explicit
truncation metadata — never silently pretending the LLM saw everything.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.config import settings
from app.db.models.repository import Repository
from app.evidence.budget import pack_evidence
from app.evidence.items import EvidenceItem, canonical_relative_path
from app.evidence.redaction import redact_text
from app.tools.context import context_for_repository

logger = logging.getLogger(__name__)


def _excerpt(path: str, text: str, max_chars: int) -> tuple[str, bool]:
    redacted, was_redacted = redact_text(text[:max_chars])
    lines = redacted.splitlines()
    # Keep head + structure: first N lines carry imports/definitions.
    kept = "\n".join(lines[:80])[:max_chars]
    return kept, was_redacted


def _priority(rel: str, facts: dict) -> int:
    entry_paths = {e["path"] for e in facts.get("entry_point_candidates", [])}
    route_paths = {r["path"] for r in facts.get("route_hints", [])}
    if rel in entry_paths:
        return 0
    if rel in route_paths:
        return 1
    base = rel.rsplit("/", 1)[-1]
    if base in ("package.json", "pyproject.toml", "requirements.txt", "go.mod"):
        return 2
    if rel in set(facts.get("db_indicators", [])):
        return 3
    if rel in set(facts.get("config_files", [])):
        return 4
    top = {t["path"] for t in facts.get("top_importers", [])}
    if rel in top:
        return 5
    return 6


def select_evidence(
    repository: Repository, snapshot_id: UUID, facts: dict
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read prioritized excerpts → EvidenceItems → budgeted pack."""
    repo_id = str(repository.id)
    snap_id = str(snapshot_id)
    try:
        ctx = context_for_repository(repository)
    except Exception as exc:
        logger.warning(
            "overview_evidence_no_workspace repository_id=%s error=%s",
            repo_id,
            type(exc).__name__,
        )
        return [], {
            "evidence_items_total": 0,
            "evidence_items_used": 0,
            "evidence_truncated": False,
            "reason": "workspace_unavailable",
            "omitted_count": 0,
        }
    from app.ingestion import discovery

    found = discovery.discover_files(ctx.root)
    by_rel = {item.rel: item for item in found.files}
    # candidate pool: facts-referenced files first, then discovered code
    pool: list[str] = []
    for group in (
        [e["path"] for e in facts.get("entry_point_candidates", [])],
        [r["path"] for r in facts.get("route_hints", [])],
        list(facts.get("manifests", {}).keys()),
        list(facts.get("db_indicators", [])),
        list(facts.get("config_files", [])),
        [t["path"] for t in facts.get("top_importers", [])],
    ):
        for rel in group:
            if rel in by_rel and rel not in pool:
                pool.append(rel)
    for rel in sorted(by_rel):
        if rel not in pool and len(pool) < 120:
            item = by_rel[rel]
            if item.language in ("python", "javascript", "typescript"):
                pool.append(rel)
    pool.sort(key=lambda r: (_priority(r, facts), r))

    max_items = max(1, settings.OVERVIEW_MAX_EVIDENCE_ITEMS)
    max_excerpt = max(256, settings.OVERVIEW_MAX_EXCERPT_CHARS)
    items: list[dict[str, Any]] = []
    for rel in pool[: max_items * 2]:  # oversample; packer enforces budget
        pool_item = by_rel.get(rel)
        if pool_item is None:
            continue
        item = pool_item
        try:
            raw = item.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        lines = raw.splitlines()
        excerpt, was_redacted = _excerpt(rel, raw, max_excerpt)
        try:
            path = canonical_relative_path(rel)
        except ValueError:
            continue
        try:
            ev = EvidenceItem(
                repository_id=repo_id,
                snapshot_id=snap_id,
                kind="code",
                path=path,
                start_line=1,
                end_line=max(1, min(len(lines) or 1, 80)),
                excerpt=excerpt,
                source_tool="overview_evidence",
                source_ref=f"overview:{path}",
                confidence="direct",
                redacted=was_redacted,
            )
        except ValueError:
            continue
        items.append(ev.model_dump())
    kept, meta = pack_evidence(
        items,
        max_items=max_items,
        max_chars=max(4096, settings.OVERVIEW_MAX_PROMPT_CHARS // 2),
    )
    total = int(meta.get("evidence_items_total", 0))
    used = int(meta.get("evidence_items_used", len(kept)))
    meta["omitted_count"] = max(0, total - used)
    if meta.get("evidence_truncated"):
        meta["reason"] = "evidence_budget"
    logger.info(
        "overview_evidence_selected repository_id=%s snapshot_id=%s used=%d total=%d",
        repo_id,
        snap_id,
        used,
        total,
    )
    return kept, meta
