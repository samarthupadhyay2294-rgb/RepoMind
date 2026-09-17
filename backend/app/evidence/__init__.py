"""Shared evidence primitives (Part 1 foundation)."""

from app.evidence.budget import pack_evidence
from app.evidence.citations import (
    find_unsupported_prose_refs,
    scrub_unsupported_refs,
    validate_structured_citations,
)
from app.evidence.dedupe import deduplicate_evidence, rank_key
from app.evidence.items import (
    EvidenceItem,
    EvidenceValidationError,
    canonical_relative_path,
    evidence_usable_for,
    validate_evidence_item,
)
from app.evidence.normalize import normalize_retrieval_hit, normalize_tool_result
from app.evidence.redaction import redact_text, sanitize_for_log

__all__ = [
    "EvidenceItem",
    "EvidenceValidationError",
    "canonical_relative_path",
    "deduplicate_evidence",
    "evidence_usable_for",
    "find_unsupported_prose_refs",
    "normalize_retrieval_hit",
    "normalize_tool_result",
    "pack_evidence",
    "rank_key",
    "redact_text",
    "sanitize_for_log",
    "scrub_unsupported_refs",
    "validate_evidence_item",
    "validate_structured_citations",
]
