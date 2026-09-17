"""Prompt-injection defenses (plan v2 A.4 / §13).

Labeling evidence 'untrusted' is not enforcement by itself, so:
1. Evidence enters prompts only inside fixed delimiter blocks.
2. Common injection patterns are flagged *before* model context assembly
   and surfaced as agent warnings (content still treated as data only).
"""

import re

EVIDENCE_BEGIN = "<<<REPOSITORY_EVIDENCE_BEGIN>>>"
EVIDENCE_END = "<<<REPOSITORY_EVIDENCE_END>>>"

_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "ignore-instructions",
        r"ignor(e|ing)\s+(all\s+)?(previous|prior|above)\s+instructions?",
    ),
    ("disregard-instructions", r"disregard\s+.*instructions?"),
    ("override-policy", r"overrid(e|ing)\s+.*(polic|instruction|guardrail)"),
    (
        "reveal-secrets",
        r"(reveal|show|disclose|print|output)\s+.*(api[\s_-]?key|secret|token|password|credential)",
    ),
    (
        "run-command",
        r"(run|execut(e|ing)|eval)\s+(this\s+|the\s+)?(command|script|code|shell)",
    ),
    ("system-prompt", r"(system|developer)\s+prompt"),
    (
        "new-role",
        r"(you\s+are\s+now|act\s+as\s+(a\s+)?(?!assistant\b)[a-z]+|pretend\s+to\s+be)",
    ),
    ("exfiltrate", r"(send|post|upload|transmit)\s+.*\b(to|at)\b\s+\S+"),
)


def flag_injection_patterns(text: str) -> list[str]:
    """Return names of matched injection patterns (empty when clean)."""
    lowered = text.lower()
    return [name for name, pattern in _PATTERNS if re.search(pattern, lowered)]


def scan_evidence(items: list[dict]) -> dict[str, int]:
    """Count pattern hits per evidence item id for warning summaries."""
    counts: dict[str, int] = {}
    for item in items:
        hits = flag_injection_patterns(str(item.get("content", "")))
        if hits:
            key = f"{item.get('file_path', '?')}:{item.get('start_line', 1)}"
            counts[key] = len(hits)
    return counts
