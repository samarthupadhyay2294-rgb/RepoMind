"""Path confinement tests: traversal, absolute, Windows, symlinks, isolation."""

from pathlib import Path

import pytest

from app.exceptions import IngestionError
from app.ingestion.paths import is_within, resolve_root, safe_join


def test_resolve_root_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(IngestionError):
        resolve_root(tmp_path / "nope")


def test_safe_join_allows_nested(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    assert safe_join(root, "src/app.py") == root / "src" / "app.py"


def test_safe_join_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    for rel in ("../secret.txt", "../../secret.txt", "a/../../secret.txt"):
        with pytest.raises(IngestionError):
            safe_join(root, rel)


def test_safe_join_rejects_absolute_and_windows_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    for rel in (
        "/etc/passwd",
        "C:/Windows/System32/x",
        "C:\\Windows\\x",
        "\\server\\x",
    ):
        with pytest.raises(IngestionError):
            safe_join(root, rel)


def test_is_within(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    assert is_within(root, root / "a.py")
    assert not is_within(root, tmp_path / "other.py")


def test_repositories_are_isolated(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    with pytest.raises(IngestionError):
        safe_join(repo_a, "../b/secret.py")
    assert not is_within(repo_a, repo_b / "code.py")
