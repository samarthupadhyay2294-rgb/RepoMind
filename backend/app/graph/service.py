"""Graph persistence + bounded traversal (snapshot-scoped, repository-isolated).

All queries filter by (repository_id, snapshot_id) at the SQL layer — a node
is never fetched globally and ownership-checked afterwards.
"""

from __future__ import annotations

import logging
from collections import deque
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.graph import CodeRelationship, CodeSymbol
from app.db.models.repository import Repository
from app.exceptions import AppError
from app.graph.extractor import ExtractionResult

logger = logging.getLogger(__name__)

SUPPORTED_RELATIONSHIPS = frozenset(
    {
        "contains",
        "imports",
        "exports",
        "defines",
        "calls",
        "references",
        "inherits",
        "implements",
        "overrides",
        "uses_type",
    }
)
GRAPH_REL_ALIAS = {"defines": "contains"}


def _norm_rel(rel: str) -> str:
    return GRAPH_REL_ALIAS.get(rel, rel)


def active_snapshot_for(repository: Repository) -> UUID | None:
    return repository.active_snapshot_id


async def persist_extraction(
    session: AsyncSession,
    *,
    repository_id: UUID,
    snapshot_id: UUID,
    result: ExtractionResult,
) -> tuple[int, int]:
    """Persist symbols then relationships; returns (symbol_count, rel_count)."""
    key_to_id: dict[str, UUID] = {}
    for sym in result.symbols:
        row = CodeSymbol(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            stable_key=sym.stable_key,
            symbol_type=sym.symbol_type,
            name=sym.name[:512],
            qualified_name=sym.qualified_name[:1024],
            path=sym.path[:1024],
            start_line=max(1, sym.start_line),
            end_line=max(1, max(sym.end_line, sym.start_line)),
            signature=(sym.signature or "")[:2000],
            parent_symbol_id=None,
            language=sym.language,
            visibility=sym.visibility,
            provenance=sym.provenance,
            meta=sym.metadata or {},
        )
        session.add(row)
        key_to_id[sym.stable_key] = row.id
    await session.flush()
    # wire parent_symbol_id where the parent key exists
    by_key = {s.stable_key: s for s in result.symbols}
    rows = (
        (
            await session.execute(
                select(CodeSymbol).where(
                    CodeSymbol.repository_id == repository_id,
                    CodeSymbol.snapshot_id == snapshot_id,
                )
            )
        )
        .scalars()
        .all()
    )
    id_by_key = {r.stable_key: r.id for r in rows}
    for row in rows:
        extracted = by_key.get(row.stable_key)
        parent_key = extracted.parent_key if extracted is not None else None
        if parent_key and parent_key in id_by_key:
            row.parent_symbol_id = id_by_key[parent_key]
    rel_count = 0
    for rel in result.relationships:
        if (
            settings.GRAPH_ENABLE_INFERRED_RELATIONSHIPS is False
            and rel.provenance == "inferred"
        ):
            continue
        src = id_by_key.get(rel.source_key)
        dst = id_by_key.get(rel.target_key)
        if src is None or dst is None:
            continue
        rel_type = _norm_rel(rel.relationship_type)
        if rel_type not in SUPPORTED_RELATIONSHIPS:
            continue
        session.add(
            CodeRelationship(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                source_symbol_id=src,
                target_symbol_id=dst,
                relationship_type=rel_type,
                confidence=max(0.0, min(1.0, rel.confidence)),
                provenance=rel.provenance,
                path=(rel.path or "")[:1024],
                start_line=max(1, rel.start_line),
                end_line=max(1, max(rel.end_line, rel.start_line)),
                excerpt=(rel.excerpt or "")[:2000],
                meta=rel.metadata or {},
            )
        )
        rel_count += 1
    await session.flush()
    logger.info(
        "graph_persisted repository_id=%s snapshot_id=%s symbols=%d rels=%d",
        repository_id,
        snapshot_id,
        len(id_by_key),
        rel_count,
    )
    return len(id_by_key), rel_count


async def clear_snapshot_graph(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID
) -> None:
    await session.execute(
        delete(CodeRelationship).where(
            CodeRelationship.repository_id == repository_id,
            CodeRelationship.snapshot_id == snapshot_id,
        )
    )
    await session.execute(
        delete(CodeSymbol).where(
            CodeSymbol.repository_id == repository_id,
            CodeSymbol.snapshot_id == snapshot_id,
        )
    )
    await session.flush()


def node_to_dict(row: CodeSymbol, snapshot_id: str) -> dict:
    return {
        "id": str(row.id),
        "type": row.symbol_type,
        "name": row.name,
        "qualified_name": row.qualified_name,
        "path": row.path,
        "start_line": row.start_line,
        "end_line": row.end_line,
        "signature": row.signature or "",
        "language": row.language,
        "visibility": row.visibility,
        "snapshot_id": snapshot_id,
        "provenance": row.provenance,
        "parent_symbol_id": str(row.parent_symbol_id) if row.parent_symbol_id else None,
        "metadata": row.meta or {},
    }


def edge_to_dict(row: CodeRelationship) -> dict:
    return {
        "id": str(row.id),
        "source": str(row.source_symbol_id),
        "target": str(row.target_symbol_id),
        "relationship_type": row.relationship_type,
        "confidence": row.confidence,
        "provenance": row.provenance,
        "evidence": {
            "path": row.path,
            "start_line": row.start_line,
            "end_line": row.end_line,
            "excerpt": row.excerpt or "",
        },
        "metadata": row.meta or {},
    }


async def get_symbol(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID, node_id: UUID
) -> CodeSymbol | None:
    return (
        await session.execute(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.snapshot_id == snapshot_id,
                CodeSymbol.id == node_id,
            )
        )
    ).scalar_one_or_none()


async def get_edge(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID, edge_id: UUID
) -> CodeRelationship | None:
    return (
        await session.execute(
            select(CodeRelationship).where(
                CodeRelationship.repository_id == repository_id,
                CodeRelationship.snapshot_id == snapshot_id,
                CodeRelationship.id == edge_id,
            )
        )
    ).scalar_one_or_none()


async def neighborhood(
    session: AsyncSession,
    *,
    repository_id: UUID,
    snapshot_id: UUID,
    root_id: UUID | None,
    depth: int,
    direction: str,
    relationship_types: list[str] | None,
    node_types: list[str] | None,
    max_nodes: int,
    max_edges: int,
) -> tuple[list[CodeSymbol], list[CodeRelationship], bool, str | None]:
    """Bounded BFS from root (or seed set when root is None)."""
    if root_id is None:
        # seed: top-level files/directories, bounded
        seed_q = select(CodeSymbol).where(
            CodeSymbol.repository_id == repository_id,
            CodeSymbol.snapshot_id == snapshot_id,
        )
        if node_types:
            seed_q = seed_q.where(CodeSymbol.symbol_type.in_(node_types))
        else:
            seed_q = seed_q.where(
                CodeSymbol.symbol_type.in_(("file", "directory", "module"))
            )
        seed_q = seed_q.order_by(CodeSymbol.path).limit(min(max_nodes, 25))
        seeds = (await session.execute(seed_q)).scalars().all()
        return list(seeds), [], False, None
    root = await get_symbol(session, repository_id, snapshot_id, root_id)
    if root is None:
        raise AppError(
            "Graph node not found.", code="GRAPH_NODE_NOT_FOUND", status_code=404
        )
    rel_filter = {
        _norm_rel(r)
        for r in (relationship_types or [])
        if _norm_rel(r) in SUPPORTED_RELATIONSHIPS
    }
    node_map: dict[UUID, CodeSymbol] = {root.id: root}
    edges: list[CodeRelationship] = []
    seen_edges: set[UUID] = set()
    truncated = False
    limit_reason: str | None = None
    visited: set[UUID] = {root.id}
    frontier: deque[tuple[UUID, int]] = deque([(root.id, 0)])
    while frontier:
        current, dist = frontier.popleft()
        if dist >= depth:
            continue
        for dirn in ("out", "in"):
            if (
                direction != "both"
                and direction != dirn
                and direction != ("outbound" if dirn == "out" else "inbound")
            ):
                # accept both "out"/"outbound" and "in"/"inbound"
                if direction in ("out", "outbound", "in", "inbound", "both"):
                    continue
            col = (
                CodeRelationship.source_symbol_id
                if dirn == "out"
                else CodeRelationship.target_symbol_id
            )
            edge_q = select(CodeRelationship).where(
                CodeRelationship.repository_id == repository_id,
                CodeRelationship.snapshot_id == snapshot_id,
                col == current,
            )
            if rel_filter:
                edge_q = edge_q.where(
                    CodeRelationship.relationship_type.in_(sorted(rel_filter))
                )
            edge_q = edge_q.limit(max_edges + 1)
            for edge in (await session.execute(edge_q)).scalars().all():
                if edge.id in seen_edges:
                    continue
                other_id = (
                    edge.target_symbol_id if dirn == "out" else edge.source_symbol_id
                )
                if len(edges) >= max_edges:
                    truncated, limit_reason = True, "max_edges"
                    frontier.clear()
                    break
                other = await get_symbol(session, repository_id, snapshot_id, other_id)
                if other is None:
                    continue
                if node_types and other.symbol_type not in node_types:
                    continue
                if other.id not in node_map:
                    if len(node_map) >= max_nodes:
                        truncated, limit_reason = True, "max_nodes"
                        frontier.clear()
                        break
                    node_map[other.id] = other
                edges.append(edge)
                seen_edges.add(edge.id)
                if other_id not in visited:
                    visited.add(other_id)
                    frontier.append((other_id, dist + 1))
            if truncated:
                break
    return list(node_map.values()), edges, truncated, limit_reason


async def direct_edges(
    session: AsyncSession,
    repository_id: UUID,
    snapshot_id: UUID,
    node_id: UUID,
    limit: int = 50,
) -> list[CodeRelationship]:
    q = (
        select(CodeRelationship)
        .where(
            CodeRelationship.repository_id == repository_id,
            CodeRelationship.snapshot_id == snapshot_id,
            (
                (CodeRelationship.source_symbol_id == node_id)
                | (CodeRelationship.target_symbol_id == node_id)
            ),
        )
        .limit(limit)
    )
    return list((await session.execute(q)).scalars().all())


async def count_snapshot(
    session: AsyncSession, repository_id: UUID, snapshot_id: UUID
) -> tuple[int, int]:
    n = (
        await session.execute(
            select(func.count())
            .select_from(CodeSymbol)
            .where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.snapshot_id == snapshot_id,
            )
        )
    ).scalar_one()
    e = (
        await session.execute(
            select(func.count())
            .select_from(CodeRelationship)
            .where(
                CodeRelationship.repository_id == repository_id,
                CodeRelationship.snapshot_id == snapshot_id,
            )
        )
    ).scalar_one()
    return int(n), int(e)
