"""End-to-end ingestion tests on small temporary repositories."""

from pathlib import Path

import pytest

from app.db.models.repository import Repository, SourceType
from app.exceptions import IngestionError
from app.services.ingestion import ingest_directory, ingest_repository, workspace_for


def make_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "def login(user):\n    return True\n", encoding="utf-8"
    )
    (root / "src" / "util.js").write_text(
        "export function add(a, b) {\n  return a + b;\n}\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (root / "img.png").write_bytes(b"\x89PNG\r\n")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")


def test_end_to_end_ingestion(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    make_repo(root)
    result = ingest_directory(root, repository_id="repo-1", commit_sha="sha1")
    assert result.files_processed == 3
    assert result.chunks_created >= 3
    assert result.commit_sha == "sha1"
    assert {c.file_path for c in result.chunks} == {
        "src/app.py",
        "src/util.js",
        "README.md",
    }
    by_file = {c.file_path: c for c in result.chunks}
    assert by_file["src/app.py"].symbol == "login"
    assert by_file["src/app.py"].start_line == 1
    assert by_file["README.md"].chunk_type == "doc"
    assert by_file["src/util.js"].chunk_type == "code"
    assert set(result.file_hashes) == {"src/app.py", "src/util.js", "README.md"}
    assert "repo-1" == result.repository_id
    # No absolute workspace paths leak into the public result.
    assert str(root) not in result.model_dump_json()
    skipped = {s.file_path: s.category for s in result.skipped}
    assert skipped[".env"] == "secret"
    assert skipped["img.png"] == "binary"


def test_ingestion_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    make_repo(root)
    first = ingest_directory(root, repository_id="r")
    second = ingest_directory(root, repository_id="r")
    assert [c.content_hash for c in first.chunks] == [
        c.content_hash for c in second.chunks
    ]


def test_ingest_local_repository_record(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    make_repo(root)
    record = Repository(
        owner_id="o", name="n", source_type=SourceType.LOCAL, local_path=str(root)
    )
    result = ingest_repository(record)
    assert result.files_processed == 3


def test_ingest_local_missing_path_raises() -> None:
    record = Repository(
        owner_id="o",
        name="n",
        source_type=SourceType.LOCAL,
        local_path="/nonexistent-xyz",
    )
    with pytest.raises(IngestionError):
        ingest_repository(record)


def test_ingest_git_without_workspace_acquires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Gap #1: Git repos clone into their workspace instead of raising."""
    import subprocess
    from types import SimpleNamespace

    from app.config import settings

    monkeypatch.setattr(settings, "REPOSITORY_STORAGE_PATH", str(tmp_path / "store"))

    def _run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[1] == "clone":
            dest = Path(argv[-1])
            (dest / ".git").mkdir(parents=True)
            (dest / "a.py").write_text("x = 1\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    record = Repository(
        owner_id="o",
        name="n",
        source_type=SourceType.GIT,
        source_url="https://x/y.git",
    )
    result = ingest_repository(record)
    assert result.files_processed == 1


def test_workspace_for_rejects_traversal() -> None:
    with pytest.raises(IngestionError):
        workspace_for("../evil")
    assert workspace_for("abc-123").name == "repo"
