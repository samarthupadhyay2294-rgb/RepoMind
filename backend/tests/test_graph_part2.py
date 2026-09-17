"""Part 2 tests: extraction, isolation, boundaries, API, integration fixture."""

import asyncio
import uuid
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models.graph import CodeRelationship, CodeSymbol
from app.db.models.repository import Repository, SourceType
from app.graph import extractor as gx
from app.graph import service as gs
from tests.conftest import use_owner


@pytest.fixture(autouse=True)
def _graph_flags(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEPENDENCY_GRAPH", True)
    monkeypatch.setattr(settings, "GRAPH_ENABLE_INFERRED_RELATIONSHIPS", False)
    monkeypatch.setattr(settings, "GRAPH_MAX_NODES", 100)
    monkeypatch.setattr(settings, "GRAPH_MAX_EDGES", 200)
    monkeypatch.setattr(settings, "GRAPH_MAX_DEPTH", 3)
    yield


def _fixture_files() -> dict[str, tuple[str, str | None]]:
    return {
        "app/main.py": (
            "from app import auth\nfrom app import service\n\n"
            "def main():\n    auth.authenticate()\n    service.run()\n",
            "python",
        ),
        "app/auth.py": (
            "from app import db\n\ndef authenticate():\n    return db.get_user()\n",
            "python",
        ),
        "app/service.py": (
            "from app import db\n\ndef run():\n    return db.get_user()\n",
            "python",
        ),
        "app/db.py": (
            "def get_user():\n    return 1\n",
            "python",
        ),
    }


# ---- unit: extraction ------------------------------------------------------


def test_extract_tier1_files_imports_contains() -> None:
    result = gx.extract_files(_fixture_files())
    by_key = {s.stable_key: s for s in result.symbols}
    assert gx.file_key("app/main.py") in by_key
    assert gx.file_key("app/auth.py") in by_key
    imports = {
        (r.source_key, r.target_key)
        for r in result.relationships
        if r.relationship_type == "imports"
    }
    assert (gx.file_key("app/main.py"), gx.file_key("app/auth.py")) in imports
    contains = [r for r in result.relationships if r.relationship_type == "contains"]
    assert contains, "contains edges must exist"
    for r in result.relationships:
        assert r.path and r.start_line >= 1 and r.end_line >= r.start_line


def test_extract_tier2_calls_resolved_not_fabricated() -> None:
    result = gx.extract_files(_fixture_files())
    calls = [r for r in result.relationships if r.relationship_type == "calls"]
    assert calls, "expected resolved calls"
    for c in calls:
        assert c.provenance == "resolver"
        assert c.confidence > 0
    # unknown callee must not fabricate an edge
    result2 = gx.extract_files(
        {"x.py": ("def a():\n    nope_not_defined()\n", "python")}
    )
    assert [r for r in result2.relationships if r.relationship_type == "calls"] == []


def test_extract_inheritance_and_unsupported_language() -> None:
    files = {
        "a.py": ("class Base:\n    pass\nclass Child(Base):\n    pass\n", "python"),
        "notes.txt": ("hello", "text"),
        "bad.py": ("def broken(:\n", "python"),
    }
    result = gx.extract_files(files)
    assert any(r.relationship_type == "inherits" for r in result.relationships)
    assert any(s.path == "notes.txt" for s in result.symbols)
    assert any(s.path == "bad.py" for s in result.symbols)


def test_extract_typescript_imports_exports() -> None:
    files = {
        "src/a.ts": ('import { b } from "./b";\nexport class Foo {}\n', "typescript"),
        "src/b.ts": ("export function b() {}\n", "typescript"),
    }
    result = gx.extract_files(files)
    assert any(r.relationship_type == "imports" for r in result.relationships)
    assert any(
        r.relationship_type in ("contains", "exports") for r in result.relationships
    )


def test_canonical_keys_distinct_per_file() -> None:
    files = {
        "a.py": ("def handle():\n    return 1\n", "python"),
        "b.py": ("def handle():\n    return 2\n", "python"),
    }
    result = gx.extract_files(files)
    keys = [s.stable_key for s in result.symbols if s.name == "handle"]
    assert len(keys) == 2 and len(set(keys)) == 2


# ---- helpers ---------------------------------------------------------------


async def _make_repo(
    session: AsyncSession, owner: str, name: str, root: Path
) -> Repository:
    from app.services import repositories as repo_service
    from app.schemas.repository import RepositoryCreate

    return await repo_service.create_repository(
        session,
        owner,
        RepositoryCreate(name=name, source_type=SourceType.LOCAL, local_path=str(root)),
    )


async def _snapshot(session: AsyncSession, repo_id: UUID, rev: str = "r1"):
    from app.services import snapshots as snap_service

    begun = await snap_service.begin_snapshot(session, repo_id, revision=rev)
    return await snap_service.activate_snapshot(session, begun.id)


def _write_fixture_repo(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "from app import auth\ndef main():\n    auth.authenticate()\n", encoding="utf-8"
    )
    (root / "app" / "auth.py").write_text(
        "from app import db\ndef authenticate():\n    return db.get_user()\n",
        encoding="utf-8",
    )
    (root / "app" / "service.py").write_text(
        "from app import db\ndef run():\n    return db.get_user()\n", encoding="utf-8"
    )
    (root / "app" / "db.py").write_text(
        "def get_user():\n    return 1\n", encoding="utf-8"
    )


# ---- isolation ---------------------------------------------------------------


def test_repository_and_snapshot_isolation(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async def _go() -> None:
        r1 = tmp_path / "r1"
        r1.mkdir()
        r2 = tmp_path / "r2"
        r2.mkdir()
        _write_fixture_repo(r1)
        _write_fixture_repo(r2)
        async with session_factory() as s:
            repo_a = await _make_repo(s, "owner-A", "repo-a", r1)
            repo_b = await _make_repo(s, "owner-B", "repo-b", r2)
            snap_a1 = await _snapshot(s, repo_a.id, "a1")
            snap_a2 = await _snapshot(s, repo_a.id, "a2")
            snap_b = await _snapshot(s, repo_b.id, "b1")
            from app.tools.context import context_for_repository
            from app.ingestion import discovery

            for repo, snap in ((repo_a, snap_a1), (repo_b, snap_b)):
                ctx = context_for_repository(repo)
                files = {}
                for item in discovery.discover_files(ctx.root).files:
                    try:
                        files[item.rel] = (
                            item.path.read_text(encoding="utf-8"),
                            item.language,
                        )
                    except (OSError, UnicodeDecodeError):
                        continue
                res = gx.extract_files(files)
                await gs.persist_extraction(
                    s, repository_id=repo.id, snapshot_id=snap.id, result=res
                )
            await s.commit()
            # cross-repo: node from A invisible in B
            node_a = (
                (
                    await s.execute(
                        select(CodeSymbol).where(
                            CodeSymbol.repository_id == repo_a.id,
                            CodeSymbol.snapshot_id == snap_a1.id,
                            CodeSymbol.symbol_type == "file",
                        )
                    )
                )
                .scalars()
                .first()
            )
            assert node_a is not None
            assert await gs.get_symbol(s, repo_b.id, snap_b.id, node_a.id) is None
            # cross-snapshot: node from snap_a1 invisible in snap_a2
            assert await gs.get_symbol(s, repo_a.id, snap_a2.id, node_a.id) is None
            # edge isolation
            edge_a = (
                (
                    await s.execute(
                        select(CodeRelationship).where(
                            CodeRelationship.repository_id == repo_a.id,
                            CodeRelationship.snapshot_id == snap_a1.id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if edge_a is not None:
                assert await gs.get_edge(s, repo_b.id, snap_b.id, edge_a.id) is None
                assert await gs.get_edge(s, repo_a.id, snap_a2.id, edge_a.id) is None

    asyncio.run(_go())


# ---- boundaries --------------------------------------------------------------


def test_traversal_bounds(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async def _go() -> None:
        root = tmp_path / "bound"
        root.mkdir()
        _write_fixture_repo(root)
        async with session_factory() as s:
            repo = await _make_repo(s, "o", "bound-repo", root)
            snap = await _snapshot(s, repo.id)
            from app.tools.context import context_for_repository
            from app.ingestion import discovery

            ctx = context_for_repository(repo)
            files = {
                i.rel: (i.path.read_text(encoding="utf-8"), i.language)
                for i in discovery.discover_files(ctx.root).files
            }
            await gs.persist_extraction(
                s,
                repository_id=repo.id,
                snapshot_id=snap.id,
                result=gx.extract_files(files),
            )
            await s.commit()
            seed = (
                (
                    await s.execute(
                        select(CodeSymbol).where(
                            CodeSymbol.repository_id == repo.id,
                            CodeSymbol.snapshot_id == snap.id,
                            CodeSymbol.symbol_type == "file",
                        )
                    )
                )
                .scalars()
                .first()
            )
            assert seed is not None
            # depth beyond maximum is clamped server-side; huge limits truncate
            nodes, edges, truncated, reason = await gs.neighborhood(
                s,
                repository_id=repo.id,
                snapshot_id=snap.id,
                root_id=seed.id,
                depth=50,
                direction="both",
                relationship_types=None,
                node_types=None,
                max_nodes=2,
                max_edges=1,
            )
            assert len(nodes) <= 2 and len(edges) <= 1
            assert truncated is True and reason is not None

    asyncio.run(_go())


# ---- API ---------------------------------------------------------------------


def _register(client: TestClient, tmp_path: Path, name: str) -> dict:
    src = tmp_path / name
    src.mkdir(exist_ok=True)
    _write_fixture_repo(src)
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


def test_graph_api_endpoints(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "graph-api")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    g = client.get(f"/api/v1/repositories/{created['id']}/graph")
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["snapshot_id"] and body["nodes"] and body["limits"]
    assert body["truncated"] in (True, False)
    node_id = body["nodes"][0]["id"]
    n = client.get(f"/api/v1/repositories/{created['id']}/graph/nodes/{node_id}")
    assert n.status_code == 200, n.text
    assert n.json()["node"]["id"] == node_id
    assert n.json()["evidence"]
    if body["edges"]:
        edge_id = body["edges"][0]["id"]
        e = client.get(f"/api/v1/repositories/{created['id']}/graph/edges/{edge_id}")
        assert e.status_code == 200, e.text
        assert e.json()["edge"]["id"] == edge_id
        ex = client.post(
            f"/api/v1/repositories/{created['id']}/graph/explain",
            json={"edge_id": edge_id, "question": "Why does this depend on this?"},
        )
        assert ex.status_code == 200, ex.text
        assert ex.json()["explanation"] and ex.json()["evidence"]
    # unknown node → 404, not leakage
    bad = client.get(f"/api/v1/repositories/{created['id']}/graph/nodes/{uuid.uuid4()}")
    assert bad.status_code == 404


def test_graph_api_other_owner_is_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "graph-iso")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-B")
    r = client.get(f"/api/v1/repositories/{created['id']}/graph")
    assert r.status_code == 404


def test_graph_disabled_flag(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "graph-flag")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    monkeypatch.setattr(settings, "DEPENDENCY_GRAPH", False)
    r = client.get(f"/api/v1/repositories/{created['id']}/graph")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "GRAPH_DISABLED"


# ---- integration fixture -------------------------------------------------------


def test_integration_fixture_relationships(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _register(client, tmp_path, "graph-fixture")
    _index(client, created["id"], monkeypatch)
    use_owner("owner-A")
    g = client.get(f"/api/v1/repositories/{created['id']}/graph?limit=300").json()
    by_path = {n["path"]: n for n in g["nodes"] if n["type"] == "file"}
    assert "app/main.py" in by_path and "app/auth.py" in by_path
    # Expand from main.py: bounded neighborhood must carry imports + calls.
    main_id = by_path["app/main.py"]["id"]
    nb = client.get(
        f"/api/v1/repositories/{created['id']}/graph",
        params={"node_id": main_id, "depth": 2, "limit": 300},
    ).json()
    id_of = {n["id"]: n for n in nb["nodes"]}
    edge_set = {
        (id_of[e["source"]]["path"], e["relationship_type"], id_of[e["target"]]["path"])
        for e in nb["edges"]
        if e["source"] in id_of and e["target"] in id_of
    }
    assert ("app/main.py", "imports", "app/auth.py") in edge_set
    # symbol-level: authenticate defined in auth.py (seed query lists symbols)
    auth_fns = [n for n in g["nodes"] + nb["nodes"] if n["name"] == "authenticate"]
    assert auth_fns and auth_fns[0]["path"] == "app/auth.py"
    # every persisted edge has evidence + provenance
    for e in nb["edges"]:
        assert e["provenance"] in ("parser", "resolver", "inferred")
        assert e["evidence"]["path"]
        assert e["confidence"] > 0
