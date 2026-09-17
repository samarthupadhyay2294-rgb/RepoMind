"""Part 4/5 tests: debug investigator (input, verdicts, isolation, API)."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models.investigation import InvestigationAction
from app.investigations import service as inv_service
from app.investigations.schemas import InvestigationCreate
from tests.conftest import use_owner


@pytest.fixture(autouse=True)
def _investigator_flags(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEBUG_INVESTIGATOR", True)
    monkeypatch.setattr(settings, "ARCHITECTURE_OVERVIEW", True)
    yield


AUTH_PY = '''"""Auth."""

def verify_token(token):
    """Check token."""
    if not token:
        raise PermissionError("401 Unauthorized")
    return True
'''

MAIN_PY = '''"""App."""

from app.auth import verify_token


def login(token):
    return verify_token(token)
'''


def _write_debug_repo(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "auth.py").write_text(AUTH_PY, encoding="utf-8")
    (root / "app" / "main.py").write_text(MAIN_PY, encoding="utf-8")


async def _make_repo(session: AsyncSession, owner: str, name: str, root: Path):
    from app.schemas.repository import RepositoryCreate
    from app.db.models.repository import SourceType
    from app.services import repositories as repo_service

    return await repo_service.create_repository(
        session,
        owner,
        RepositoryCreate(name=name, source_type=SourceType.LOCAL, local_path=str(root)),
    )


async def _snapshot(session: AsyncSession, repo_id: UUID, rev: str = "r1"):
    from app.services import snapshots as snap_service

    begun = await snap_service.begin_snapshot(session, repo_id, revision=rev)
    return await snap_service.activate_snapshot(session, begun.id)


class _CannedDebugLLM:
    """Deterministic stand-in: search once for verify_token, then answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def __call__(self, prompt: str) -> str:
        if "classify repository questions" in prompt:
            return json.dumps({"request_type": "bug_investigation", "confidence": 0.9})
        if "plan read-only" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "action": "search_code",
                            "target": "verify_token",
                            "purpose": "find token check",
                        }
                    ]
                }
            )
        if "judge whether" in prompt:
            return json.dumps(
                {"sufficient": True, "confidence": 0.9, "missing_information": []}
            )
        return self.answer


def _deps_for(root: Path, repository_id: str, answer: str):
    from app.agent.nodes import AgentDeps
    from app.tools.context import make_context

    async def no_hits(repository_id: str, query: str, top_k: int | None = None):
        return []

    return AgentDeps(
        invoke_llm=_CannedDebugLLM(answer),
        retrieve=no_hits,
        tool_context=make_context(repository_id, root),
    )


# ---- unit: input redaction / frames / verdicts --------------------------------


def test_input_redaction_strips_secrets() -> None:
    payload = InvestigationCreate(
        error_text="Login fails with password=hunter2-secret",
        stack_trace='token="sk-abc123xyz" failed',
    )
    redacted = inv_service.redact_input(payload)
    assert "hunter2" not in redacted["error_text"]
    assert "sk-abc123xyz" not in (redacted["stack_trace"] or "")
    assert "[REDACTED]" in (redacted["stack_trace"] or "")


def test_input_rejects_empty_error() -> None:
    with pytest.raises(Exception):
        inv_service.redact_input(InvestigationCreate(error_text="   "))


def test_simplified_form_payload_reaches_question() -> None:
    payload = InvestigationCreate(
        error_text="401 Unauthorized when signing in",
        affected_route="backend/app/auth.py",
    )
    redacted = inv_service.redact_input(payload)
    assert redacted["error_text"] == "401 Unauthorized when signing in"
    assert redacted["affected_route"] == "backend/app/auth.py"
    question = inv_service.build_question(redacted)
    assert "401 Unauthorized when signing in" in question
    assert "backend/app/auth.py" in question


def test_extract_frames() -> None:
    frames = inv_service.extract_frames(
        "Error at app/auth.py:6", 'File "app/main.py", line 12\nat x (web/app.js:42:7)'
    )
    paths = {(f["path"], f["line"]) for f in frames}
    assert ("app/auth.py", 6) in paths
    assert ("app/main.py", 12) in paths
    assert ("web/app.js", 42) in paths


def test_map_verdict_unresolved_without_citations() -> None:
    verdict, _ = inv_service.map_verdict([], [{"path": "a.py", "line": 1}])
    assert verdict == "unresolved"


def test_map_verdict_likely_with_citation_but_no_frame() -> None:
    citations = [
        {"file_path": "app/auth.py", "start_line": 3, "end_line": 6},
    ]
    verdict, _ = inv_service.map_verdict(citations, [])
    assert verdict == "likely"


def test_map_verdict_likely_never_confirmed_without_frame_overlap() -> None:
    citations = [
        {"file_path": "app/auth.py", "start_line": 3, "end_line": 6},
        {"file_path": "app/main.py", "start_line": 1, "end_line": 4},
    ]
    verdict, _ = inv_service.map_verdict(citations, [{"path": "other.py", "line": 99}])
    assert verdict == "likely"


def test_map_verdict_confirmed_on_frame_overlap_plus_support() -> None:
    citations = [
        {"file_path": "app/auth.py", "start_line": 3, "end_line": 6},
        {"file_path": "app/main.py", "start_line": 1, "end_line": 4},
    ]
    verdict, confidence = inv_service.map_verdict(
        citations, [{"path": "app/auth.py", "line": 5}]
    )
    assert verdict == "confirmed"
    assert confidence == "high"


# ---- service with the real bounded agent loop (canned LLM) ---------------------


def test_service_investigation_likely(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async def _go() -> None:
        root = tmp_path / "dbg"
        root.mkdir()
        _write_debug_repo(root)
        async with session_factory() as s:
            repo = await _make_repo(s, "owner-A", "dbg-repo", root)
            snap = await _snapshot(s, repo.id)
            deps = _deps_for(
                root, str(repo.id), "The 401 comes from `app/auth.py:3-6`."
            )
            row = await inv_service.run_investigation(
                s,
                "owner-A",
                repo.id,
                InvestigationCreate(error_text="401 on login"),
                deps=deps,
            )
            assert row.status == "completed"
            assert row.verdict == "likely"
            assert row.snapshot_id == snap.id
            assert row.stop_reason
            assert row.tool_calls >= 1
            actions = (
                await s.execute(
                    select(InvestigationAction).where(
                        InvestigationAction.investigation_id == row.id
                    )
                )
            ).scalars()
            tools = [a.tool_name for a in actions]
            assert "search_code" in tools

    asyncio.run(_go())


def test_service_investigation_unresolved_without_evidence(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async def _go() -> None:
        root = tmp_path / "dbg2"
        root.mkdir()
        _write_debug_repo(root)
        async with session_factory() as s:
            repo = await _make_repo(s, "owner-A", "dbg-repo-2", root)
            await _snapshot(s, repo.id)
            deps = _deps_for(root, str(repo.id), "Something somewhere is broken.")
            row = await inv_service.run_investigation(
                s,
                "owner-A",
                repo.id,
                InvestigationCreate(error_text="mystery failure"),
                deps=deps,
            )
            assert row.status == "completed"
            assert row.verdict == "unresolved"
            assert any("No validated" in limit for limit in (row.limitations or []))

    asyncio.run(_go())


# ---- API -----------------------------------------------------------------------


def _register(client: TestClient, tmp_path: Path, name: str) -> dict:
    src = tmp_path / name
    src.mkdir(exist_ok=True)
    _write_debug_repo(src)
    use_owner("owner-A")
    r = client.post(
        "/api/v1/repositories",
        json={"name": name, "source_type": "local", "local_path": str(src)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _index(client: TestClient, repo_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.embeddings.groq as groq_mod
    from app.services.qdrant_service import QdrantService

    class P:
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 1024 for _ in texts]

        async def embed_query(self, text: str) -> list[float]:
            return [0.1] * 1024

    class Q:
        async def ensure_collection(self, vector_size: int) -> None:
            return None

        async def upsert_chunks(
            self, chunks: list[object], vectors: list[list[float]]
        ) -> int:
            return len(chunks)

        async def list_point_ids(self, repository_id: str) -> set[str]:
            return set()

        async def delete_point_ids(self, point_ids: set[str] | list[str]) -> None:
            return None

    monkeypatch.setattr(groq_mod, "get_embedding_provider", lambda: P())
    monkeypatch.setattr(QdrantService, "from_settings", classmethod(lambda cls: Q()))
    r = client.post(f"/api/v1/repositories/{repo_id}/index")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "indexed"


def _mock_run_graph(monkeypatch: pytest.MonkeyPatch, repo_id: str) -> None:
    import app.investigations.service as svc

    async def fake_run_graph(repository, question, session_id=None, deps=None):
        final = {
            "answer": "The 401 comes from `app/auth.py:3-6`.",
            "citations": [
                {
                    "repository_id": repo_id,
                    "file_path": "app/auth.py",
                    "start_line": 3,
                    "end_line": 6,
                    "source_type": "search",
                    "reason": "match",
                }
            ],
            "steps_taken": ["classified", "planned", "answered"],
            "warnings": [],
            "tool_calls": [
                {
                    "tool_name": "search_code",
                    "arguments": {"query": "verify_token"},
                    "ok": True,
                    "result_count": 1,
                    "warning": "",
                    "duration_ms": 1.0,
                }
            ],
            "tool_call_count": 1,
            "stop_reason": "answer_sufficient",
            "evidence_meta": {"evidence_truncated": False},
        }
        return final, "sess-1", 3, 12.5

    monkeypatch.setattr(svc, "_run_graph", fake_run_graph)


def test_investigation_api_flow(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "dbg-api")
    _index(client, created["id"], monkeypatch)
    _mock_run_graph(monkeypatch, created["id"])
    use_owner("owner-A")
    created_run = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "401 on login", "affected_route": "/api/login"},
    )
    assert created_run.status_code == 200, created_run.text
    body = created_run.json()
    assert body["status"] == "completed"
    assert body["verdict"] == "likely"
    assert body["snapshot_id"]
    assert body["citations"]
    assert body["actions"]
    assert body["stop_reason"] == "answer_sufficient"
    fetched = client.get(
        f"/api/v1/repositories/{created['id']}/investigations/{body['id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_investigation_api_other_owner_is_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "dbg-iso")
    _index(client, created["id"], monkeypatch)
    _mock_run_graph(monkeypatch, created["id"])
    use_owner("owner-A")
    run_id = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "boom"},
    ).json()["id"]
    use_owner("owner-B")
    assert (
        client.get(
            f"/api/v1/repositories/{created['id']}/investigations/{run_id}"
        ).status_code
        == 404
    )


def test_investigation_unknown_run_is_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import uuid4

    created = _register(client, tmp_path, "dbg-404")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    assert (
        client.get(
            f"/api/v1/repositories/{created['id']}/investigations/{uuid4()}"
        ).status_code
        == 404
    )


def test_investigation_disabled_flag(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "dbg-flag")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    monkeypatch.setattr(settings, "DEBUG_INVESTIGATOR", False)
    assert (
        client.post(
            f"/api/v1/repositories/{created['id']}/investigations",
            json={"error_text": "boom"},
        ).status_code
        == 403
    )


def test_investigation_no_snapshot_is_409(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "dbg-nosnap")
    use_owner("owner-A")
    r = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "boom"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVESTIGATION_NO_SNAPSHOT"


def test_failed_run_preserves_previous(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.investigations.service as svc

    created = _register(client, tmp_path, "dbg-fail")
    _index(client, created["id"], monkeypatch)
    _mock_run_graph(monkeypatch, created["id"])
    use_owner("owner-A")
    first_id = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "boom"},
    ).json()["id"]

    async def _boom(repository, question, session_id=None, deps=None):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(svc, "_run_graph", _boom)
    failed = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "boom"},
    )
    assert failed.status_code == 502
    fetched = client.get(
        f"/api/v1/repositories/{created['id']}/investigations/{first_id}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"


def test_snapshot_isolation_across_reindex(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "dbg-stale")
    _index(client, created["id"], monkeypatch)
    _mock_run_graph(monkeypatch, created["id"])
    use_owner("owner-A")
    first = client.post(
        f"/api/v1/repositories/{created['id']}/investigations",
        json={"error_text": "boom"},
    ).json()
    old_snapshot = first["snapshot_id"]
    _index(client, created["id"], monkeypatch)
    pinned = client.get(
        f"/api/v1/repositories/{created['id']}/investigations/{first['id']}"
    )
    assert pinned.status_code == 200
    assert pinned.json()["snapshot_id"] == old_snapshot
    assert pinned.json()["snapshot_active"] is False


# ---- architecture map ------------------------------------------------------------


def test_architecture_map_needs_overview(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "archmap-empty")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    r = client.get(f"/api/v1/repositories/{created['id']}/architecture-map")
    assert r.status_code == 404


def test_architecture_map_from_overview(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.overview.service as ov_svc

    created = _register(client, tmp_path, "archmap-full")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")

    real_generate = ov_svc.generate_overview

    async def _fake_generate(session, owner_id, repository_id, snapshot_id=None):
        return await real_generate(
            session, owner_id, repository_id, snapshot_id, llm_model=_overview_json()
        )

    monkeypatch.setattr(ov_svc, "generate_overview", _fake_generate)
    gen = client.post(
        f"/api/v1/repositories/{created['id']}/overview:generate", json={}
    )
    assert gen.status_code == 200, gen.text
    am = client.get(f"/api/v1/repositories/{created['id']}/architecture-map")
    assert am.status_code == 200, am.text
    body = am.json()
    assert body["snapshot_id"] == gen.json()["snapshot_id"]
    assert {c["id"] for c in body["components"]} >= {"backend", "frontend"}
    assert body["data_flows"]
    assert isinstance(body["entry_points"], list)


def _overview_json() -> str:
    import json as _json

    return _json.dumps(
        {
            "summary": "Debug fixture app.",
            "architecture_style": "layered",
            "entry_points": [
                {
                    "name": "login",
                    "type": "function",
                    "path": "app/main.py",
                    "start_line": 1,
                    "end_line": 5,
                    "description": "Entry.",
                    "confidence": "candidate",
                    "evidence_ids": [],
                }
            ],
            "components": [
                {
                    "id": "backend",
                    "name": "backend",
                    "type": "backend",
                    "description": "API.",
                    "paths": ["app/main.py"],
                    "responsibilities": [],
                    "dependencies": [],
                    "evidence_ids": [],
                },
                {
                    "id": "frontend",
                    "name": "frontend",
                    "type": "frontend",
                    "description": "UI.",
                    "paths": ["app/auth.py"],
                    "responsibilities": [],
                    "dependencies": [],
                    "evidence_ids": [],
                },
            ],
            "data_flows": [
                {
                    "source": "frontend",
                    "target": "backend",
                    "description": "Calls.",
                    "evidence_ids": [],
                }
            ],
            "boundaries": [],
            "key_dependencies": [],
            "configuration_areas": [],
            "uncertainties": [],
        }
    )
