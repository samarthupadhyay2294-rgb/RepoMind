"""Shared repository context for investigation tools (Part 6).

Every tool takes a :class:`ToolContext` — never a bare filesystem path —
so repository isolation is structural, not a per-tool afterthought.
"""

from dataclasses import dataclass
from pathlib import Path

from app.db.models.repository import Repository, SourceType
from app.exceptions import IngestionError, ToolError
from app.ingestion.paths import resolve_root
from app.services.ingestion import workspace_for


@dataclass(frozen=True)
class ToolContext:
    repository_id: str
    root: Path  # Resolved, existing repository workspace directory.


def make_context(repository_id: str, root: Path | str) -> ToolContext:
    """Build a context from an already-authorized workspace path (tests/Part 7)."""
    if not repository_id.strip():
        raise ToolError("repository_id is required.", code="TOOL_REPOSITORY_REQUIRED")
    try:
        root_path = resolve_root(root)
    except IngestionError as exc:
        raise ToolError(str(exc), code="TOOL_REPOSITORY_UNAVAILABLE") from exc
    return ToolContext(repository_id=repository_id, root=root_path)


def context_for_repository(repository: Repository) -> ToolContext:
    """Build a context from a Part 3 repository record (same root rules as ingestion)."""
    repository_id = str(repository.id)
    if repository.source_type == SourceType.LOCAL:
        if not repository.local_path:
            raise ToolError(
                "Local repository has no path configured.",
                code="TOOL_REPOSITORY_UNAVAILABLE",
            )
        return make_context(repository_id, repository.local_path)
    workspace = workspace_for(repository.id)
    if not workspace.is_dir():
        raise ToolError(
            "Repository workspace is not prepared yet.",
            code="TOOL_REPOSITORY_UNAVAILABLE",
        )
    return make_context(repository_id, workspace)
