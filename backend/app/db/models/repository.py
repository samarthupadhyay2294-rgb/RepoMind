"""Repository ORM model. Metadata only — no secrets are stored here."""

import enum
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceType(str, enum.Enum):
    LOCAL = "local"
    GIT = "git"


class RepositoryStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_repositories_owner_name"),
        Index("ix_repositories_status", "status"),
        Index("ix_repositories_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="repository_source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status"),
        nullable=False,
        default=RepositoryStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Part 1: pointer to the currently active indexing snapshot (nullable
    # for pre-snapshot rows; backfilled on next successful indexing run).
    active_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, default=None
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
