"""Regression tests for the GRAPH_DISABLED fix.

Local development enables the code graph by default via
``DEPENDENCY_GRAPH=true`` in ``backend/.env`` / ``backend/.env.example``,
while the flag stays environment-controlled (``app/config.py`` default is
also ``True``; production disables it by setting ``false`` explicitly).
API routes must keep reading ``settings.DEPENDENCY_GRAPH`` (no hardcoded
access) and must keep ownership + snapshot guards.
"""

from pathlib import Path

from app import config as config_module
from app.api import routes_graph


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_dependency_graph_code_default_is_true() -> None:
    field = config_module.Settings.model_fields["DEPENDENCY_GRAPH"]
    assert field.default is True


def test_local_env_enables_graph_by_default() -> None:
    root = _repo_root()
    for name in (".env", ".env.example"):
        path = root / "backend" / name
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert "DEPENDENCY_GRAPH=true" in lines, f"{name} must enable the graph"


def test_graph_guard_stays_environment_controlled() -> None:
    src = Path(routes_graph.__file__).read_text(encoding="utf-8")
    assert "if not settings.DEPENDENCY_GRAPH:" in src
    assert 'code="GRAPH_DISABLED"' in src
    # Ownership + snapshot checks must remain: every graph handler resolves
    # the snapshot through the owner-checked repository service first.
    assert src.count("_resolve_snapshot(") >= 4
    assert "await repository_service.get_repository(session, owner_id" in src
    assert "GRAPH_NO_SNAPSHOT" in src
    assert "GRAPH_SNAPSHOT_NOT_READY" in src


def test_indexing_still_builds_graph_unconditionally() -> None:
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "indexing_service.py").read_text(
        encoding="utf-8"
    )
    assert "await _build_snapshot_graph(session, repository, snapshot.id)" in src
    # Graph extraction must not be gated on the read flag: extraction runs
    # after indexing so enabling the flag + reindexing restores graph data.
    build_fn = src.split("async def _build_snapshot_graph")[1]
    assert "DEPENDENCY_GRAPH" not in build_fn
