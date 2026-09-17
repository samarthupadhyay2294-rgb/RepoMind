"""Regression tests for the OVERVIEW_DISABLED fix.

Local development enables repository overviews by default via
``ARCHITECTURE_OVERVIEW=true`` in ``backend/.env`` /
``backend/.env.example``. Production keeps an explicit opt-out by
setting the variable to ``false``.
"""

from pathlib import Path

from app import config as config_module
from app.api import routes_overview
from app.overview import service as overview_service


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_overview_code_default_is_true() -> None:
    field = config_module.Settings.model_fields["ARCHITECTURE_OVERVIEW"]
    assert field.default is True


def test_local_env_enables_overview_by_default() -> None:
    root = _repo_root()
    for name in (".env", ".env.example"):
        path = root / "backend" / name
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert "ARCHITECTURE_OVERVIEW=true" in lines, f"{name} must enable overviews"


def test_overview_guard_stays_environment_controlled() -> None:
    src = Path(overview_service.__file__).read_text(encoding="utf-8")
    assert "if not settings.ARCHITECTURE_OVERVIEW:" in src
    assert 'code="OVERVIEW_DISABLED"' in src
    routes_src = Path(routes_overview.__file__).read_text(encoding="utf-8")
    assert routes_src.count("overview_service.require_overview_enabled()") >= 3
    assert "await repository_service.get_repository(session, owner_id" in src
    assert "OVERVIEW_NO_SNAPSHOT" in src
    assert "OVERVIEW_SNAPSHOT_NOT_READY" in src
