"""Snapshot-scoped code graph ORM models (Part 2: Interactive Dependency & Code Graph).

Every row is bound to (repository_id, snapshot_id). All queries MUST filter
by both columns — never fetch a node/edge globally and check ownership after.
"""

import enum
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SymbolType(str, enum.Enum):
    FILE = "file"
    DIRECTORY = "directory"
    MODULE = "module"
    NAMESPACE = "namespace"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    VARIABLE = "variable"
    CONSTANT = "constant"


class RelationshipType(str, enum.Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    EXPORTS = "exports"
    CALLS = "calls"
    REFERENCES = "references"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    OVERRIDES = "overrides"
    USES_TYPE = "uses_type"
    DEFINES = "defines"


class Provenance(str, enum.Enum):
    PARSER = "parser"
    RESOLVER = "resolver"
    INFERRED = "inferred"


class CodeSymbol(Base):
    __tablename__ = "code_symbols"
    __table_args__ = (
        Index("ix_symbols_repository_id", "repository_id"),
        Index("ix_symbols_snapshot_id", "snapshot_id"),
        Index("ix_symbols_repo_snapshot", "repository_id", "snapshot_id"),
        Index("ix_symbols_stable_key", "repository_id", "snapshot_id", "stable_key"),
        Index("ix_symbols_path", "repository_id", "snapshot_id", "path"),
        Index("ix_symbols_parent", "parent_symbol_id"),
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
    # Stable within a snapshot: "<path>::<qualified_name>::<symbol_type>"
    stable_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visibility: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provenance: Mapped[str] = mapped_column(
        String(16), nullable=False, default="parser"
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CodeRelationship(Base):
    __tablename__ = "code_relationships"
    __table_args__ = (
        Index("ix_rels_repository_id", "repository_id"),
        Index("ix_rels_snapshot_id", "snapshot_id"),
        Index("ix_rels_repo_snapshot", "repository_id", "snapshot_id"),
        Index("ix_rels_source", "repository_id", "snapshot_id", "source_symbol_id"),
        Index("ix_rels_target", "repository_id", "snapshot_id", "target_symbol_id"),
        Index("ix_rels_type", "repository_id", "snapshot_id", "relationship_type"),
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
    source_symbol_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_symbol_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    provenance: Mapped[str] = mapped_column(
        String(16), nullable=False, default="parser"
    )
    # Source evidence location (denormalized for cheap reads; full evidence
    # comes from EvidenceItem construction, not a FK to avoid cycles).
    path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
