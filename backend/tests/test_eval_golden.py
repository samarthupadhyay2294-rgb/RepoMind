"""Golden evaluation set (plan v2 A.5/§8/§14/§18 starter: 5 questions).

Recall harness over a fixed demo repo using Part 6 tools only — no LLM,
no network. Expand the JSON set (and repos) per §18; every major change
to chunking/prompts/tool policy is compared against this baseline.
"""

import json
import subprocess
from pathlib import Path

import pytest

from app.tools import deps, git, search, symbols
from app.tools.context import make_context

GOLDEN = Path(__file__).parent.parent / "eval" / "golden_questions.json"

LOGIN_PY = '''"""Login flow."""


def authenticate(username, password):
    """Check credentials."""
    return username == "admin"
'''

HANDLERS_PY = '''"""API handlers."""

from src.auth.login import authenticate


def login_handler(request):
    return authenticate(request.user, request.password)
'''

USER_PY = '''"""Models."""


class User:
    def __init__(self, name):
        self.name = name
'''


def build_demo(root: Path) -> None:
    (root / "src" / "auth").mkdir(parents=True)
    (root / "src" / "models").mkdir(parents=True)
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "auth" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "auth" / "login.py").write_text(LOGIN_PY, encoding="utf-8")
    (root / "src" / "models" / "user.py").write_text(USER_PY, encoding="utf-8")
    (root / "src" / "api" / "handlers.py").write_text(HANDLERS_PY, encoding="utf-8")
    _git_commit(root)


CONFIG_PY = '''"""Centralized settings."""

GROQ_MODEL = "openai/gpt-oss-20b"
QDRANT_URL = ""
RETRIEVAL_TOP_K = 8
'''

FACTORY_PY = '''"""Chat-model factory."""

from config import GROQ_MODEL


def get_primary_chat_model():
    """Build the primary reasoning model."""
    return GROQ_MODEL
'''

STORE_PY = '''"""Vector store boundary."""


class QdrantService:
    """Scoped vector operations."""

    def delete_repository(self, repository_id):
        """Delete every vector for one repository."""
        return repository_id
'''

ROUTES_PY = '''"""Chat routes."""

from llm.factory import get_primary_chat_model


def chat_handler(question):
    """Answer one repository question."""
    return get_primary_chat_model()
'''

INDEXING_PY = '''"""Indexing flow."""

from vector.store import QdrantService


async def index_repository(repository_id):
    """Index one repository into the vector store."""
    return QdrantService().delete_repository(repository_id)
'''


def build_config_repo(root: Path) -> None:
    """Second fixture: layered backend (config → factory → routes → store)."""
    (root / "llm").mkdir(parents=True)
    (root / "vector").mkdir(parents=True)
    (root / "api").mkdir(parents=True)
    (root / "services").mkdir(parents=True)
    (root / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    (root / "llm" / "factory.py").write_text(FACTORY_PY, encoding="utf-8")
    (root / "vector" / "store.py").write_text(STORE_PY, encoding="utf-8")
    (root / "api" / "routes.py").write_text(ROUTES_PY, encoding="utf-8")
    (root / "services" / "indexing.py").write_text(INDEXING_PY, encoding="utf-8")
    _git_commit(root)


def _git_commit(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.t", "commit", "-m", "demo"],
        cwd=root,
        capture_output=True,
        check=True,
    )


def _files_for(tool: str, entry: dict) -> list[str]:
    args = entry["args"]
    ctx = entry["_ctx"]
    if tool == "search_code":
        return [m.file_path for m in search.search_code(ctx, **args).matches]
    if tool == "get_symbol":
        return [m.file_path for m in symbols.get_symbol(ctx, **args).matches]
    if tool == "find_references":
        return [m.file_path for m in symbols.find_references(ctx, **args).matches]
    if tool == "dependency_graph":
        graph = deps.dependency_graph(ctx, **args)
        return [e.target for e in graph.edges if e.source == args["path"]]
    if tool == "git_log":
        return [c.commit_sha for c in git.git_log(ctx, **args).commits]
    raise AssertionError(f"unknown golden tool: {tool}")


def test_golden_set_recall(tmp_path: Path) -> None:
    try:
        demo = tmp_path / "demo"
        demo.mkdir()
        build_demo(demo)
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()
        build_config_repo(config_repo)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git CLI not available for golden repo fixture")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden["questions"]) >= 10
    contexts = {
        "demo": make_context("golden-demo", demo),
        "config": make_context("golden-config", config_repo),
    }
    failures = []
    for entry in golden["questions"]:
        fixture = entry.get("fixture", "demo")
        assert fixture in contexts, f"{entry['id']}: unknown fixture {fixture!r}"
        entry["_ctx"] = contexts[fixture]
        found = _files_for(entry["tool"], entry)
        for expected in entry.get("expect_files", []):
            if expected not in found:
                failures.append(
                    f"{entry['id']}: expected {expected} via {entry['tool']}"
                )
        if "expect_min_results" in entry and len(found) < entry["expect_min_results"]:
            failures.append(f"{entry['id']}: only {len(found)} results")
    assert not failures, "; ".join(failures)


def test_identifier_search_is_case_insensitive_across_files(
    tmp_path: Path,
) -> None:
    """Generic lexical-search contract (not Q-specific): an identifier query
    matches every file containing it regardless of query casing, and a query
    for an identifier present nowhere returns no matches (no fabrication)."""
    try:
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()
        build_config_repo(config_repo)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git CLI not available for golden repo fixture")
    ctx = make_context("golden-config-ci", config_repo)
    for query in ("GROQ_MODEL", "groq_model", "Groq_Model"):
        found = {m.file_path for m in search.search_code(ctx, query=query).matches}
        assert found == {"config.py", "llm/factory.py"}, query
    assert search.search_code(ctx, query="NO_SUCH_IDENTIFIER_XYZ").matches == []
