"""Snapshot-scoped evidence/index cache keys (Part 1 foundation).

Every evidence/index-related cache key includes repository_id AND
snapshot_id plus relevant query/configuration/version information, so
stale evidence from one snapshot is never returned for another.
"""

from __future__ import annotations

import hashlib

CACHE_VERSION = "v1"


def evidence_cache_key(
    *,
    repository_id: str,
    snapshot_id: str | None,
    query: str,
    top_k: int = 8,
    namespace: str = "retrieval",
) -> str:
    """Build a snapshot-isolated cache key for evidence/index lookups."""
    if not repository_id.strip():
        raise ValueError("repository_id is required for cache keys.")
    snapshot_scope = snapshot_id or "legacy"
    digest = hashlib.sha256(
        f"{namespace}|{query}|{top_k}|{CACHE_VERSION}".encode()
    ).hexdigest()[:32]
    return f"{namespace}:{repository_id}:{snapshot_scope}:{digest}"


def invalidate_snapshot_caches() -> str:
    """Document the invalidation rule: new snapshots mint new key scopes.

    No deletion is needed — keys embed the snapshot_id, so activating a
    new snapshot automatically orphans the previous scope. Returns the
    active cache version for observability.
    """
    return CACHE_VERSION
