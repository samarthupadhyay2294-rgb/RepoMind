"""Discovery tests: ordering, ignores, .gitignore, binary, secrets, limits."""

import os
from pathlib import Path

import pytest

from app.ingestion.discovery import discover_files


def write(root: Path, rel: str, content: bytes | str = "x = 1\n") -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    return target


def rels(result) -> list:  # type: ignore[no-untyped-def]
    return [f.rel for f in result.files]


def test_nested_discovery_is_sorted_and_deterministic(tmp_path: Path) -> None:
    write(tmp_path, "src/main.py")
    write(tmp_path, "src/config.py")
    write(tmp_path, "tests/test_app.py")
    write(tmp_path, "README.md", "# hi\n")
    write(tmp_path, "src/nested/deep.py")
    first = rels(discover_files(tmp_path))
    assert first == sorted(first)
    assert first == rels(discover_files(tmp_path))
    assert first == [
        "README.md",
        "src/config.py",
        "src/main.py",
        "src/nested/deep.py",
        "tests/test_app.py",
    ]


def test_empty_repository(tmp_path: Path) -> None:
    result = discover_files(tmp_path)
    assert result.files == [] and result.skipped == []


def test_default_ignored_dirs_pruned(tmp_path: Path) -> None:
    write(tmp_path, "src/app.py")
    write(tmp_path, ".git/HEAD", "ref\n")
    write(tmp_path, "node_modules/lib/index.js", "x\n")
    write(tmp_path, "__pycache__/app.pyc", b"\x00\x01")
    write(tmp_path, ".venv/lib/x.py")
    assert rels(discover_files(tmp_path)) == ["src/app.py"]


def test_gitignore_respected(tmp_path: Path) -> None:
    write(tmp_path, ".gitignore", "*.log\ngenerated/\n")
    write(tmp_path, "src/app.py")
    write(tmp_path, "debug.log", "x\n")
    write(tmp_path, "generated/out.js", "x\n")
    result = discover_files(tmp_path)
    assert rels(result) == ["src/app.py"]
    skipped = {s[0]: s[1] for s in result.skipped}
    assert skipped["debug.log"] == "ignored"
    assert skipped["generated/"] == "ignored"  # Pruned dir recorded once.


def test_binary_by_extension_and_content(tmp_path: Path) -> None:
    write(tmp_path, "img.png", b"\x89PNG\r\n")
    write(tmp_path, "doc.txt", b"text\x00with-nul\n")
    write(tmp_path, "ok.txt", "plain\n")
    result = discover_files(tmp_path)
    assert rels(result) == ["ok.txt"]
    assert {s[1] for s in result.skipped} == {"binary"}


def test_secret_files_skipped(tmp_path: Path) -> None:
    write(tmp_path, ".env", "K=v\n")
    write(tmp_path, ".env.local", "K=v\n")
    write(tmp_path, "cert.pem", "x\n")
    write(tmp_path, "id_rsa", "x\n")
    write(tmp_path, "src/app.py")
    result = discover_files(tmp_path)
    assert rels(result) == ["src/app.py"]
    assert all(s[1] == "secret" for s in result.skipped)


def test_oversized_files_skipped(tmp_path: Path) -> None:
    write(tmp_path, "big.py", "x" * 100)
    write(tmp_path, "small.py", "y\n")
    result = discover_files(tmp_path, max_bytes=10)
    assert rels(result) == ["small.py"]
    assert result.skipped[0][1] == "too_large"


def test_unsupported_extensions_skipped(tmp_path: Path) -> None:
    write(tmp_path, "app.py")
    write(tmp_path, "data.xyz", "???\n")
    result = discover_files(tmp_path)
    assert rels(result) == ["app.py"]


def test_file_limit_caps_results(tmp_path: Path) -> None:
    for i in range(5):
        write(tmp_path, f"f{i}.py")
    result = discover_files(tmp_path, max_files=2)
    assert len(result.files) == 2
    assert any(s[1] == "file_limit" for s in result.skipped)


def test_symlink_escape_skipped(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("evil = 1\n", encoding="utf-8")
    link = tmp_path / "repo" / "link.py"
    link.parent.mkdir(parents=True, exist_ok=True)
    write(link.parent, "ok.py")
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = discover_files(link.parent)
    assert rels(result) == ["ok.py"]
    assert ("link.py", "symlink_escape", "Symlink leaves the workspace.") in [
        (s[0], s[1], s[2]) for s in result.skipped
    ]
