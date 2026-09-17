"""Filesystem confinement: every path stays inside its repository root."""

from pathlib import Path

from app.exceptions import IngestionError


def resolve_root(root: Path | str) -> Path:
    """Resolve a workspace root; must be an existing directory."""
    resolved = Path(root).resolve()
    if not resolved.is_dir():
        raise IngestionError("Repository workspace is not available.")
    return resolved


def is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def safe_join(root: Path, rel: str) -> Path:
    """Join a user/relative path onto root, rejecting traversal and escapes."""
    candidate = Path(rel)
    if candidate.is_absolute() or candidate.drive:
        raise IngestionError(f"Path escapes the repository workspace: {rel}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise IngestionError(f"Path escapes the repository workspace: {rel}")
    return resolved
