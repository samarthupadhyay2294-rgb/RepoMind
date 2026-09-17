"""Secret redaction for evidence, prompts, and logs (Part 1 security).

Secrets never appear in evidence excerpts, prompts, logs, UI payloads, or
metrics. This module redacts credential-shaped content before persistence
or model-context assembly and reports whether redaction occurred.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{0,200}")),
    (
        "bearer-token",
        re.compile(r"\b[bB]earer\s+[A-Za-z0-9\-._~+/=]{8,}", re.IGNORECASE),
    ),
    (
        "api-key-assign",
        re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[^'\"\s;]{6,}"),
    ),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9\-_]{8,}\b")),
    (
        "password-assign",
        re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s;]{4,}"),
    ),
    (
        "connection-string",
        re.compile(
            r"(?i)(postgres(ql)?|mysql|mongodb(\+srv)?|redis)://[^\s'\";]{4,}",
        ),
    ),
    (
        "secret-assign",
        re.compile(r"(?i)(secret|client_secret)\s*[:=]\s*['\"]?[^'\"\s;]{4,}"),
    ),
)

_PLACEHOLDER = "[REDACTED]"


def redact_text(text: str) -> tuple[str, bool]:
    """Redact secret-shaped substrings. Returns (redacted_text, was_redacted)."""
    if not text:
        return text, False
    redacted = text
    hit = False
    for _name, pattern in _PATTERNS:
        redacted, count = pattern.subn(_PLACEHOLDER, redacted)
        if count:
            hit = True
    return redacted, hit


def sanitize_for_log(text: str, max_chars: int = 200) -> str:
    """Log-safe preview: redacted and truncated (never raw source/secrets)."""
    redacted, _ = redact_text(text or "")
    return redacted[:max_chars]
