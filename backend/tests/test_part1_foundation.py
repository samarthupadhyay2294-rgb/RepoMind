"""Part 1 foundation tests: snapshots, evidence, citations, tools, agent,
security, Qdrant isolation, flags, and cache keys. All mocked — no network.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.nodes import (
    AgentDeps,
    evaluate_node,
    route_after_classify,
    tool_call_node,
    validate_citations,
)
from app.agent.state import initial_state
from app.config import settings as app_settings
from app.db.base import Base  # noqa: F401  (ensure metadata registration)
import app.db.models  # noqa: F401
from app.db.models.repository import Repository, RepositoryStatus, SourceType
from app.db.models.snapshot import SnapshotStatus
from app.evidence import (
    EvidenceValidationError,
    deduplicate_evidence,
    evidence_usable_for,
    find_unsupported_prose_refs,
    pack_evidence,
    redact_text,
    validate_evidence_item,
    validate_structured_citations,
)
from app.evidence.normalize import normalize_tool_result
from app.services import snapshots as snapshot_service
from app.services.evidence_cache import evidence_cache_key
from app.services.qdrant_service import MetadataFilter, build_filter, build_payload
from app.agent.nodes import resolve_tool_args
from app.tools.context import make_context
from app.tools.registry import available_tool_names, capability_error


# -- helpers ---------------------------------------------------------------


def ev_dict(
    path: str = "src/auth.py",
    start: int = 4,
    end: int = 6,
    repo: str = "repo-a",
    snapshot: str | None = "snap-1",
    score: float = 0.9,
    tool: str = "read_file",
    confidence: str = "direct",
) -> dict:
    return {
        "source_type": "tool",
        "repository_id": repo,
        "snapshot_id": snapshot,
        "file_path": path,
        "path": path,
        "start_line": start,
        "end_line": end,
        "content": "def authenticate(name):",
        "excerpt": "def authenticate(name):",
        "relevance_score": score,
        "tool_name": tool,
        "source_tool": tool,
        "confidence": confidence,
    }


def run(coro):
    return asyncio.run(coro)


async def make_repo(session: AsyncSession, name: str = "demo") -> Repository:
    repo = Repository(
        owner_id="owner-1",
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        source_type=SourceType.LOCAL,
        local_path="/tmp",
        status=RepositoryStatus.PENDING,
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    return repo


# -- snapshots --------------------------------------------------------------


def test_snapshot_creation_and_unique_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _run() -> None:
        async with session_factory() as session:
            repo = await make_repo(session)
            first = await snapshot_service.begin_snapshot(
                session, repo.id, revision="abc123"
            )
            second = await snapshot_service.begin_snapshot(
                session, repo.id, revision="abc123"
            )
            assert first.id != second.id
            assert first.repository_id == repo.id == second.repository_id
            assert first.manifest_hash == second.manifest_hash
            assert first.embedding_model == "mistral-embed"
            assert first.embedding_dimensions == 1024

    run(_run())


def test_snapshot_activation_and_failed_run_keeps_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _run() -> None:
        async with session_factory() as session:
            repo = await make_repo(session)
            good = await snapshot_service.begin_snapshot(
                session, repo.id, revision="v1"
            )
            await snapshot_service.activate_snapshot(session, good.id)
            bad = await snapshot_service.begin_snapshot(session, repo.id, revision="v2")
            await snapshot_service.fail_snapshot(session, bad.id, "boom")
            active = await snapshot_service.get_active_snapshot(session, repo.id)
            assert active is not None and active.id == good.id
            assert active.status == SnapshotStatus.READY

    run(_run())


def test_snapshot_manifest_hash_deterministic_without_revision() -> None:
    hashes = [
        snapshot_service.manifest_hash_for(None, {"b.py": "h2", "a.py": "h1"})
        for _ in range(2)
    ]
    assert hashes[0] == hashes[1]
    assert snapshot_service.manifest_hash_for(
        "rev", None
    ) != snapshot_service.manifest_hash_for(None, {"a.py": "h1"})


def test_snapshot_repository_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _run() -> None:
        async with session_factory() as session:
            repo_a = await make_repo(session, "a")
            repo_b = await make_repo(session, "b")
            snap = await snapshot_service.begin_snapshot(
                session, repo_a.id, revision="v1"
            )
            await snapshot_service.activate_snapshot(session, snap.id)
            assert (
                await snapshot_service.get_active_snapshot(session, repo_b.id) is None
            )
            # Evidence usability respects both boundaries.
            item = validate_evidence_item(
                {
                    "repository_id": str(repo_a.id),
                    "snapshot_id": str(snap.id),
                    "kind": "code",
                    "path": "src/a.py",
                    "start_line": 1,
                    "end_line": 2,
                    "excerpt": "x",
                    "source_tool": "read_file",
                }
            )
            assert evidence_usable_for(
                item, repository_id=str(repo_a.id), snapshot_id=str(snap.id)
            )
            assert not evidence_usable_for(item, repository_id=str(repo_b.id))
            assert not evidence_usable_for(
                item, repository_id=str(repo_a.id), snapshot_id="other"
            )

    run(_run())


def test_snapshot_backfill_baseline(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def _run() -> None:
        async with session_factory() as session:
            repo = await make_repo(session)
            baseline = await snapshot_service.ensure_baseline_snapshot(
                session, repo.id, revision="old"
            )
            assert baseline.is_active is True
            again = await snapshot_service.ensure_baseline_snapshot(session, repo.id)
            assert again.id == baseline.id  # no duplicate baseline rows

    run(_run())


# -- evidence contract -------------------------------------------------------


def test_evidence_valid_item() -> None:
    item = validate_evidence_item(
        {
            "repository_id": "repo-a",
            "snapshot_id": "snap-1",
            "kind": "code",
            "path": "backend/app/auth.py",
            "start_line": 20,
            "end_line": 35,
            "excerpt": "x = 1",
            "source_tool": "read_file",
            "source_ref": "call-1",
            "confidence": "direct",
        },
        expected_repository_id="repo-a",
        expected_snapshot_id="snap-1",
    )
    assert item.path == "backend/app/auth.py"


@pytest.mark.parametrize("path", ["/etc/passwd", "C:\\Windows\\x.py", "\\\\share\\x"])
def test_evidence_rejects_absolute_paths(path: str) -> None:
    with pytest.raises(EvidenceValidationError):
        validate_evidence_item(
            {
                "repository_id": "r",
                "kind": "code",
                "path": path,
                "start_line": 1,
                "end_line": 1,
                "excerpt": "x",
                "source_tool": "read_file",
            }
        )


@pytest.mark.parametrize("path", ["../secret.txt", "a/../../x.py", "a/../.."])
def test_evidence_rejects_traversal(path: str) -> None:
    with pytest.raises(EvidenceValidationError):
        validate_evidence_item(
            {
                "repository_id": "r",
                "kind": "code",
                "path": path,
                "start_line": 1,
                "end_line": 1,
                "excerpt": "x",
                "source_tool": "read_file",
            }
        )


def test_evidence_rejects_invalid_range_and_mismatch() -> None:
    with pytest.raises(EvidenceValidationError):
        validate_evidence_item(
            {
                "repository_id": "r",
                "kind": "code",
                "path": "a.py",
                "start_line": 10,
                "end_line": 5,
                "excerpt": "x",
                "source_tool": "read_file",
            }
        )
    with pytest.raises(EvidenceValidationError):
        validate_evidence_item(
            {
                "repository_id": "repo-a",
                "kind": "code",
                "path": "a.py",
                "start_line": 1,
                "end_line": 1,
                "excerpt": "x",
                "source_tool": "read_file",
            },
            expected_repository_id="repo-b",
        )
    with pytest.raises(EvidenceValidationError):
        validate_evidence_item(
            {
                "repository_id": "repo-a",
                "snapshot_id": "snap-1",
                "kind": "code",
                "path": "a.py",
                "start_line": 1,
                "end_line": 1,
                "excerpt": "x",
                "source_tool": "read_file",
            },
            expected_repository_id="repo-a",
            expected_snapshot_id="snap-2",
        )


def test_evidence_dedupe_and_ranking() -> None:
    strong = ev_dict(score=0.9, tool="read_file", confidence="direct")
    weak = ev_dict(start=5, end=8, score=0.2, tool="search_code", confidence="derived")
    unique = ev_dict(path="src/other.py", start=1, end=2, score=0.1)
    kept, removed = deduplicate_evidence([weak, strong, unique])
    assert removed == 1
    assert len(kept) == 2
    assert any(i["path"] == "src/other.py" for i in kept)  # unique kept
    assert kept[0]["source_tool"] == "read_file"  # direct first
    assert "merged_sources" in kept[0] or kept[0]["path"] == "src/auth.py"


def test_evidence_dedupe_never_crosses_boundaries() -> None:
    a = ev_dict(repo="repo-a")
    b = ev_dict(repo="repo-b")
    kept, removed = deduplicate_evidence([a, b])
    assert (len(kept), removed) == (2, 0)


def test_evidence_budget_metadata() -> None:
    items = [ev_dict(path=f"src/f{i}.py", score=float(10 - i)) for i in range(10)]
    for item in items:
        item["content"] = "x" * 5000
    kept, meta = pack_evidence(items, max_items=3, max_chars=7000)
    assert meta["evidence_items_total"] == 10
    assert meta["evidence_items_used"] == len(kept) < 10
    assert meta["evidence_truncated"] is True


# -- citations ---------------------------------------------------------------


def test_citation_valid_structured() -> None:
    out = validate_structured_citations(
        [{"file_path": "src/auth.py", "start_line": 4, "end_line": 6}],
        [ev_dict()],
        "repo-a",
        "snap-1",
    )
    assert len(out) == 1


def test_citation_invalid_and_partial_overlap() -> None:
    assert (
        validate_structured_citations(
            [{"file_path": "src/missing.py", "start_line": 1, "end_line": 2}],
            [ev_dict()],
            "repo-a",
        )
        == []
    )
    assert (
        validate_structured_citations(
            [{"file_path": "src/auth.py", "start_line": 100, "end_line": 200}],
            [ev_dict()],
            "repo-a",
        )
        == []
    )
    # Partial overlap is supported.
    assert (
        len(
            validate_structured_citations(
                [{"file_path": "src/auth.py", "start_line": 6, "end_line": 10}],
                [ev_dict()],
                "repo-a",
            )
        )
        == 1
    )


def test_citation_wrong_repo_and_snapshot() -> None:
    assert (
        validate_structured_citations(
            [{"file_path": "src/auth.py", "start_line": 4, "end_line": 6}],
            [ev_dict(repo="repo-b")],
            "repo-a",
        )
        == []
    )
    assert (
        validate_structured_citations(
            [{"file_path": "src/auth.py", "start_line": 4, "end_line": 6}],
            [ev_dict(snapshot="snap-2")],
            "repo-a",
            "snap-1",
        )
        == []
    )
    assert (
        validate_citations(
            "See `src/auth.py:4-6`.", [ev_dict(snapshot="snap-2")], "repo-a", "snap-1"
        )
        == []
    )


def test_prose_citations_valid_invalid_mixed_none() -> None:
    assert (
        find_unsupported_prose_refs("See `src/auth.py:4-6`.", [ev_dict()], "repo-a")
        == []
    )
    assert find_unsupported_prose_refs(
        "See `src/auth.py:50-60`.", [ev_dict()], "repo-a"
    ) == ["`src/auth.py:50-60`"]
    mixed = "A `src/auth.py:4-6` and B `src/nope.py:1-2`."
    assert find_unsupported_prose_refs(mixed, [ev_dict()], "repo-a") == [
        "`src/nope.py:1-2`"
    ]
    assert find_unsupported_prose_refs("No refs here.", [ev_dict()], "repo-a") == []


# -- tools --------------------------------------------------------------------


def test_structured_args_valid_and_invalid() -> None:
    assert resolve_tool_args(
        "read_file", {"path": "backend/app/auth.py", "start_line": 20, "end_line": 45}
    ) == {"path": "backend/app/auth.py", "start_line": 20, "end_line": 45}
    assert (
        resolve_tool_args(
            "search_code",
            {"query": "Authorization", "path_prefix": "backend/", "language": "python"},
        )
        is not None
    )
    assert (
        resolve_tool_args("read_file", {"path": "../evil.py"}) is not None
    )  # shape-valid; tools confine
    assert (
        resolve_tool_args("read_file", {"path": "a.py", "start_line": 9, "end_line": 2})
        is None
    )
    assert (
        resolve_tool_args("search_code", {"query": "x", "max_results": 99999}) is None
    )
    assert resolve_tool_args("read_file", {"path": "a.py", "nope": 1}) is None


def test_capability_errors_unknown_and_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert capability_error("nope")["code"] == "TOOL_UNKNOWN"
    monkeypatch.setattr(app_settings, "ENABLED_VALIDATIONS", "")
    assert capability_error("run_validation")["code"] == "TOOL_DISABLED"
    assert "run_validation" not in available_tool_names()


def test_unknown_tool_step_records_capability_error(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    deps = AgentDeps(
        invoke_llm=lambda p: "x",
        retrieve=None,  # type: ignore[arg-type]
        tool_context=make_context("repo-a", root),
    )
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [{"action": "nuke_disk", "target": "x", "purpose": "evil"}]
    out = run(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert out["tool_calls"][0]["warning"] == "TOOL_UNKNOWN"
    assert out["tool_calls"][0]["ok"] is False


def test_semantic_search_example_shape_validated() -> None:
    """Task examples: semantic_search{query, limit:8} shape is bounded."""

    async def _fake_retrieve(repository_id: str, query: str, top_k: int | None = None):
        assert query == "401 unauthorized authentication"
        assert top_k == 8
        return []

    root = Path(".").resolve()
    deps = AgentDeps(
        invoke_llm=lambda p: "x",
        retrieve=_fake_retrieve,  # type: ignore[arg-type]
        tool_context=make_context("repo-a", root),
    )
    state = initial_state("q?", "repo-a", "t")
    state["current_plan"] = [
        {
            "action": "semantic_retrieval",
            "target": "",
            "purpose": "search",
            "args": {"query": "401 unauthorized authentication", "top_k": 8},
        }
    ]
    out = run(tool_call_node(state, {"configurable": {"thread_id": "t", "deps": deps}}))
    assert out["tool_calls"][0]["ok"] is True


# -- agent loop -----------------------------------------------------------------


def _deps_for(repo_root: Path, llm) -> AgentDeps:
    async def _retrieve(repository_id: str, query: str, top_k: int | None = None):
        return []

    return AgentDeps(
        invoke_llm=llm,
        retrieve=_retrieve,
        tool_context=make_context("repo-a", repo_root),
    )


def test_agent_sufficient_evidence_and_stop_reason(tmp_path: Path) -> None:
    import json as _json

    def llm(prompt: str) -> str:
        return _json.dumps(
            {"sufficient": True, "confidence": 0.9, "missing_information": []}
        )

    state = initial_state("q?", "repo-a", "t")
    state["evidence"] = [ev_dict()]
    out = run(
        evaluate_node(
            state,
            {"configurable": {"thread_id": "t", "deps": _deps_for(tmp_path, llm)}},
        )
    )
    assert out["stop_reason"] == "answer_sufficient"


def test_agent_empty_result_tries_alternative(tmp_path: Path) -> None:
    import json as _json

    def llm(prompt: str) -> str:
        return _json.dumps(
            {"sufficient": False, "confidence": 0.2, "missing_information": ["x"]}
        )

    state = initial_state("q?", "repo-a", "t")  # no evidence, first round
    out = run(
        evaluate_node(
            state,
            {"configurable": {"thread_id": "t", "deps": _deps_for(tmp_path, llm)}},
        )
    )
    assert out["decision"] == "plan"  # not forced to answer on one empty round


def test_agent_stop_reasons_limits_and_failures(tmp_path: Path) -> None:
    deps = _deps_for(tmp_path, lambda p: "x")
    cfg = {"configurable": {"thread_id": "t", "deps": deps}}

    def _state(**overrides):
        state = initial_state("q?", "repo-a", "t")
        state.update(overrides)
        return state

    out = run(
        evaluate_node(
            _state(evidence=[ev_dict()], step_count=app_settings.AGENT_MAX_STEPS), cfg
        )
    )
    assert out["stop_reason"] == "max_iterations"
    out = run(
        evaluate_node(
            _state(
                evidence=[ev_dict()], tool_call_count=app_settings.AGENT_MAX_TOOL_CALLS
            ),
            cfg,
        )
    )
    assert out["stop_reason"] == "max_tool_calls"
    # All tool calls failed + no progress → tool_failure.
    stalled = _state(
        evidence=[ev_dict()],
        last_eval_evidence_count=1,
        unproductive_rounds=1,
        tool_calls=[{"tool_name": "read_file", "ok": False}],
    )
    out = run(evaluate_node(stalled, cfg))
    assert out["stop_reason"] == "tool_failure"
    # Repeated stalls without failures → no_viable_next_action.
    stalled2 = _state(
        evidence=[ev_dict()],
        last_eval_evidence_count=1,
        unproductive_rounds=1,
        tool_calls=[{"tool_name": "read_file", "ok": True}],
    )
    out = run(evaluate_node(stalled2, cfg))
    assert out["stop_reason"] == "no_viable_next_action"


def test_agent_llm_failure_and_budget_exhaustion(tmp_path: Path) -> None:
    from app.services.llm_models import LLMUnavailableError

    def down(prompt: str) -> str:
        raise LLMUnavailableError("Ollama is not reachable at x.")

    cfg = {"configurable": {"thread_id": "t", "deps": _deps_for(tmp_path, down)}}
    state = initial_state("q?", "repo-a", "t")
    state["evidence"] = [ev_dict()]
    first = run(evaluate_node(state, cfg))
    assert first["decision"] == "plan"
    state.update(first)
    state["evidence"] = [ev_dict(), ev_dict(path="src/b.py", start=1, end=2)]
    second = run(evaluate_node(state, cfg))
    assert second["stop_reason"] == "llm_error"

    big = initial_state("q?", "repo-a", "t")
    big["evidence"] = [ev_dict(path=f"src/f{i}.py") for i in range(5)]
    for item in big["evidence"]:
        item["content"] = "y" * 50000
    out = run(evaluate_node(big, cfg))
    assert out["stop_reason"] == "budget_exhausted"


def test_agent_selectable_retrieval_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "AGENT_SELECTABLE_RETRIEVAL", False)
    assert route_after_classify({"needs_retrieval": False}) == "retrieve"
    monkeypatch.setattr(app_settings, "AGENT_SELECTABLE_RETRIEVAL", True)
    assert route_after_classify({"needs_retrieval": False}) == "plan"


def test_feature_flags_present() -> None:
    assert app_settings.STRUCTURED_TOOL_ARGS is True
    assert app_settings.SNAPSHOT_INDEXING is True
    assert app_settings.ARCHITECTURE_OVERVIEW is True
    # Local dev default: graph enabled (backend/.env sets DEPENDENCY_GRAPH=true).
    # Production disables it explicitly via DEPENDENCY_GRAPH=false.
    assert app_settings.DEPENDENCY_GRAPH is True
    assert app_settings.DEBUG_INVESTIGATOR is False


# -- security ---------------------------------------------------------------------


def test_security_cross_repo_and_snapshot_citations() -> None:
    assert (
        validate_citations("See `src/auth.py:4-6`.", [ev_dict(repo="repo-b")], "repo-a")
        == []
    )
    assert find_unsupported_prose_refs(
        "See `src/auth.py:4-6`.", [ev_dict(snapshot="snap-2")], "repo-a", "snap-1"
    ) == ["`src/auth.py:4-6`"]


def test_security_traversal_and_symlink_escape(tmp_path: Path) -> None:
    from app.exceptions import ToolError

    root = tmp_path / "repo"
    root.mkdir()
    ctx = make_context("repo-a", root)
    with pytest.raises(ToolError):
        from app.tools.files import read_file

        read_file(ctx, "../evil.txt")
    link = root / "link"
    try:
        link.symlink_to(tmp_path / "outside.txt")
    except OSError:
        pytest.skip("symlinks unavailable")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(ToolError):
        from app.tools.files import read_file as _read

        _read(ctx, "link")


def test_security_secret_redaction() -> None:
    text, hit = redact_text('api_key = "sk-abc123XYZ456" and password=hunter2')
    assert hit is True
    assert "sk-abc123XYZ456" not in text and "hunter2" not in text

    class _Result:
        file_path = "src/a.py"
        start_line = 1
        end_line = 2
        content = 'token = "ghp_abcdefgh12345678"'

    items = normalize_tool_result(
        "read_file", _Result(), repository_id="repo-a", snapshot_id="snap-1"
    )
    assert items[0]["redacted"] is True
    assert "ghp_abcdefgh12345678" not in items[0]["excerpt"]


# -- qdrant -------------------------------------------------------------------------


def test_qdrant_filters_repository_and_snapshot() -> None:
    with pytest.raises(Exception):
        build_filter("")
    filt = build_filter("repo-a", MetadataFilter(snapshot_id="snap-1"))
    keys = {c.key for c in filt.must}
    assert {"repository_id", "snapshot_id"} <= keys
    legacy = build_filter("repo-a")  # pre-snapshot data stays readable
    assert {c.key for c in legacy.must} == {"repository_id"}


def test_qdrant_payload_snapshot_and_dimensions() -> None:
    from app.ingestion.models import IngestedChunk

    chunk = IngestedChunk(
        repository_id="repo-a",
        snapshot_id="snap-1",
        file_path="src/a.py",
        file_hash="h",
        language="python",
        chunk_type="code",
        start_line=1,
        end_line=2,
        content="x",
        content_hash="c",
    )
    payload = build_payload(chunk)
    assert payload["repository_id"] == "repo-a"
    assert payload["snapshot_id"] == "snap-1"
    assert payload["path"] == "src/a.py"
    assert "is_generated" in payload
    assert app_settings.EMBEDDING_DIMENSION == 1024
    assert app_settings.MISTRAL_EMBEDDING_MODEL == "mistral-embed"


def test_indexing_rejects_wrong_dimensions() -> None:
    from app.rag.indexing import _validate_dimensions
    from app.exceptions import EmbeddingError

    with pytest.raises(EmbeddingError):
        _validate_dimensions([[0.0] * 768])


# -- cache ----------------------------------------------------------------------------


def test_cache_keys_isolate_snapshots() -> None:
    a = evidence_cache_key(repository_id="repo-a", snapshot_id="snap-1", query="auth")
    b = evidence_cache_key(repository_id="repo-a", snapshot_id="snap-2", query="auth")
    c = evidence_cache_key(repository_id="repo-b", snapshot_id="snap-1", query="auth")
    assert len({a, b, c}) == 3
    assert "repo-a" in a and "snap-1" in a
