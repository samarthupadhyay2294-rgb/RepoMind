"""Debug investigation ORM models (Part 4/5: AI Debug Investigator).

One Investigation row per debug run, bound to (repository_id, snapshot_id).
InvestigationAction rows record the auditable, user-safe tool activity.
Rows are immutable history: new runs create new rows; failures never
overwrite prior completed investigations.
"""

import enum
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InvestigationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationVerdict(str, enum.Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    UNRESOLVED = "unresolved"


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        Index("ix_investigations_repository_id", "repository_id"),
        Index("ix_investigations_snapshot_id", "snapshot_id"),
        Index("ix_investigations_repo_snapshot", "repository_id", "snapshot_id"),
        Index("ix_investigations_status", "repository_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("repository_index_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Redacted structured input (never raw secrets).
    error_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_route: Mapped[str | None] = mapped_column(String(512), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    reproduction_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    stop_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_truncated: Mapped[bool] = mapped_column(nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class InvestigationAction(Base):
    __tablename__ = "investigation_actions"
    __table_args__ = (
        Index("ix_inv_actions_investigation_id", "investigation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
