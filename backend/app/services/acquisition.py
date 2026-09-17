"""Git repository acquisition (Gap #1).

Shallow-clones Git repositories into the per-repository workspace so the
existing ingestion/indexing pipeline can consume them. Local repositories
keep ingesting in place — nothing new there.

Security posture (stdlib ``subprocess`` only, same pattern as Part 6 git
tools — GitPython is not a dependency):
- the Pydantic URL validator is re-checked here; never bypassed,
- fixed argv arrays, ``shell=False``, ``--`` before the URL,
- ``GIT_TERMINAL_PROMPT=0`` so a credential prompt can never hang us,
- bounded timeout (``REPOSITORY_CLONE_TIMEOUT_SECONDS``),
- post-clone size cap (``MAX_REPOSITORY_BYTES``) — git cannot enforce
  transfer size, so oversized workspaces are removed before ingestion,
- destination is always ``workspace_for(repository.id)`` — one repo can
  never land in another's workspace,
- URLs are never logged whole (host only) and never appear in errors,
- partial clones we created are removed on failure.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.db.models.repository import Repository, SourceType
from app.exceptions import IngestionError
from app.ingestion.paths import resolve_root
from app.schemas.repository import validate_source_url
from app.services.ingestion import workspace_for

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcquisitionResult:
    root: Path
    commit_sha: str | None
    fresh_clone: bool


def acquire_repository(repository: Repository) -> AcquisitionResult:
    """Prepare the on-disk workspace for a repository record."""
    if repository.source_type == SourceType.LOCAL:
        if not repository.local_path:
            raise IngestionError("Local repository has no path configured.")
        return AcquisitionResult(
            root=resolve_root(repository.local_path),
            commit_sha=repository.current_commit_sha,
            fresh_clone=False,
        )
    if not (repository.source_url or "").strip():
        raise IngestionError("Git repository has no URL configured.")
    return _acquire_git(
        str(repository.id), repository.source_url or "", repository.default_branch
    )


def _acquire_git(repository_id: str, url: str, branch: str | None) -> AcquisitionResult:
    try:
        clean_url = validate_source_url(url)
    except ValueError as exc:
        raise IngestionError(f"Unsafe repository URL: {exc}") from None
    assert clean_url is not None
    dest = workspace_for(repository_id)
    host = _safe_host(clean_url)
    if (dest / ".git").is_dir():
        logger.info(
            "repository_acquire_reuse repository_id=%s host=%s", repository_id, host
        )
        _refresh(dest, repository_id, host, branch)
        return AcquisitionResult(
            root=resolve_root(dest), commit_sha=_head_sha(dest), fresh_clone=False
        )
    if dest.exists():
        # Leftover from a failed run (never another repo's data — the path
        # is derived from this repository's UUID). Remove before cloning.
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _clone(clean_url, dest, repository_id, host, branch)
        _enforce_size(dest, repository_id)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    logger.info(
        "repository_acquire_cloned repository_id=%s host=%s", repository_id, host
    )
    return AcquisitionResult(
        root=resolve_root(dest), commit_sha=_head_sha(dest), fresh_clone=True
    )


def _clone(
    url: str, dest: Path, repository_id: str, host: str, branch: str | None
) -> None:
    argv = ["git", "clone", "--depth", "1"]
    clean_branch = (branch or "").strip()
    if clean_branch:
        argv += ["--branch", clean_branch]
    argv += ["--", url, str(dest)]
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=max(1, settings.REPOSITORY_CLONE_TIMEOUT_SECONDS),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning(
            "repository_acquire_timeout repository_id=%s host=%s", repository_id, host
        )
        raise IngestionError("Repository clone timed out.") from exc
    except OSError as exc:
        raise IngestionError("Git is not available.") from exc
    if proc.returncode != 0:
        logger.warning(
            "repository_acquire_failed repository_id=%s host=%s", repository_id, host
        )
        raise IngestionError("Repository clone failed.")


def _refresh(dest: Path, repository_id: str, host: str, branch: str | None) -> None:
    """Best-effort update of an existing shallow clone (keeps old state on failure)."""
    ref = (branch or "").strip() or "HEAD"
    try:
        subprocess.run(
            ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", ref],
            shell=False,
            capture_output=True,
            timeout=max(1, settings.REPOSITORY_CLONE_TIMEOUT_SECONDS),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"],
            shell=False,
            capture_output=True,
            timeout=60,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(
            "repository_acquire_refresh_failed repository_id=%s host=%s error=%s",
            repository_id,
            host,
            type(exc).__name__,
        )
        raise IngestionError("Repository update failed.") from None
    _enforce_size(dest, repository_id)


def _enforce_size(dest: Path, repository_id: str) -> None:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(dest, followlinks=False):
        for name in filenames:
            try:
                # lstat: a symlink counts as itself, never its target.
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                continue
            if total > max(1, settings.MAX_REPOSITORY_BYTES):
                logger.warning(
                    "repository_acquire_oversized repository_id=%s", repository_id
                )
                raise IngestionError("Repository exceeds the size limit.")
    logger.info(
        "repository_acquire_size repository_id=%s bytes=%d", repository_id, total
    )


def _head_sha(dest: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = proc.stdout.strip() if proc.returncode == 0 else ""
    return sha or None


def _safe_host(url: str) -> str:
    """Host for logs only — never the full URL (may carry a username)."""
    try:
        if "://" in url:
            return url.split("://", 1)[1].split("/", 1)[0].rsplit("@", 1)[-1]
        return url.split("@", 1)[1].split(":", 1)[0]
    except IndexError:
        return "unknown-host"
