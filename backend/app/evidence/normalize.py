"""Evidence normalization layer (Part 1 foundation).

Converts heterogeneous tool results (semantic retrieval, read_file,
search_code, future graph/validation tools, metadata) into validated
``EvidenceItem`` dicts. Existing tool result behavior is preserved —
normalization is additive and never mutates tool outputs.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.evidence.items import EvidenceValidationError, canonical_relative_path
from app.evidence.redaction import redact_text

# source_tool → evidence kind mapping (graph/validation tools land here later).
_TOOL_KINDS: dict[str, str] = {
    "semantic_retrieval": "search",
    "semantic_search": "search",
    "search_code": "search",
    "read_file": "code",
    "get_symbol": "code",
    "find_references": "code",
    "git_blame": "code",
    "git_log": "metadata",
    "list_directory": "metadata",
    "dependency_graph": "graph",
    "graph_neighbors": "graph",
    "find_symbol": "graph",
    "find_paths": "graph",
    "edge_evidence": "graph",
    "run_validation": "validation",
}


def _base(
    *,
    repository_id: str,
    snapshot_id: str | None,
    kind: str,
    path: str,
    start_line: int,
    end_line: int,
    excerpt: str,
    source_tool: str,
    source_ref: str = "",
    confidence: str = "direct",
    relevance_score: float = 0.5,
) -> dict[str, Any]:
    cleaned_path = canonical_relative_path(path) if path else ""
    start = max(1, int(start_line or 1))
    end = max(1, int(end_line or 1))
    if end < start:
        raise EvidenceValidationError(
            f"invalid line range {start}-{end}.", code="EVIDENCE_RANGE"
        )
    excerpt_text, was_redacted = redact_text(str(excerpt or ""))
    return {
        "id": f"ev_{uuid.uuid4().hex[:12]}",
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "kind": kind,
        "path": cleaned_path,
        "start_line": start,
        "end_line": end,
        "excerpt": excerpt_text,
        "source_tool": source_tool,
        "source_ref": source_ref,
        "confidence": confidence,
        "redacted": was_redacted,
        # Agent-rank/display hints (kept alongside the contract; harmless
        # for future persistence which selects contract fields only).
        "file_path": cleaned_path,
        "content": excerpt_text,
        "relevance_score": float(relevance_score),
    }


def normalize_retrieval_hit(
    hit: Any,
    *,
    repository_id: str,
    snapshot_id: str | None,
    cap_chars: int = 20000,
) -> dict[str, Any]:
    """Normalize one semantic-retrieval hit (RetrievalResult or Qdrant hit)."""
    payload = getattr(hit, "payload", None)
    if isinstance(payload, dict):
        file_path = str(payload.get("file_path", "") or "")
        start = int(payload.get("start_line", 1) or 1)
        end = int(payload.get("end_line", 1) or 1)
        content = str(payload.get("content", "") or "")
        score = float(getattr(hit, "score", 0.0) or 0.0)
        hit_repo = str(payload.get("repository_id", repository_id))
        hit_snap = payload.get("snapshot_id")
    else:
        file_path = str(getattr(hit, "file_path", "") or "")
        start = int(getattr(hit, "start_line", 1) or 1)
        end = int(getattr(hit, "end_line", 1) or 1)
        content = str(getattr(hit, "content", "") or "")
        score = float(getattr(hit, "score", 0.0) or 0.0)
        hit_repo = str(getattr(hit, "repository_id", repository_id))
        hit_snap = getattr(hit, "snapshot_id", None)
    if hit_repo != repository_id:
        raise EvidenceValidationError(
            "retrieval hit repository mismatch.", code="EVIDENCE_REPOSITORY_MISMATCH"
        )
    if snapshot_id is not None and hit_snap is not None and hit_snap != snapshot_id:
        raise EvidenceValidationError(
            "retrieval hit snapshot mismatch.", code="EVIDENCE_SNAPSHOT_MISMATCH"
        )
    return _base(
        repository_id=repository_id,
        snapshot_id=snapshot_id if snapshot_id is not None else hit_snap,
        kind="search",
        path=file_path,
        start_line=start,
        end_line=end,
        excerpt=content[:cap_chars],
        source_tool="semantic_search",
        confidence="derived",
        relevance_score=score,
    )


def normalize_tool_result(
    tool_name: str,
    result: Any,
    *,
    repository_id: str,
    snapshot_id: str | None,
    source_ref: str = "",
    cap_chars: int = 20000,
) -> list[dict[str, Any]]:
    """Normalize any supported tool result into evidence dicts.

    Unknown result shapes yield no items (never a crash); tool behavior
    itself is unchanged. Graph/validation/metadata tools share this path.
    """
    kind = _TOOL_KINDS.get(tool_name, "code")

    def get(name: str) -> Any:
        return getattr(result, name, None)

    if tool_name == "read_file":
        return [
            _base(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind=kind,
                path=str(get("file_path") or ""),
                start_line=int(get("start_line") or 1),
                end_line=int(get("end_line") or 1),
                excerpt=str(get("content") or "")[:cap_chars],
                source_tool=tool_name,
                source_ref=source_ref,
                confidence="direct",
                relevance_score=0.9,
            )
        ]
    matches = get("matches")
    if isinstance(matches, list):
        items: list[dict[str, Any]] = []
        for match in matches:
            snippet = (
                getattr(match, "snippet", None)
                or getattr(match, "signature", None)
                or ""
            )
            items.append(
                _base(
                    repository_id=repository_id,
                    snapshot_id=snapshot_id,
                    kind=kind,
                    path=str(getattr(match, "file_path", "") or ""),
                    start_line=int(getattr(match, "start_line", 1) or 1),
                    end_line=int(getattr(match, "end_line", 1) or 1),
                    excerpt=str(snippet)[:cap_chars],
                    source_tool=tool_name,
                    source_ref=source_ref,
                    confidence="direct" if tool_name == "read_file" else "derived",
                )
            )
        return items
    if tool_name == "list_directory":
        entries = get("entries") or []
        content = "\n".join(f"{e.type} {e.path}" for e in entries[:100])
        return [
            _base(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind="metadata",
                path=str(get("path") or ""),
                start_line=1,
                end_line=1,
                excerpt=content[:cap_chars],
                source_tool=tool_name,
                source_ref=source_ref,
                confidence="derived",
            )
        ]
    if tool_name == "run_validation":
        content = (
            f"[{get('validation_id')}] exit={get('exit_code')} "
            f"timed_out={get('timed_out')}\n{get('output')}"
        )
        return [
            _base(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind="validation",
                path="",
                start_line=1,
                end_line=1,
                excerpt=content[:cap_chars],
                source_tool=tool_name,
                source_ref=source_ref,
                confidence="derived",
            )
        ]
    generic_content = get("content")
    if isinstance(generic_content, str):
        file_path = str(get("file_path") or "")
        return [
            _base(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind=kind,
                path=file_path,
                start_line=int(get("start_line") or 1),
                end_line=int(get("end_line") or 1),
                excerpt=generic_content[:cap_chars],
                source_tool=tool_name,
                source_ref=source_ref,
                confidence="derived",
            )
        ]
    return []
