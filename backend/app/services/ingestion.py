"""Ingestion orchestration: repository → discovery → parse → chunk → result.

Read-only: never executes, modifies, or moves repository files. Reusable by
the future indexing worker; no API, DB, or queue coupling here.
"""

import logging
from pathlib import Path
from uuid import UUID

from app.config import settings
from app.db.models.repository import Repository
from app.exceptions import IngestionError
from app.ingestion import chunking, discovery, hashing
from app.ingestion.models import IngestionResult, SkippedFile
from app.ingestion.parsers import parse_file
from app.ingestion.paths import resolve_root

logger = logging.getLogger(__name__)


def workspace_for(repository_id: UUID | str) -> Path:
    """Future clone target: <storage>/<repository-id>/repo/ (no traversal)."""
    rid = str(repository_id)
    if not rid or "/" in rid or "\\" in rid or ".." in rid:
        raise IngestionError("Invalid repository identifier.")
    return Path(settings.REPOSITORY_STORAGE_PATH) / rid / "repo"


def ingest_directory(
    root: Path | str, *, repository_id: str, commit_sha: str | None = None
) -> IngestionResult:
    resolved = resolve_root(root)
    logger.info("repository_ingestion_started repository_id=%s", repository_id)
    found = discovery.discover_files(resolved)
    result = IngestionResult(repository_id=repository_id, commit_sha=commit_sha)

    for skipped_rel, category, reason in found.skipped:
        result.skipped.append(
            SkippedFile(file_path=skipped_rel, category=category, reason=reason)
        )
    for item in found.files:
        try:
            raw = item.path.read_bytes()
        except OSError:
            result.skipped.append(
                SkippedFile(
                    file_path=item.rel,
                    category="unreadable",
                    reason="File cannot be read.",
                )
            )
            continue
        file_hash = hashing.hash_bytes(raw)
        result.file_hashes[item.rel] = file_hash
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            result.skipped.append(
                SkippedFile(
                    file_path=item.rel, category="binary", reason="Not UTF-8 text."
                )
            )
            continue
        parsed = parse_file(text, item.rel, item.language)
        chunks = chunking.chunk_parsed_file(
            parsed,
            repository_id=repository_id,
            commit_sha=commit_sha,
            file_path=item.rel,
            file_hash=file_hash,
            language=item.language,
        )
        if not chunks:  # Empty file: processed, nothing to index.
            result.files_processed += 1
            continue
        result.chunks.extend(chunks)
        result.files_processed += 1

    result.files_skipped = len(result.skipped)
    result.chunks_created = len(result.chunks)
    logger.info(
        "repository_ingestion_completed repository_id=%s files=%d skipped=%d chunks=%d",
        repository_id,
        result.files_processed,
        result.files_skipped,
        result.chunks_created,
    )
    return result


def ingest_repository(repository: Repository) -> IngestionResult:
    """Acquire the workspace (cloning Git repos when needed) and ingest it."""
    from app.services.acquisition import acquire_repository

    acquired = acquire_repository(repository)
    commit_sha = acquired.commit_sha or repository.current_commit_sha
    return ingest_directory(
        acquired.root,
        repository_id=str(repository.id),
        commit_sha=commit_sha,
    )
