"""Graph-backed agent tools (Part 2 → existing Part 6/7 registry).

These are the DB-backed counterparts of the filesystem tools
``dependency_graph`` / ``get_symbol`` / ``find_references``. They query the
snapshot-scoped graph tables (repository + snapshot isolation at SQL level),
enforce server-side bounds, validate structured arguments, and normalize
every hit into an ``EvidenceItem``.

The existing filesystem tools remain unchanged; the agent may use either
source, but graph results always carry snapshot provenance.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.graph import CodeRelationship, CodeSymbol
from app.evidence.items import EvidenceItem
from app.exceptions import ToolError


def _require_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ToolError(f"Invalid {field}.", code="TOOL_INVALID_QUERY") from None


async def graph_get_symbol(
    session: AsyncSession,
    *,
    repository_id: str,
    snapshot_id: str,
    symbol: str,
    path: str | None = None,
    limit: int = 20,
) -> tuple[list[dict], list[EvidenceItem]]:
    """DB-backed symbol lookup. Returns (nodes, evidence)."""
    cleaned = (symbol or "").strip()
    if not cleaned:
        raise ToolError("Symbol must not be empty.", code="TOOL_INVALID_QUERY")
    if len(cleaned) > 500:
        raise ToolError("Symbol exceeds 500 characters.", code="TOOL_QUERY_TOO_LONG")
    repo_id = _require_uuid(repository_id, "repository_id")
    snap_id = _require_uuid(snapshot_id, "snapshot_id")
    lim = max(1, min(int(limit or 20), 50))
    q = select(CodeSymbol).where(
        CodeSymbol.repository_id == repo_id,
        CodeSymbol.snapshot_id == snap_id,
        CodeSymbol.name == cleaned,
    )
    if path:
        q = q.where(CodeSymbol.path == path.strip().replace("\\", "/"))
    q = q.order_by(CodeSymbol.path).limit(lim + 1)
    rows = list((await session.execute(q)).scalars().all())[:lim]
    nodes, evidence = [], []
    for row in rows:
        nodes.append(
            {
                "id": str(row.id),
                "type": row.symbol_type,
                "name": row.name,
                "qualified_name": row.qualified_name,
                "path": row.path,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "signature": row.signature or "",
                "snapshot_id": str(row.snapshot_id),
                "provenance": row.provenance,
            }
        )
        evidence.append(
            EvidenceItem(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind="graph",
                path=row.path,
                start_line=max(1, row.start_line),
                end_line=max(1, max(row.end_line, row.start_line)),
                excerpt=(row.signature or "")[:500],
                source_tool="get_symbol",
                source_ref=str(row.id),
                confidence="direct",
                redacted=False,
            )
        )
    return nodes, evidence


async def graph_find_references(
    session: AsyncSession,
    *,
    repository_id: str,
    snapshot_id: str,
    symbol_id: str,
    limit: int = 50,
) -> tuple[list[dict], list[EvidenceItem]]:
    """Inbound references/calls to one graph node. Returns (edges, evidence)."""
    repo_id = _require_uuid(repository_id, "repository_id")
    snap_id = _require_uuid(snapshot_id, "snapshot_id")
    node_id = _require_uuid(symbol_id, "symbol_id")
    lim = max(1, min(int(limit or 50), 50))
    # Node itself must belong to this repo+snapshot (isolation first).
    node = (
        await session.execute(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repo_id,
                CodeSymbol.snapshot_id == snap_id,
                CodeSymbol.id == node_id,
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise ToolError("Symbol not found.", code="TOOL_NOT_FOUND")
    q = (
        select(CodeRelationship)
        .where(
            CodeRelationship.repository_id == repo_id,
            CodeRelationship.snapshot_id == snap_id,
            CodeRelationship.target_symbol_id == node_id,
            CodeRelationship.relationship_type.in_(
                ["calls", "references", "uses_type"]
            ),
        )
        .limit(lim + 1)
    )
    rows = list((await session.execute(q)).scalars().all())
    rows = rows[:lim]
    out, evidence = [], []
    for edge in rows:
        out.append(
            {
                "id": str(edge.id),
                "source": str(edge.source_symbol_id),
                "target": str(edge.target_symbol_id),
                "relationship_type": edge.relationship_type,
                "confidence": edge.confidence,
                "provenance": edge.provenance,
                "path": edge.path,
                "start_line": edge.start_line,
                "end_line": edge.end_line,
            }
        )
        evidence.append(
            EvidenceItem(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                kind="graph",
                path=edge.path or node.path,
                start_line=max(1, edge.start_line),
                end_line=max(1, max(edge.end_line, edge.start_line)),
                excerpt=(edge.excerpt or "")[:500],
                source_tool="find_references",
                source_ref=str(edge.id),
                confidence="direct"
                if edge.provenance in ("parser", "resolver")
                else "derived",
                redacted=False,
            )
        )
    return out, evidence


async def graph_dependency(
    session: AsyncSession,
    *,
    repository_id: str,
    snapshot_id: str,
    node_id: str,
    direction: str = "both",
    depth: int = 2,
    relationship_types: list[str] | None = None,
    limit: int = 50,
) -> tuple[list[dict], list[dict], list[EvidenceItem]]:
    """Bounded dependency neighborhood. Returns (nodes, edges, evidence)."""
    from app.graph import service as graph_service

    repo_id = _require_uuid(repository_id, "repository_id")
    snap_id = _require_uuid(snapshot_id, "snapshot_id")
    root = _require_uuid(node_id, "node_id")
    if direction not in ("both", "in", "out", "inbound", "outbound"):
        raise ToolError("Invalid direction.", code="TOOL_INVALID_QUERY")
    depth = max(0, min(int(depth), 5))
    lim = max(1, min(int(limit or 50), 100))
    nodes, edges, _, _ = await graph_service.neighborhood(
        session,
        repository_id=repo_id,
        snapshot_id=snap_id,
        root_id=root,
        depth=depth,
        direction=direction,
        relationship_types=relationship_types,
        node_types=None,
        max_nodes=lim,
        max_edges=lim * 2,
    )
    sid = str(snap_id)
    node_dicts = [graph_service.node_to_dict(n, sid) for n in nodes]
    edge_dicts = [graph_service.edge_to_dict(e) for e in edges]
    evidence = [
        EvidenceItem(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            kind="graph",
            path=e["evidence"]["path"] or "",
            start_line=max(1, e["evidence"]["start_line"]),
            end_line=max(
                1, max(e["evidence"]["end_line"], e["evidence"]["start_line"])
            ),
            excerpt=(e["evidence"]["excerpt"] or "")[:500],
            source_tool="dependency_graph",
            source_ref=e["id"],
            confidence="direct"
            if e["provenance"] in ("parser", "resolver")
            else "derived",
            redacted=False,
        )
        for e in edge_dicts
        if e["evidence"]["path"]
    ]
    return node_dicts, edge_dicts, evidence
