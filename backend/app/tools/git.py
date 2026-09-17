"""git_log / git_blame: read-only history inspection (Part 6).

DEVIATION REPORT (vs prompt §22-23): GitPython is not an installed
dependency (see requirements.txt) and rule.md's ladder says stdlib first,
so these tools use stdlib ``subprocess`` with fixed argv arrays —
``shell=False`` always, ``--`` separating paths, ints coerced/bounded,
paths confined via Part 4 ``safe_join``. No user string ever becomes a
flag, revision, or shell fragment. Only ``log``/``blame``/``rev-parse``
are invocable; there is no generic git runner.

Purpose: who changed what, when (commits touching a path; per-line
authorship for a bounded range).
Inputs: repository_id (via context), path?, max_entries? / start_line/end_line.
Output: GitLogResult / GitBlameResult.
Limits: MAX_GIT_LOG_ENTRIES, MAX_BLAME_LINES, subprocess timeout 30s.
Failures: not a git repo (TOOL_GIT_UNAVAILABLE), bad range, git errors.
"""

import logging
import subprocess
import time

from app.config import settings
from app.exceptions import ToolError
from app.tools._common import rel_posix, resolve_tool_path
from app.tools.context import ToolContext
from app.tools.models import BlameLine, GitBlameResult, GitCommit, GitLogResult

logger = logging.getLogger(__name__)

_GIT_TIMEOUT_SECONDS = 30
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"


def _ensure_git_repo(ctx: ToolContext) -> None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ctx.root), "rev-parse", "--git-dir"],
            shell=False,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolError(
            "Git is not available for this repository.",
            code="TOOL_GIT_UNAVAILABLE",
        ) from exc
    if proc.returncode != 0:
        raise ToolError(
            "Git repository unavailable for this workspace.",
            code="TOOL_GIT_UNAVAILABLE",
        )


def _run_git(ctx: ToolContext, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ctx.root), *args],
            shell=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Git operation timed out.", code="TOOL_GIT_TIMEOUT") from exc
    except OSError as exc:
        raise ToolError(
            "Git is not available for this repository.",
            code="TOOL_GIT_UNAVAILABLE",
        ) from exc
    if proc.returncode != 0:
        # stderr may echo paths; keep only the category, never raw output.
        raise ToolError("Git operation failed.", code="TOOL_GIT_FAILED")
    return proc.stdout


def git_log(
    ctx: ToolContext,
    path: str | None = None,
    max_entries: int | None = None,
) -> GitLogResult:
    """List recent commits (newest first), optionally touching ``path``."""
    _ensure_git_repo(ctx)
    limit = (
        settings.MAX_GIT_LOG_ENTRIES
        if max_entries is None
        else max(1, min(max_entries, settings.MAX_GIT_LOG_ENTRIES))
    )
    started = time.monotonic()
    args = [
        "log",
        f"--format=%H{_FIELD_SEP}%an{_FIELD_SEP}%aI{_FIELD_SEP}%s{_RECORD_SEP}",
        "-n",
        str(limit),
    ]
    if path is not None:
        resolved = resolve_tool_path(ctx, path)
        args += ["--", rel_posix(ctx, resolved)]
    out = _run_git(ctx, args)
    commits: list[GitCommit] = []
    for record in out.split(_RECORD_SEP):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) != 4:
            continue
        sha, author, timestamp, message = parts
        commits.append(
            GitCommit(
                commit_sha=sha.strip()[:64],
                author=author.strip()[:200],
                timestamp=timestamp.strip()[:64],
                message=message.strip()[:1000],
            )
        )
    logger.info(
        "tool_completed tool=git_log repository_id=%s commits=%d duration_ms=%.1f",
        ctx.repository_id,
        len(commits),
        (time.monotonic() - started) * 1000,
    )
    return GitLogResult(
        repository_id=ctx.repository_id,
        commits=commits,
        truncated=len(commits) >= limit,
    )


def git_blame(
    ctx: ToolContext,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> GitBlameResult:
    """Per-line authorship for a bounded range of one tracked file."""
    _ensure_git_repo(ctx)
    resolved = resolve_tool_path(ctx, path, must_be_file=True)
    rel = rel_posix(ctx, resolved)
    first = start_line if start_line is not None else 1
    last = end_line if end_line is not None else first + settings.MAX_BLAME_LINES - 1
    if first < 1 or last < 1 or first > last:
        raise ToolError(
            f"Invalid line range {first}-{last} for {rel}.",
            code="TOOL_INVALID_RANGE",
        )
    if last - first + 1 > settings.MAX_BLAME_LINES:
        last = first + settings.MAX_BLAME_LINES - 1
    started = time.monotonic()
    out = _run_git(
        ctx, ["blame", "--line-porcelain", "-L", f"{first},{last}", "--", rel]
    )
    lines: list[BlameLine] = []
    sha, author, timestamp, summary = "", "", "", ""
    for raw in out.splitlines():
        if raw.startswith("\t"):
            if not sha:
                continue
            lines.append(
                BlameLine(
                    line=first + len(lines),
                    commit_sha=sha[:64],
                    author=author[:200],
                    timestamp=timestamp[:64],
                    summary=summary[:500],
                )
            )
            sha, author, timestamp, summary = "", "", "", ""
        elif len(raw) >= 40 and all(c in "0123456789abcdef" for c in raw[:40]):
            sha = raw[:40]
        elif raw.startswith("author ") and not raw.startswith("author-"):
            author = raw[len("author ") :]
        elif raw.startswith("author-time "):
            timestamp = raw[len("author-time ") :]
        elif raw.startswith("summary "):
            summary = raw[len("summary ") :]
    logger.info(
        "tool_completed tool=git_blame repository_id=%s lines=%d duration_ms=%.1f",
        ctx.repository_id,
        len(lines),
        (time.monotonic() - started) * 1000,
    )
    return GitBlameResult(repository_id=ctx.repository_id, file_path=rel, lines=lines)
