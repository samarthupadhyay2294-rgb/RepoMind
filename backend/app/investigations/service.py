"""Investigation lifecycle (Part 4/5).

Verdict rules (deterministic, evidence-based — never model self-grading):
- confirmed: a stack frame from the report matches a validated citation
  (same path, overlapping lines) AND ≥2 validated citations total.
- likely: ≥1 validated citation.
- unresolved: no validated citations.

Every verdict ships with limitations; "likely" is never upgraded without
the confirmed-rule evidence above.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import _run_graph
from app.config import settings
from app.db.models.investigation import (
    Investigation,
    InvestigationAction,
    InvestigationStatus,
)
from app.db.models.snapshot import RepositoryIndexSnapshot, SnapshotStatus
from app.evidence.redaction import redact_text
from app.exceptions import AppError
from app.investigations.schemas import InvestigationCreate
from app.services import repositories as repository_service
from app.services import snapshots as snapshot_service

logger = logging.getLogger(__name__)

# `path/to/file.py:123`, `at fn (file:line:col)`, and `File "file", line N`.
_FRAME_RES = (
    re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+\.py):(?P<line>\d+)"),
    re.compile(r"\((?P<path>[A-Za-z0-9_./\\-]+\.[a-z]+):(?P<line>\d+)(?::\d+)?\)"),
    re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)'),
)

_CONFIDENCE_BY_VERDICT = {"confirmed": "high", "likely": "medium", "unresolved": "low"}


def require_investigator_enabled() -> None:
    if not settings.DEBUG_INVESTIGATOR:
        raise AppError(
            "Debug investigator is disabled for this deployment.",
            code="INVESTIGATION_DISABLED",
            status_code=403,
        )


def redact_input(payload: InvestigationCreate) -> dict[str, str | None]:
    """Redact secret-shaped content from every input field before storage/use."""
    out: dict[str, str | None] = {}
    for field in (
        "error_text",
        "stack_trace",
        "affected_route",
        "environment",
        "expected_behavior",
        "actual_behavior",
        "reproduction_steps",
    ):
        value = getattr(payload, field)
        if value is None:
            out[field] = None
        else:
            redacted, _ = redact_text(value.strip()[:8000])
            out[field] = redacted
    if not (out["error_text"] or "").strip():
        raise AppError(
            "error_text must not be empty.",
            code="INVESTIGATION_INVALID",
            status_code=422,
        )
    return out


def extract_frames(error_text: str, stack_trace: str | None) -> list[dict[str, Any]]:
    """Parse stack frames from the report (deterministic, no LLM)."""
    frames: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for pattern in _FRAME_RES:
        for match in pattern.finditer(f"{error_text or ''}\n{stack_trace or ''}"):
            path = match.group("path").replace("\\", "/").lstrip("./")
            try:
                line = int(match.group("line"))
            except (TypeError, ValueError):
                continue
            if line < 1 or (path, line) in seen:
                continue
            seen.add((path, line))
            frames.append({"path": path, "line": line})
    return frames[:20]


def map_verdict(
    citations: list[dict[str, Any]], frames: list[dict[str, Any]]
) -> tuple[str, str]:
    """Map validated citations (+ optional frame overlap) to a verdict."""
    valid = [
        c
        for c in citations
        if c.get("file_path") and int(c.get("start_line", 0) or 0) >= 1
    ]
    if not valid:
        return "unresolved", _CONFIDENCE_BY_VERDICT["unresolved"]
    for frame in frames:
        for citation in valid:
            try:
                start = int(citation.get("start_line", 0) or 0)
                end = int(citation.get("end_line", start) or start)
            except (TypeError, ValueError):
                continue
            if (
                str(citation.get("file_path", "")).lstrip("./") == frame["path"]
                and start <= frame["line"] <= end
                and len(valid) >= 2
            ):
                return "confirmed", _CONFIDENCE_BY_VERDICT["confirmed"]
    return "likely", _CONFIDENCE_BY_VERDICT["likely"]


def build_question(redacted: dict[str, str | None]) -> str:
    """Assemble the debug-framed agent question from redacted fields only."""
    parts = [f"Investigate this failure: {redacted['error_text']}"]
    if redacted.get("stack_trace"):
        parts.append(f"Stack trace:\n{redacted['stack_trace']}")
    if redacted.get("affected_route"):
        parts.append(f"Affected route/command: {redacted['affected_route']}")
    if redacted.get("environment"):
        parts.append(f"Environment: {redacted['environment']}")
    if redacted.get("expected_behavior"):
        parts.append(f"Expected: {redacted['expected_behavior']}")
    if redacted.get("actual_behavior"):
        parts.append(f"Actual: {redacted['actual_behavior']}")
    if redacted.get("reproduction_steps"):
        parts.append(f"Reproduction: {redacted['reproduction_steps']}")
    parts.append(
        "Find the responsible code with file:line evidence. "
        "Distinguish confirmed causes from hypotheses."
    )
    question = "\n\n".join(parts)
    return question[:4000]


async def resolve_snapshot(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    snapshot_id: str | None,
) -> tuple[RepositoryIndexSnapshot, bool]:
    await repository_service.get_repository(session, owner_id, repository_id)
    if snapshot_id:
        try:
            sid = UUID(snapshot_id)
        except ValueError:
            raise AppError(
                "Invalid snapshot_id.",
                code="INVESTIGATION_INVALID_SNAPSHOT",
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
                code="INVESTIGATION_SNAPSHOT_NOT_FOUND",
                status_code=404,
            )
        if row.status != SnapshotStatus.READY:
            raise AppError(
                "Snapshot is not ready.",
                code="INVESTIGATION_SNAPSHOT_NOT_READY",
                status_code=409,
            )
        active = await snapshot_service.get_active_snapshot(session, repository_id)
        return row, active is not None and active.id == row.id
    active = await snapshot_service.get_active_snapshot(session, repository_id)
    if active is None:
        raise AppError(
            "Repository must be indexed before running an investigation.",
            code="INVESTIGATION_NO_SNAPSHOT",
            status_code=409,
        )
    return active, True


async def get_investigation(
    session: AsyncSession, owner_id: str, repository_id: UUID, run_id: UUID
) -> tuple[Investigation, list[InvestigationAction]]:
    await repository_service.get_repository(session, owner_id, repository_id)
    row = (
        await session.execute(
            select(Investigation).where(
                Investigation.id == run_id,
                Investigation.repository_id == repository_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(
            "Investigation not found.", code="INVESTIGATION_NOT_FOUND", status_code=404
        )
    actions = (
        await session.execute(
            select(InvestigationAction)
            .where(InvestigationAction.investigation_id == row.id)
            .order_by(InvestigationAction.sequence)
        )
    ).scalars()
    return row, list(actions)


async def run_investigation(
    session: AsyncSession,
    owner_id: str,
    repository_id: UUID,
    payload: InvestigationCreate,
    *,
    deps: Any = None,
) -> Investigation:
    """Run one bounded investigation; failures preserve prior runs."""
    snapshot, _ = await resolve_snapshot(
        session, owner_id, repository_id, payload.snapshot_id
    )
    repository = await repository_service.get_repository(
        session, owner_id, repository_id
    )
    redacted = redact_input(payload)
    frames = extract_frames(
        str(redacted["error_text"] or ""), redacted.get("stack_trace")
    )
    row = Investigation(
        repository_id=repository_id,
        snapshot_id=snapshot.id,
        error_text=str(redacted["error_text"] or "")[:4000],
        stack_trace=redacted.get("stack_trace"),
        affected_route=redacted.get("affected_route"),
        environment=redacted.get("environment"),
        expected_behavior=redacted.get("expected_behavior"),
        actual_behavior=redacted.get("actual_behavior"),
        reproduction_steps=redacted.get("reproduction_steps"),
        status=InvestigationStatus.RUNNING.value,
    )
    session.add(row)
    await session.flush()
    try:
        question = build_question(redacted)
        final, sid, llm_calls, latency_ms = await _run_graph(
            repository, question, None, deps
        )
        citations = [
            dict(c) for c in (final.get("citations", []) or []) if isinstance(c, dict)
        ]
        verdict, confidence = map_verdict(citations, frames)
        limitations = list(final.get("warnings", []) or [])
        if verdict == "unresolved":
            limitations.append(
                "No validated file:line evidence was found for this symptom."
            )
        if not frames:
            limitations.append(
                "No stack-trace file:line frames were supplied; "
                "cause confirmation needs exact locations."
            )
        row.status = InvestigationStatus.COMPLETED.value
        row.verdict = verdict
        row.confidence = confidence
        row.summary = str(final.get("answer", ""))[:4000]
        row.findings = [
            {
                "claim": str(final.get("answer", ""))[:2000],
                "confidence": verdict,
                "evidence_refs": [
                    f"{c.get('file_path')}:{c.get('start_line')}-{c.get('end_line')}"
                    for c in citations
                ],
            }
        ]
        row.next_steps = []
        row.limitations = limitations[:20]
        row.citations = citations
        row.stop_reason = str(final.get("stop_reason", "") or "")
        row.tool_calls = int(final.get("tool_call_count", 0) or 0)
        row.llm_calls = int(llm_calls or 0)
        row.duration_ms = float(latency_ms or 0.0)
        row.evidence_truncated = bool(
            (final.get("evidence_meta", {}) or {}).get("evidence_truncated", False)
        )
        row.session_id = sid
        await session.flush()
        records = final.get("tool_calls", []) or []
        for seq, record in enumerate(records[:100]):
            if not isinstance(record, dict):
                continue
            session.add(
                InvestigationAction(
                    investigation_id=row.id,
                    sequence=seq,
                    tool_name=str(record.get("tool_name", ""))[:64],
                    arguments=dict(record.get("arguments", {}) or {}),
                    ok=bool(record.get("ok", False)),
                    result_count=int(record.get("result_count", 0) or 0),
                    warning=str(record.get("warning", ""))[:256],
                    duration_ms=float(record.get("duration_ms", 0.0) or 0.0),
                )
            )
        await session.commit()
        await session.refresh(row)
        logger.info(
            "investigation_completed repository_id=%s run_id=%s verdict=%s stop=%s",
            repository_id,
            row.id,
            verdict,
            row.stop_reason,
        )
        return row
    except Exception as exc:
        logger.warning(
            "investigation_failed repository_id=%s error=%s",
            repository_id,
            type(exc).__name__,
        )
        row.status = InvestigationStatus.FAILED.value
        # Controlled message only — never raw tracebacks with source/secrets.
        row.error_message = (
            str(exc)[:500] if isinstance(exc, AppError) else "Investigation failed."
        )
        await session.commit()
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "Investigation failed.", code="INVESTIGATION_FAILED", status_code=502
        )


async def latest_for_snapshot(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID
) -> Investigation | None:
    rows = (
        await session.execute(
            select(Investigation)
            .where(
                Investigation.repository_id == repository_id,
                Investigation.snapshot_id == snapshot_id,
                Investigation.status == InvestigationStatus.COMPLETED.value,
            )
            .order_by(desc(Investigation.created_at))
            .limit(1)
        )
    ).scalars()
    return next(iter(rows), None)


def row_to_response(
    row: Investigation,
    actions: list[InvestigationAction],
    *,
    snapshot_active: bool,
) -> dict[str, Any]:
    created = row.created_at
    return {
        "id": str(row.id),
        "repository_id": str(row.repository_id),
        "snapshot_id": str(row.snapshot_id),
        "snapshot_active": snapshot_active,
        "status": row.status,
        "verdict": row.verdict,
        "confidence": row.confidence,
        "summary": row.summary or "",
        "findings": row.findings or [],
        "next_steps": row.next_steps or [],
        "limitations": row.limitations or [],
        "citations": row.citations or [],
        "actions": [
            {
                "sequence": a.sequence,
                "tool": a.tool_name,
                "ok": a.ok,
                "result_count": a.result_count,
                "warning": a.warning,
                "duration_ms": a.duration_ms,
            }
            for a in actions
        ],
        "stop_reason": row.stop_reason or "",
        "tool_calls": int(row.tool_calls or 0),
        "llm_calls": int(row.llm_calls or 0),
        "duration_ms": float(row.duration_ms or 0.0),
        "evidence_truncated": bool(row.evidence_truncated),
        "session_id": row.session_id,
        "created_at": created.isoformat()
        if isinstance(created, datetime)
        else str(created),
    }
