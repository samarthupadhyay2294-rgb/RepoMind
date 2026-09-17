"""Git acquisition tests. Git itself is mocked — no network, no GitHub."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.db.models.repository import Repository, SourceType
from app.exceptions import IngestionError
from app.services import acquisition as acq
from app.services.ingestion import workspace_for


def _repo(source_type: SourceType, **kwargs: object) -> Repository:
    return Repository(
        id=uuid4(),
        owner_id="o",
        name="n",
        source_type=source_type,
        **kwargs,  # type: ignore[arg-type]
    )


def test_local_acquire_uses_existing_directory(tmp_path: Path) -> None:
    repo = _repo(SourceType.LOCAL, local_path=str(tmp_path))
    result = acq.acquire_repository(repo)
    assert result.root == tmp_path.resolve()
    assert result.fresh_clone is False


def test_git_rejects_unsafe_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    repo = _repo(SourceType.GIT, source_url="file:///etc/passwd")
    with pytest.raises(IngestionError, match="Unsafe repository URL"):
        acq.acquire_repository(repo)


def _ok_clone(dest_marker: list[str]):
    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[1] == "clone":
            dest = Path(argv[-1])
            (dest / ".git").mkdir(parents=True)
            (dest / "a.py").write_text("x = 1\n", encoding="utf-8")
            dest_marker.append(str(dest))
        return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")

    return _run


def test_git_shallow_clone_into_own_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    seen: list[str] = []
    monkeypatch.setattr(subprocess, "run", _ok_clone(seen))
    repo = _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    result = acq.acquire_repository(repo)
    assert result.root == workspace_for(repo.id).resolve()
    assert result.commit_sha == "abc123"
    assert result.fresh_clone is True
    clone_argv_dest = seen[0]
    assert Path(clone_argv_dest) == workspace_for(repo.id)


def test_clone_uses_depth_one_and_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    captured: list[list[str]] = []

    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        captured.append(argv)
        (Path(argv[-1]) / ".git").mkdir(parents=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    repo = _repo(
        SourceType.GIT, source_url="https://example.com/o/r.git", default_branch="main"
    )
    acq.acquire_repository(repo)
    clone = captured[0]
    assert clone[:3] == ["git", "clone", "--depth"]
    assert clone[3] == "1"
    assert "--branch" in clone and "main" in clone


def test_clone_failure_cleans_partial_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))

    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[1] == "clone":
            (Path(argv[-1]) / ".git").mkdir(parents=True)
            return SimpleNamespace(returncode=1, stdout="", stderr="nope")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    repo = _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    with pytest.raises(IngestionError, match="clone failed"):
        acq.acquire_repository(repo)
    assert not workspace_for(repo.id).exists()


def test_clone_timeout_is_controlled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "REPOSITORY_CLONE_TIMEOUT_SECONDS", 5)

    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=5)

    monkeypatch.setattr(subprocess, "run", _run)
    repo = _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    with pytest.raises(IngestionError, match="timed out"):
        acq.acquire_repository(repo)
    assert not workspace_for(repo.id).exists()


def test_oversized_workspace_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_REPOSITORY_BYTES", 10)

    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[1] == "clone":
            dest = Path(argv[-1])
            (dest / ".git").mkdir(parents=True)
            (dest / "big.bin").write_bytes(b"0" * 100)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    repo = _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    with pytest.raises(IngestionError, match="size limit"):
        acq.acquire_repository(repo)
    assert not workspace_for(repo.id).exists()


def test_repositories_never_share_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", _ok_clone([]))
    first = acq.acquire_repository(
        _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    )
    second = acq.acquire_repository(
        _repo(SourceType.GIT, source_url="https://example.com/o/r.git")
    )
    assert first.root != second.root
    # Both confined under the same storage root, in per-repository dirs.
    assert first.root.parent.parent == second.root.parent.parent == tmp_path.resolve()
