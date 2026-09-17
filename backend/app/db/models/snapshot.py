"""Immutable indexing snapshot ORM model (Part 1 shared foundation).

One row per indexing run. The snapshot is the exact repository state used
to generate embeddings, evidence, and (later) graph/overview/investigation
artifacts. Rows are never mutated after activation — a new indexing run
creates a new row; a failed run never replaces the previous active one.
"""

import enum
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SnapshotStatus(str, enum.Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class RepositoryIndexSnapshot(Base):
    __tablename__ = "repository_index_snapshots"
    __table_args__ = (
        Index("ix_snapshots_repository_id", "repository_id"),
        Index("ix_snapshots_repo_status", "repository_id", "status"),
        Index("ix_snapshots_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manifest_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v1"
    )
    embedding_model: Mapped[str] = mapped_column(
        String(128), nullable=False, default="mistral-embed"
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024
    )
    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status"),
        nullable=False,
        default=SnapshotStatus.PENDING,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
