"""Overview lifecycle service (Part 3).

Dedicated service flow — independent of the user-chat LangGraph loop —
reusing the LLM factory, evidence budget/redaction, citation validation,
repository tools, and Part 2 graph services. Rows are immutable history:
generation creates rows; failure marks the new row failed and preserves
the previous successful overview.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.overview import ArchitectureOverview, OverviewStatus
from app.db.models.snapshot import RepositoryIndexSnapshot, SnapshotStatus
from app.exceptions import AppError
from app.overview import OVERVIEW_PROMPT_VERSION, evidence_selection, facts
from app.overview import prompt as prompt_mod
from app.overview import synthesis as synthesis_mod
from app.overview import validate as validate_mod
from app.services import repositories as repository_service
from app.services import snapshots as snapshot_service

logger = logging.getLogger(__name__)


def require_overview_enabled() -> None:
    if not settings.ARCHITECTURE_OVERVIEW:
        raise AppError(
            "Repository overview is disabled for this deployment.",
            code="OVERVIEW_DISABLED",
            status_code=403,
        )


async def resolve_snapshot(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    snapshot_id: str | None,
) -> tuple[RepositoryIndexSnapshot, bool]:
    """Owner-checked snapshot resolution; (snapshot, is_active)."""
    await repository_service.get_repository(session, owner_id, repository_id)
    if snapshot_id:
        try:
            sid = UUID(snapshot_id)
        except ValueError:
            raise AppError(
                "Invalid snapshot_id.",
                code="OVERVIEW_INVALID_SNAPSHOT",
                status_code=422,
            )
        row = (
            await session.execute(
                select(RepositoryIndexSnapshot).where(
                    RepositoryIndexSnapshot.id == sid,
                    RepositoryIndexSnapshot.repository_id == repository_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(
                "Snapshot not found.",
                code="OVERVIEW_SNAPSHOT_NOT_FOUND",
                status_code=404,
            )
        if row.status != SnapshotStatus.READY:
            raise AppError(
                "Snapshot is not ready.",
                code="OVERVIEW_SNAPSHOT_NOT_READY",
                status_code=409,
            )
        active = await snapshot_service.get_active_snapshot(session, repository_id)
        return row, active is not None and active.id == row.id
    active = await snapshot_service.get_active_snapshot(session, repository_id)
    if active is None:
        raise AppError(
            "Repository must be indexed before generating an overview.",
            code="OVERVIEW_NO_SNAPSHOT",
            status_code=409,
        )
    return active, True


async def latest_overview(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID
) -> ArchitectureOverview | None:
    rows = (
        await session.execute(
            select(ArchitectureOverview)
            .where(
                ArchitectureOverview.repository_id == repository_id,
                ArchitectureOverview.snapshot_id == snapshot_id,
                ArchitectureOverview.generation_status
                == OverviewStatus.COMPLETED.value,
            )
            .order_by(desc(ArchitectureOverview.created_at))
            .limit(1)
        )
    ).scalars()
    return next(iter(rows), None)


async def generate_overview(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    snapshot_id: str | None = None,
    *,
    llm_model: Any = None,
) -> ArchitectureOverview:
    """Run the full pipeline; failed runs preserve prior overviews."""
    snapshot, _ = await resolve_snapshot(session, owner_id, repository_id, snapshot_id)
    repository = await repository_service.get_repository(
        session, owner_id, repository_id
    )
    model_name = (
        "mock-llm"
        if isinstance(llm_model, str)
        else synthesis_mod.generation_model_name()
    )
    row = ArchitectureOverview(
        repository_id=repository_id,
        snapshot_id=snapshot.id,
        generation_status=OverviewStatus.GENERATING.value,
        generation_model=model_name[:128],
        prompt_version=OVERVIEW_PROMPT_VERSION,
    )
    session.add(row)
    await session.flush()
    try:
        fact_data = await facts.collect_facts(session, repository, snapshot.id)
        evidence, ev_meta = evidence_selection.select_evidence(
            repository, snapshot.id, fact_data
        )
        prompt_text, _ = prompt_mod.build_prompt(fact_data, evidence)
        structured = synthesis_mod.synthesize(prompt_text, model_override=llm_model)
        snapshot_paths = await validate_mod._snapshot_paths(
            session, repository_id, snapshot.id
        )
        validated, _report = validate_mod.validate_overview(
            structured.model_dump(),
            evidence=evidence,
            repository_id=str(repository_id),
            snapshot_id=str(snapshot.id),
            snapshot_paths=snapshot_paths,
        )
        row.summary = validated["summary"]
        row.architecture_style = validated["architecture_style"]
        row.entry_points = validated["entry_points"]
        row.components = validated["components"]
        row.data_flows = validated["data_flows"]
        row.boundaries = validated["boundaries"]
        row.key_dependencies = validated["key_dependencies"]
        row.configuration_areas = validated["configuration_areas"]
        row.uncertainties = validated["uncertainties"]
        row.evidence = [
            {
                "id": e.get("id"),
                "path": e.get("path"),
                "start_line": e.get("start_line"),
                "end_line": e.get("end_line"),
                "source_tool": e.get("source_tool"),
                "redacted": e.get("redacted", False),
            }
            for e in evidence
        ]
        row.evidence_truncated = bool(ev_meta.get("evidence_truncated", False))
        row.evidence_items_total = int(ev_meta.get("evidence_items_total", 0))
        row.evidence_items_used = int(ev_meta.get("evidence_items_used", 0))
        row.generation_status = OverviewStatus.COMPLETED.value
        await session.commit()
        await session.refresh(row)
        logger.info(
            "overview_generated repository_id=%s snapshot_id=%s overview_id=%s",
            repository_id,
            snapshot.id,
            row.id,
        )
        return row
    except AppError:
        raise
    except synthesis_mod.OverviewSynthesisError as exc:
        await _mark_failed(session, row, str(exc)[:500])
        raise AppError(
            str(exc)[:500], code="OVERVIEW_GENERATION_FAILED", status_code=502
        )
    except Exception as exc:
        logger.warning(
            "overview_generation_failed repository_id=%s error=%s",
            repository_id,
            type(exc).__name__,
        )
        await _mark_failed(session, row, "Overview generation failed.")
        raise AppError(
            "Overview generation failed.",
            code="OVERVIEW_GENERATION_FAILED",
            status_code=502,
        )


async def _mark_failed(
    session: AsyncSession, row: ArchitectureOverview, message: str
) -> None:
    row.generation_status = OverviewStatus.FAILED.value
    row.error_message = message
    await session.commit()


def row_to_response(
    row: ArchitectureOverview, *, snapshot_active: bool, stale: bool = False
) -> dict[str, Any]:
    created = row.created_at
    if isinstance(created, datetime):
        generated_at = created.isoformat()
    else:
        generated_at = str(created)
    return {
        "repository_id": str(row.repository_id),
        "snapshot_id": str(row.snapshot_id),
        "snapshot_active": snapshot_active,
        "overview_id": str(row.id),
        "generated_at": generated_at,
        "generation_model": row.generation_model,
        "generation_status": row.generation_status,
        "stale": stale,
        "overview": {
            "summary": row.summary,
            "architecture_style": row.architecture_style,
            "entry_points": row.entry_points or [],
            "components": row.components or [],
            "data_flows": row.data_flows or [],
            "boundaries": row.boundaries or [],
            "key_dependencies": row.key_dependencies or [],
            "configuration_areas": row.configuration_areas or [],
            "uncertainties": row.uncertainties or [],
        },
        "evidence": row.evidence or [],
        "truncated": bool(row.evidence_truncated),
        "evidence_items_total": int(row.evidence_items_total or 0),
        "evidence_items_used": int(row.evidence_items_used or 0),
    }
