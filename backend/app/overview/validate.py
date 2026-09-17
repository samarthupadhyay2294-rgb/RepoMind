"""Claim validation for overviews (Part 3).

Enforces: same repository + snapshot evidence, known evidence IDs, valid
canonical paths that exist in the snapshot's symbol inventory, sane line
ranges, and scrubbed prose citations. Invalid claims are removed or
demoted to uncertainties — never silently preserved.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.graph import CodeSymbol
from app.evidence import citations as citation_utils
from app.evidence.items import canonical_relative_path

logger = logging.getLogger(__name__)


async def _snapshot_paths(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID
) -> set[str]:
    rows = (
        await session.execute(
            select(CodeSymbol.path).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.snapshot_id == snapshot_id,
            )
        )
    ).all()
    return {str(r[0]) for r in rows}


def _valid_path(path: Any, snapshot_paths: set[str]) -> str | None:
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        cleaned = canonical_relative_path(path)
    except ValueError:
        return None
    if cleaned not in snapshot_paths:
        return None
    return cleaned


def validate_overview(
    overview: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
    repository_id: str,
    snapshot_id: str,
    snapshot_paths: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate + repair a structured overview. Returns (overview, report)."""
    valid_ids = {str(e.get("id")) for e in evidence if e.get("id")}
    # Evidence itself must be repo+snapshot confined.
    for ev in evidence:
        if str(ev.get("repository_id", "")) != repository_id or (
            ev.get("snapshot_id") is not None
            and str(ev.get("snapshot_id")) != snapshot_id
        ):
            raise ValueError("Evidence escaped repository/snapshot confinement.")
    removed = 0
    demoted = 0

    def clean_ids(ids: Any) -> list[str]:
        nonlocal removed
        out = [i for i in (ids or []) if str(i) in valid_ids]
        removed += len(ids or []) - len(out)
        return [str(i) for i in out]

    def scrub(text: Any) -> Any:
        if not isinstance(text, str) or not text:
            return text
        unsupported = citation_utils.find_unsupported_prose_refs(
            text, evidence, repository_id, snapshot_id
        )
        if unsupported:
            return citation_utils.scrub_unsupported_refs(text, unsupported)
        return text

    # entry points: require valid path + at least one valid evidence ID
    entries = []
    for ep in overview.get("entry_points", []) or []:
        path = _valid_path(ep.get("path"), snapshot_paths)
        if path is None:
            removed += 1
            continue
        ids = clean_ids(ep.get("evidence_ids"))
        if not ids:
            removed += 1
            continue
        start = max(1, int(ep.get("start_line", 1) or 1))
        end = max(start, int(ep.get("end_line", start) or start))
        entries.append(
            {
                "name": str(ep.get("name", ""))[:256],
                "type": str(ep.get("type", "file"))[:64],
                "path": path,
                "start_line": start,
                "end_line": end,
                "description": scrub(str(ep.get("description", ""))[:2000]),
                "confidence": ep.get("confidence", "candidate"),
                "evidence_ids": ids,
            }
        )

    # components: require ≥1 valid path or ≥1 valid evidence ID
    components = []
    for comp in overview.get("components", []) or []:
        paths = [
            p
            for p in (
                _valid_path(p, snapshot_paths) for p in (comp.get("paths", []) or [])
            )
            if p is not None
        ]
        removed += len(comp.get("paths", []) or []) - len(paths)
        ids = clean_ids(comp.get("evidence_ids"))
        if not paths and not ids:
            removed += 1
            continue
        components.append(
            {
                "id": str(comp.get("id", comp.get("name", "")))[:256],
                "name": str(comp.get("name", ""))[:256],
                "type": str(comp.get("type", "module"))[:64],
                "description": scrub(str(comp.get("description", ""))[:3000]),
                "paths": paths[:30],
                "responsibilities": [
                    scrub(str(r)[:500])
                    for r in (comp.get("responsibilities", []) or [])[:10]
                ],
                "dependencies": [
                    str(d)[:256] for d in (comp.get("dependencies", []) or [])[:20]
                ],
                "evidence_ids": ids,
            }
        )
    comp_ids = {c["id"] for c in components} | {c["name"] for c in components}

    flows = []
    for fl in overview.get("data_flows", []) or []:
        ids = clean_ids(fl.get("evidence_ids"))
        src, tgt = str(fl.get("source", "")), str(fl.get("target", ""))
        if not src or not tgt:
            removed += 1
            continue
        if (src not in comp_ids or tgt not in comp_ids) and not ids:
            removed += 1
            continue
        flows.append(
            {
                "source": src[:256],
                "target": tgt[:256],
                "description": scrub(str(fl.get("description", ""))[:2000]),
                "evidence_ids": ids,
            }
        )

    boundaries = []
    for b in overview.get("boundaries", []) or []:
        paths = [
            p
            for p in (
                _valid_path(p, snapshot_paths) for p in (b.get("paths", []) or [])
            )
            if p is not None
        ]
        ids = clean_ids(b.get("evidence_ids"))
        if not str(b.get("name", "")):
            removed += 1
            continue
        boundaries.append(
            {
                "name": str(b.get("name", ""))[:256],
                "description": scrub(str(b.get("description", ""))[:2000]),
                "paths": paths[:30],
                "evidence_ids": ids,
            }
        )

    deps = []
    for d in overview.get("key_dependencies", []) or []:
        if not str(d.get("name", "")):
            removed += 1
            continue
        deps.append(
            {
                "name": str(d.get("name", ""))[:256],
                "purpose": scrub(str(d.get("purpose", ""))[:1000]),
                "evidence_ids": clean_ids(d.get("evidence_ids")),
            }
        )

    configs = []
    for c in overview.get("configuration_areas", []) or []:
        path = _valid_path(c.get("path"), snapshot_paths)
        if path is None:
            removed += 1
            continue
        configs.append(
            {
                "path": path,
                "description": scrub(str(c.get("description", ""))[:1000]),
                "evidence_ids": clean_ids(c.get("evidence_ids")),
            }
        )

    uncertainties = []
    for u in overview.get("uncertainties", []) or []:
        if str(u.get("statement", "")):
            uncertainties.append(
                {
                    "statement": str(u.get("statement", ""))[:2000],
                    "reason": scrub(str(u.get("reason", ""))[:2000]),
                }
            )
    if demoted:
        uncertainties.append(
            {
                "statement": f"{demoted} claim(s) lacked evidence.",
                "reason": "Removed during validation; treated as unknown.",
            }
        )

    style = overview.get("architecture_style")
    if style is not None and (not isinstance(style, str) or not style.strip()):
        style = None
    validated = {
        "summary": scrub(str(overview.get("summary", ""))[:6000]),
        "architecture_style": style[:64] if isinstance(style, str) else None,
        "entry_points": entries[:20],
        "components": components[:20],
        "data_flows": flows[:20],
        "boundaries": boundaries[:20],
        "key_dependencies": deps[:30],
        "configuration_areas": configs[:20],
        "uncertainties": uncertainties[:20],
    }
    report = {"removed_claims": removed, "demoted_claims": demoted}
    logger.info(
        "overview_validated repository_id=%s removed=%d",
        repository_id,
        removed,
    )
    return validated, report
