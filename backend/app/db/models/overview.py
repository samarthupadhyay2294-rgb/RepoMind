"""Architecture overview ORM model (Part 3: AI Repository Overview).

One row per (repository_id, snapshot_id) generation. Rows are immutable
history: a new snapshot/generation creates a new row; a failed generation
never overwrites the last successful overview.
"""

import enum
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OverviewStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ArchitectureOverview(Base):
    __tablename__ = "architecture_overviews"
    __table_args__ = (
        Index("ix_overviews_repository_id", "repository_id"),
        Index("ix_overviews_snapshot_id", "snapshot_id"),
        Index("ix_overviews_repo_snapshot", "repository_id", "snapshot_id"),
        Index("ix_overviews_status", "repository_id", "generation_status"),
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
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    architecture_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_flows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    boundaries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    key_dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    configuration_areas: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    uncertainties: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_truncated: Mapped[bool] = mapped_column(nullable=False, default=False)
    evidence_items_total: Mapped[int] = mapped_column(nullable=False, default=0)
    evidence_items_used: Mapped[int] = mapped_column(nullable=False, default=0)
    generation_model: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    generation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="v1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
