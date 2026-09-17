"""Chunking/hashing/language/parser tests: determinism, lines, metadata."""

from app.ingestion import hashing
from app.ingestion.chunking import chunk_parsed_file, symbol_for
from app.ingestion.language import chunk_type_for, detect_language
from app.ingestion.parsers import PythonAstParser, parse_file

REPO = "repo-1"


def make_chunks(content: str, **kwargs):  # type: ignore[no-untyped-def]
    parsed = parse_file(content, "src/a.py", "python")
    return chunk_parsed_file(
        parsed,
        repository_id=REPO,
        commit_sha="abc",
        file_path="src/a.py",
        file_hash="fh",
        language="python",
        **kwargs,
    )


def test_language_detection() -> None:
    assert detect_language("a.py") == "python"
    assert detect_language("b.TS") == "typescript"
    assert detect_language("c.jsx") == "javascript"
    assert detect_language("d.yml") == "yaml"
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("nope.xyz") is None
    assert chunk_type_for("python") == "code"
    assert chunk_type_for("markdown") == "doc"
    assert chunk_type_for("json") == "data"


def test_chunk_boundaries_and_preservation() -> None:
    content = "\n".join(f"line {i}" for i in range(1, 11)) + "\n"
    chunks = make_chunks(content, max_lines=4, max_chars=10_000)
    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 4), (5, 8), (9, 10)]
    assert "\n".join(c.content for c in chunks) == content.rstrip("\n")
    assert all(c.end_line - c.start_line + 1 <= 4 for c in chunks)


def test_char_limit_splits_long_lines() -> None:
    content = "x = '" + "a" * 100 + "'\ny = 2\n"
    chunks = make_chunks(content, max_lines=100, max_chars=30)
    assert len(chunks) == 2
    assert chunks[0].start_line == 1 and chunks[1].start_line == 2


def test_chunks_are_deterministic() -> None:
    content = "def f():\n    return 1\n\n\nclass A:\n    pass\n"
    first = make_chunks(content, max_lines=3, max_chars=200)
    second = make_chunks(content, max_lines=3, max_chars=200)
    assert [c.content_hash for c in first] == [c.content_hash for c in second]
    assert [(c.start_line, c.end_line) for c in first] == [
        (c.start_line, c.end_line) for c in second
    ]


def test_symbol_attribution() -> None:
    content = "import os\n\n\ndef login(user):\n    return True\n\n\nclass Auth:\n    def check(self):\n        return False\n"
    chunks = make_chunks(content, max_lines=3, max_chars=10_000)
    by_start = {c.start_line: c for c in chunks}
    assert by_start[1].symbol is None
    assert by_start[4].symbol == "login"
    assert by_start[10].symbol == "check"
    assert all(c.language == "python" and c.chunk_type == "code" for c in chunks)
    assert all(c.repository_id == REPO and c.commit_sha == "abc" for c in chunks)


def test_malformed_python_falls_back_to_plain() -> None:
    chunks = make_chunks("def broken(:\n  oops\n", max_lines=100, max_chars=10_000)
    assert len(chunks) == 1
    assert chunks[0].symbol is None
    assert "broken" in chunks[0].content


def test_empty_file_yields_no_chunks() -> None:
    assert make_chunks("") == []


def test_hash_properties() -> None:
    assert hashing.hash_text("hello") == hashing.hash_text("hello")
    assert hashing.hash_text("hello") != hashing.hash_text("world")
    assert len(hashing.hash_text("hello")) == 64


def test_symbol_for_picks_innermost() -> None:
    parser = PythonAstParser()
    parsed = parser.parse("class A:\n    def m(self):\n        return 1\n", "a.py")
    assert symbol_for(parsed.symbols, 3) == "m"
    assert symbol_for(parsed.symbols, 1) == "A"
    assert symbol_for([], 1) is None
