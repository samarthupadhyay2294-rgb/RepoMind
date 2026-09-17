"""Deterministic repository fact collection (Part 3).

Everything here is observed from the workspace, manifests, parser output,
and Part 2 graph tables — no LLM involved. The LLM later synthesizes prose
from these facts; it must never invent files, dependencies, or behavior.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.graph import CodeRelationship, CodeSymbol
from app.db.models.repository import Repository
from app.ingestion import discovery
from app.tools.context import context_for_repository

logger = logging.getLogger(__name__)

_MAX_MANIFEST_BYTES = 50000
_MAX_FACT_FILES = 2000

_MANIFEST_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "poetry.lock",
    "go.mod",
    "Cargo.toml",
    "composer.json",
    "Gemfile",
}

_CONFIG_BASENAMES = {
    ".env.example",
    ".env.template",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "next.config.ts",
    "next.config.js",
    "vite.config.ts",
    "alembic.ini",
    "docker-compose.yml",
    "Dockerfile",
}

_ENTRY_CANDIDATE_NAMES = {
    "main.py",
    "__main__.py",
    "app.py",
    "manage.py",
    "cli.py",
    "server.py",
    "index.ts",
    "index.js",
    "main.ts",
    "server.ts",
}

_FASTAPI_APP_RE = re.compile(r"(\w+)\s*=\s*FastAPI\s*\(")
_ROUTE_DECORATOR_RE = re.compile(
    r"@(?:\w+\.)?(?:get|post|put|patch|delete|head|options|websocket)\s*\("
)
_APPROuter_RE = re.compile(r"APIRouter\s*\(")
_NEXT_ROUTE_RE = re.compile(
    r"(?:^|/)app/(?:.*/)?(page|route|layout)\.(tsx?|jsx?|mdx?)$"
)
_NEXT_PAGES_RE = re.compile(r"(?:^|/)pages/(?:.*/)?index\.(tsx?|jsx?)$")

_FRAMEWORK_MARKERS: tuple[tuple[str, str, str], ...] = (
    ("fastapi", "backend", "FastAPI"),
    ("flask", "backend", "Flask"),
    ("django", "backend", "Django"),
    ("next", "frontend", "Next.js"),
    ("react", "frontend", "React"),
    ("sqlalchemy", "database", "SQLAlchemy"),
    ("asyncpg", "database", "asyncpg/PostgreSQL driver"),
    ("qdrant-client", "database", "Qdrant client"),
    ("redis", "infrastructure", "Redis"),
    ("celery", "worker", "Celery"),
    ("click", "cli", "Click"),
    ("langgraph", "ai", "LangGraph"),
    ("langchain", "ai", "LangChain"),
)

_DB_HINT_RE = re.compile(
    r"(?i)(sqlalchemy|asyncpg|psycopg|alembic|create_engine|sessionmaker|Base\s*=|DeclarativeBase)"
)


def _read_bounded(path: Path, limit: int = _MAX_MANIFEST_BYTES) -> str | None:
    try:
        if path.stat().st_size > settings.MAX_FILE_SIZE_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return text[:limit]


def _parse_package_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    for key in ("scripts", "dependencies", "devDependencies"):
        val = data.get(key)
        if isinstance(val, dict):
            out[key] = {str(k): str(v)[:200] for k, v in list(val.items())[:60]}
    return out


def _parse_requirements(text: str) -> list[str]:
    names = []
    for line in text.splitlines()[:100]:
        line = line.strip()
        if not line or line.startswith(("#", "-", "!")):
            continue
        names.append(re.split(r"[<>=!~\s;\[]", line, maxsplit=1)[0].strip()[:120])
    return [n for n in names if n]


async def collect_facts(
    session: AsyncSession, repository: Repository, snapshot_id: UUID
) -> dict:
    """Collect deterministic facts scoped to one repository snapshot."""
    repo_id = repository.id
    facts: dict = {
        "repository_id": str(repo_id),
        "snapshot_id": str(snapshot_id),
        "languages": {},
        "file_counts": {"total": 0, "by_language": {}},
        "top_directories": [],
        "manifests": {},
        "python_dependencies": [],
        "js_dependencies": [],
        "scripts": {},
        "frameworks": [],
        "entry_point_candidates": [],
        "route_hints": [],
        "config_files": [],
        "db_indicators": [],
        "graph": {"symbols": 0, "relationships": 0, "by_type": {}},
        "top_importers": [],
        "diagnostics": [],
    }
    try:
        ctx = context_for_repository(repository)
    except Exception as exc:
        facts["diagnostics"].append(f"workspace_unavailable:{type(exc).__name__}")
        return facts

    found = discovery.discover_files(ctx.root)
    files = found.files[:_MAX_FACT_FILES]
    if len(found.files) > _MAX_FACT_FILES:
        facts["diagnostics"].append(f"files_truncated:{len(found.files)}")
    lang_counter: Counter[str] = Counter()
    dir_counter: Counter[str] = Counter()
    for item in files:
        lang = item.language or "unknown"
        lang_counter[lang] += 1
        parent = str(Path(item.rel).parent)
        if parent not in (".", ""):
            dir_counter[parent] += 1
    facts["languages"] = dict(lang_counter.most_common(20))
    facts["file_counts"] = {
        "total": len(found.files),
        "by_language": dict(lang_counter),
    }
    facts["top_directories"] = [
        {"path": d, "files": c} for d, c in dir_counter.most_common(20)
    ]

    by_rel = {item.rel: item for item in files}
    # manifests + config
    for rel, item in by_rel.items():
        base = Path(rel).name
        if base in _MANIFEST_FILES or base in _CONFIG_BASENAMES:
            facts["config_files"].append(rel)
        if base not in _MANIFEST_FILES:
            continue
        text = _read_bounded(item.path)
        if text is None:
            facts["diagnostics"].append(f"manifest_unreadable:{rel}")
            continue
        if base == "package.json":
            parsed = _parse_package_json(text)
            facts["manifests"][rel] = {
                k: v for k, v in parsed.items() if k in ("scripts",)
            } | {
                "dependency_names": sorted(
                    set(parsed.get("dependencies", {}))
                    | set(parsed.get("devDependencies", {}))
                )[:80]
            }
            facts["js_dependencies"] = sorted(
                set(facts["js_dependencies"])
                | set(parsed.get("dependencies", {}))
                | set(parsed.get("devDependencies", {}))
            )[:120]
            facts["scripts"] = parsed.get("scripts", {})
        elif base in ("requirements.txt", "requirements-dev.txt"):
            names = _parse_requirements(text)
            facts["manifests"][rel] = {"dependency_names": names[:80]}
            facts["python_dependencies"] = sorted(
                set(facts["python_dependencies"]) | set(names)
            )[:150]
        elif base == "pyproject.toml":
            names = sorted(
                set(
                    re.findall(
                        r'(?m)^\s*["\']?([A-Za-z0-9_.-]+)["\']?\s*(?:[<>=!~]|,|\s|$)',
                        text,
                    )
                )
            )[:80]
            facts["manifests"][rel] = {"dependency_names": names}
        else:
            facts["manifests"][rel] = {"present": True}

    # entry points: filenames + content markers (bounded reads)
    for rel, item in by_rel.items():
        base = Path(rel).name
        if base in _ENTRY_CANDIDATE_NAMES:
            facts["entry_point_candidates"].append(
                {"path": rel, "kind": "filename", "confidence": "candidate"}
            )
        if _NEXT_ROUTE_RE.search(rel) or _NEXT_PAGES_RE.search(rel):
            facts["entry_point_candidates"].append(
                {"path": rel, "kind": "frontend-route", "confidence": "candidate"}
            )
    # content markers on python/js files only, bounded count
    checked = 0
    for rel, item in by_rel.items():
        if item.language not in ("python", "javascript", "typescript"):
            continue
        if checked >= 300:
            facts["diagnostics"].append("marker_scan_truncated:300")
            break
        checked += 1
        text = _read_bounded(item.path, 60000)
        if text is None:
            continue
        if item.language == "python":
            m = _FASTAPI_APP_RE.search(text)
            if m:
                facts["entry_point_candidates"].append(
                    {
                        "path": rel,
                        "kind": "fastapi-app",
                        "symbol": m.group(1)[:80],
                        "confidence": "candidate",
                    }
                )
            if _APPROuter_RE.search(text):
                facts["route_hints"].append({"path": rel, "kind": "api-router"})
            if _ROUTE_DECORATOR_RE.search(text):
                facts["route_hints"].append({"path": rel, "kind": "route-decorator"})
            if "__main__" in text or "argparse" in text or "click.command" in text:
                if not any(e["path"] == rel for e in facts["entry_point_candidates"]):
                    facts["entry_point_candidates"].append(
                        {"path": rel, "kind": "cli", "confidence": "candidate"}
                    )
            if _DB_HINT_RE.search(text):
                facts["db_indicators"].append(rel)
        if "createClient" in text and "qdrant" in text.lower():
            facts["db_indicators"].append(rel)
    # dedupe preserving order
    seen_ep = set()
    deduped = []
    for e in facts["entry_point_candidates"]:
        if e["path"] not in seen_ep:
            seen_ep.add(e["path"])
            deduped.append(e)
    facts["entry_point_candidates"] = deduped[:30]
    facts["route_hints"] = facts["route_hints"][:40]
    facts["db_indicators"] = sorted(set(facts["db_indicators"]))[:30]
    facts["config_files"] = sorted(set(facts["config_files"]))[:40]

    # framework markers from dependency names
    dep_names = {d.lower() for d in facts["python_dependencies"]} | {
        d.lower() for d in facts["js_dependencies"]
    }
    for marker, layer, label in _FRAMEWORK_MARKERS:
        if marker in dep_names:
            facts["frameworks"].append({"name": label, "layer": layer})

    # graph reuse (Part 2 tables, strictly scoped)
    n_symbols = (
        await session.execute(
            select(func.count())
            .select_from(CodeSymbol)
            .where(
                CodeSymbol.repository_id == repo_id,
                CodeSymbol.snapshot_id == snapshot_id,
            )
        )
    ).scalar_one()
    n_rels = (
        await session.execute(
            select(func.count())
            .select_from(CodeRelationship)
            .where(
                CodeRelationship.repository_id == repo_id,
                CodeRelationship.snapshot_id == snapshot_id,
            )
        )
    ).scalar_one()
    by_type = (
        await session.execute(
            select(CodeSymbol.symbol_type, func.count())
            .where(
                CodeSymbol.repository_id == repo_id,
                CodeSymbol.snapshot_id == snapshot_id,
            )
            .group_by(CodeSymbol.symbol_type)
        )
    ).all()
    facts["graph"] = {
        "symbols": int(n_symbols),
        "relationships": int(n_rels),
        "by_type": {t: int(c) for t, c in by_type},
    }
    top_imports = (
        await session.execute(
            select(CodeRelationship.path, func.count())
            .where(
                CodeRelationship.repository_id == repo_id,
                CodeRelationship.snapshot_id == snapshot_id,
                CodeRelationship.relationship_type == "imports",
            )
            .group_by(CodeRelationship.path)
            .order_by(func.count().desc())
            .limit(15)
        )
    ).all()
    facts["top_importers"] = [{"path": p, "imports": int(c)} for p, c in top_imports]
    logger.info(
        "overview_facts_collected repository_id=%s snapshot_id=%s files=%d symbols=%d",
        repo_id,
        snapshot_id,
        len(found.files),
        n_symbols,
    )
    return facts
