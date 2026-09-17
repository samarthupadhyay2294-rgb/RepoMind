"""Deterministic recursive file discovery under a confined repository root."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from pathspec import GitIgnoreSpec

from app.config import settings
from app.ingestion import filters
from app.ingestion.language import detect_language
from app.ingestion.paths import is_within

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredFile:
    path: Path  # Absolute, resolved, inside root.
    rel: str  # POSIX path relative to root.
    language: str
    size: int


@dataclass
class DiscoveryResult:
    files: list[DiscoveredFile] = field(default_factory=list)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)
    # (rel path, category, reason)

    def skip(self, rel: str, category: str, reason: str) -> None:
        self.skipped.append((rel, category, reason))


def load_gitignore(root: Path) -> GitIgnoreSpec | None:
    ignore_file = root / ".gitignore"
    try:
        lines = ignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return GitIgnoreSpec.from_lines(lines)


def _ignored(spec: GitIgnoreSpec | None, rel: str, is_dir: bool) -> bool:
    if spec is None:
        return False
    # Directory patterns ("build/") only match when tested as directories.
    return bool(spec.match_file(rel + "/" if is_dir else rel))


def discover_files(
    root: Path,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> DiscoveryResult:
    """Walk root deterministically; security filters always apply."""
    limit_files = settings.MAX_FILES_PER_REPOSITORY if max_files is None else max_files
    limit_bytes = settings.MAX_FILE_SIZE_BYTES if max_bytes is None else max_bytes
    spec = load_gitignore(root)
    result = DiscoveryResult()

    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        here = Path(current).relative_to(root).as_posix()
        # Prune ignored directories before descending.
        kept = []
        for dirname in dirnames:
            if dirname in filters.DEFAULT_IGNORED_DIRS:
                continue
            rel_dir = dirname if here == "." else f"{here}/{dirname}"
            if _ignored(spec, rel_dir, is_dir=True):
                result.skip(rel_dir + "/", "ignored", "Matched .gitignore.")
                continue
            kept.append(dirname)
        dirnames[:] = kept
        for name in sorted(filenames):
            if len(result.files) >= limit_files:
                result.skip(
                    os.path.relpath(os.path.join(current, name), root),
                    "file_limit",
                    f"Repository exceeds {limit_files} files.",
                )
                logger.warning(
                    "ingestion file_limit reached files=%d", len(result.files)
                )
                return result
            candidate = Path(current) / name
            rel = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                # Never follow a link that resolves outside the workspace.
                if not is_within(root, candidate):
                    result.skip(rel, "symlink_escape", "Symlink leaves the workspace.")
                    continue
                candidate = candidate.resolve()
                if not candidate.is_file():
                    result.skip(rel, "unsupported", "Symlink target is not a file.")
                    continue
            if not candidate.is_file():
                continue
            if _ignored(spec, rel, is_dir=False):
                result.skip(rel, "ignored", "Matched .gitignore.")
                continue
            if filters.is_secret_file(name):
                # Log the name only — never contents.
                logger.warning("secret_file_skipped file=%s", rel)
                result.skip(rel, "secret", "Potential secret file.")
                continue
            size = filters.file_size(candidate)
            if size is None:
                result.skip(rel, "unreadable", "File cannot be read.")
                continue
            if size > limit_bytes:
                logger.warning("file_too_large file=%s size=%d", rel, size)
                result.skip(rel, "too_large", f"Exceeds {limit_bytes} bytes.")
                continue
            if filters.looks_binary(candidate):
                result.skip(rel, "binary", "Binary or unreadable content.")
                continue
            language = detect_language(name)
            if language is None:
                result.skip(rel, "unsupported", "Unknown file type.")
                continue
            result.files.append(
                DiscoveredFile(path=candidate, rel=rel, language=language, size=size)
            )
    return result
