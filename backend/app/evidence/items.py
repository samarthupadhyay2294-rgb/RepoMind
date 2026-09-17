"""Shared evidence contract (Part 1 foundation).

Every evidence item carries repository + snapshot provenance so evidence
from repository A / snapshot A is never usable for repository B /
snapshot B. Validation rejects absolute paths, traversal, unconfinded
roots, invalid line ranges, and repository/snapshot mismatches.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EvidenceKind = Literal["code", "search", "graph", "validation", "metadata"]
EvidenceConfidence = Literal["direct", "derived"]

_ABSOLUTE_RE = re.compile(r"^(?:[a-zA-Z]:[\\/]|\\\\|/)")
_TRAVERSAL_RE = re.compile(r"(^|/)\.\.(/|$)")


class EvidenceValidationError(ValueError):
    """Raised when an evidence item fails contract validation."""

    def __init__(self, message: str, *, code: str = "EVIDENCE_INVALID") -> None:
        super().__init__(message)
        self.code = code


def canonical_relative_path(path: str) -> str:
    """Validate + normalize a repository-relative path (raises on violation)."""
    if not isinstance(path, str) or not path.strip():
        raise EvidenceValidationError("path must not be empty.", code="EVIDENCE_PATH")
    cleaned = path.strip().replace("\\", "/")
    # Allow empty path only for non-file evidence (validation/metadata summaries
    # use path=""). File-backed kinds must name a file.
    if cleaned == "":
        return ""
    if _ABSOLUTE_RE.match(cleaned) or cleaned.startswith("/"):
        raise EvidenceValidationError(
            f"absolute paths are rejected: {path[:200]}", code="EVIDENCE_PATH_ABSOLUTE"
        )
    if _TRAVERSAL_RE.search(cleaned) or "/../" in f"/{cleaned}/":
        raise EvidenceValidationError(
            f"path traversal is rejected: {path[:200]}", code="EVIDENCE_PATH_TRAVERSAL"
        )
    normalized = re.sub(r"/+", "/", cleaned).strip("/")
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        raise EvidenceValidationError(
            f"path escapes the repository: {path[:200]}", code="EVIDENCE_PATH_ESCAPE"
        )
    return normalized


class EvidenceItem(BaseModel):
    """Validated shared evidence unit (repository + snapshot scoped)."""

    id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    repository_id: str = Field(min_length=1)
    snapshot_id: str | None = None
    kind: EvidenceKind = "code"
    path: str = ""
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=1, ge=1)
    excerpt: str = ""
    source_tool: str = Field(min_length=1)
    source_ref: str = ""
    confidence: EvidenceConfidence = "direct"
    redacted: bool = False

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: str) -> str:
        return canonical_relative_path(value)

    @field_validator("repository_id", "snapshot_id", "source_tool", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    def model_post_init(self, _context: Any) -> None:
        if self.end_line < self.start_line:
            raise EvidenceValidationError(
                f"invalid line range {self.start_line}-{self.end_line}.",
                code="EVIDENCE_RANGE",
            )
        if self.kind in ("code", "search", "graph") and not self.path:
            raise EvidenceValidationError(
                f"kind {self.kind!r} requires a file path.", code="EVIDENCE_PATH"
            )


def validate_evidence_item(
    data: dict[str, Any],
    *,
    expected_repository_id: str | None = None,
    expected_snapshot_id: str | None = None,
) -> EvidenceItem:
    """Build + validate an EvidenceItem, enforcing repo/snapshot confinement."""
    try:
        item = EvidenceItem(**data)
    except EvidenceValidationError:
        raise
    except Exception as exc:
        raise EvidenceValidationError(str(exc), code="EVIDENCE_INVALID") from exc
    if (
        expected_repository_id is not None
        and item.repository_id != expected_repository_id
    ):
        raise EvidenceValidationError(
            "evidence repository mismatch.", code="EVIDENCE_REPOSITORY_MISMATCH"
        )
    if (
        expected_snapshot_id is not None
        and item.snapshot_id is not None
        and item.snapshot_id != expected_snapshot_id
    ):
        raise EvidenceValidationError(
            "evidence snapshot mismatch.", code="EVIDENCE_SNAPSHOT_MISMATCH"
        )
    return item


def evidence_usable_for(
    item: EvidenceItem | dict[str, Any],
    *,
    repository_id: str,
    snapshot_id: str | None = None,
) -> bool:
    """True when an evidence item may be used for a repo/snapshot request."""
    repo = (
        item.repository_id
        if isinstance(item, EvidenceItem)
        else str(item.get("repository_id", ""))
    )
    if repo != repository_id:
        return False
    snap = (
        item.snapshot_id if isinstance(item, EvidenceItem) else item.get("snapshot_id")
    )
    if snapshot_id is not None and snap is not None and snap != snapshot_id:
        return False
    return True
