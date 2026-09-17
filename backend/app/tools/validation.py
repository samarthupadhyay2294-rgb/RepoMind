"""run_validation: bounded, allowlisted repository checks (Part 6).

There is deliberately NO generic command/shell tool. The caller picks a
``validation_id`` from the registry below — never argv, never shell text.
Unknown IDs (including ``"pytest; rm -rf /"``-style injections) are
rejected by exact allowlist membership before anything executes.

Registry (fixed argv, ``shell=False``, cwd = repository workspace):
  pytest     → [sys.executable, "-m", "pytest", "-q"]
  ruff_check → [sys.executable, "-m", "ruff", "check", "."]
  mypy       → [sys.executable, "-m", "mypy", "."]
Only IDs also listed in ENABLED_VALIDATIONS run; no installs, no scripts.

Purpose: let a future agent verify a repo state without terminal access.
Inputs: repository_id (via context), validation_id.
Output: ValidationResult (exit code, capped output, timeout/truncation flags).
Limits: VALIDATION_TIMEOUT_SECONDS, MAX_VALIDATION_OUTPUT_BYTES,
        max 2 concurrent validations process-wide.
Failures: unknown/disabled validation, timeout, runner errors.
"""

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from app.config import settings
from app.exceptions import ToolError
from app.tools.context import ToolContext
from app.tools.models import ValidationResult

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_VALIDATIONS = 2
_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT_VALIDATIONS)


@dataclass(frozen=True)
class ValidationSpec:
    validation_id: str
    argv: tuple[str, ...]
    description: str


VALIDATIONS: dict[str, ValidationSpec] = {
    "pytest": ValidationSpec(
        "pytest",
        (sys.executable, "-m", "pytest", "-q"),
        "Run the repository pytest suite quietly.",
    ),
    "ruff_check": ValidationSpec(
        "ruff_check",
        (sys.executable, "-m", "ruff", "check", "."),
        "Run ruff lint checks.",
    ),
    "mypy": ValidationSpec(
        "mypy",
        (sys.executable, "-m", "mypy", "."),
        "Run mypy type checks.",
    ),
}


def _resolve_spec(validation_id: str) -> ValidationSpec:
    cleaned = validation_id.strip()
    spec = VALIDATIONS.get(cleaned)
    if spec is None:
        logger.warning("tool_rejected tool=run_validation reason=unknown_validation")
        raise ToolError(
            f"Unknown validation: {cleaned[:100]}.",
            code="TOOL_VALIDATION_REJECTED",
        )
    enabled = {v.strip() for v in settings.ENABLED_VALIDATIONS.split(",") if v.strip()}
    if cleaned not in enabled:
        logger.warning("tool_rejected tool=run_validation reason=disabled")
        raise ToolError(
            f"Validation is disabled: {cleaned}.",
            code="TOOL_VALIDATION_DISABLED",
        )
    return spec


def run_validation(ctx: ToolContext, validation_id: str) -> ValidationResult:
    """Execute one allowlisted validation inside the repository workspace."""
    spec = _resolve_spec(validation_id)
    if not _semaphore.acquire(blocking=False):
        raise ToolError("Too many concurrent validations.", code="TOOL_VALIDATION_BUSY")
    try:
        return _execute(ctx, spec)
    finally:
        _semaphore.release()


def _execute(ctx: ToolContext, spec: ValidationSpec) -> ValidationResult:
    timeout = max(1, settings.VALIDATION_TIMEOUT_SECONDS)
    cap = max(1024, settings.MAX_VALIDATION_OUTPUT_BYTES)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(spec.argv),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ctx.root),
        )
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if exc.stdout:
            partial += exc.stdout if isinstance(exc.stdout, str) else ""
        logger.warning(
            "tool_timeout tool=run_validation repository_id=%s validation=%s",
            ctx.repository_id,
            spec.validation_id,
        )
        output = partial[-cap:] if len(partial) > cap else partial
        return ValidationResult(
            repository_id=ctx.repository_id,
            validation_id=spec.validation_id,
            exit_code=-1,
            timed_out=True,
            truncated=len(partial) > cap,
            output=output,
        )
    except OSError as exc:
        raise ToolError(
            "Validation runner failed.", code="TOOL_VALIDATION_FAILED"
        ) from exc
    combined = (proc.stdout or "") + (proc.stderr or "")
    truncated = len(combined) > cap
    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info(
        "tool_completed tool=run_validation repository_id=%s validation=%s exit=%d output_bytes=%d duration_ms=%.1f",
        ctx.repository_id,
        spec.validation_id,
        proc.returncode,
        min(len(combined), cap),
        elapsed_ms,
    )
    return ValidationResult(
        repository_id=ctx.repository_id,
        validation_id=spec.validation_id,
        exit_code=proc.returncode,
        timed_out=False,
        truncated=truncated,
        output=combined[:cap],
    )
