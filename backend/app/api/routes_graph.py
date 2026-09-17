"""Graph API: bounded neighborhoods, node/edge detail, evidence-grounded explain.

Isolation: every query filters by (repository_id, snapshot_id) at SQL level.
Feature flag: DEPENDENCY_GRAPH=false -> 403 GRAPH_DISABLED (chat unaffected).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner_id
from app.config import settings
from app.db.models.snapshot import RepositoryIndexSnapshot, SnapshotStatus
from app.db.session import get_db_session
from app.exceptions import AppError
from app.graph import service as graph_service
from app.graph.schemas import (
    GraphEdgeResponse,
    GraphExplainRequest,
    GraphExplainResponse,
    GraphLimits,
    GraphNeighborhoodResponse,
    GraphNodeResponse,
)
from app.services import repositories as repository_service
from app.services import snapshots as snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repositories", tags=["graph"])


def _require_graph_enabled() -> None:
    if not settings.DEPENDENCY_GRAPH:
        raise AppError(
            "Dependency graph is disabled for this deployment.",
            code="GRAPH_DISABLED",
            status_code=403,
        )


async def _resolve_snapshot(
    session: AsyncSession, owner_id: str, repository_id: UUID, snapshot_id: str | None
):
    await repository_service.get_repository(session, owner_id, repository_id)
    active = await snapshot_service.get_active_snapshot(session, repository_id)
    if snapshot_id:
        try:
            sid = UUID(snapshot_id)
        except ValueError:
            raise AppError(
                "Invalid snapshot_id.", code="GRAPH_INVALID_SNAPSHOT", status_code=422
            )
        row = (
            await session.execute(
                select(RepositoryIndexSnapshot).where(
                    RepositoryIndexSnapshot.id == sid,
                    RepositoryIndexSnapshot.repository_id == repository_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(
                "Snapshot not found.", code="GRAPH_SNAPSHOT_NOT_FOUND", status_code=404
            )
        if row.status != SnapshotStatus.READY:
            raise AppError(
                "Snapshot is not ready.",
                code="GRAPH_SNAPSHOT_NOT_READY",
                status_code=409,
            )
        return row, False
    if active is None:
        raise AppError(
            "No indexed snapshot for this repository.",
            code="GRAPH_NO_SNAPSHOT",
            status_code=409,
        )
    return active, True


@router.get("/{repository_id}/graph", response_model=GraphNeighborhoodResponse)
async def get_graph(
    repository_id: UUID,
    snapshot_id: str | None = Query(None),
    node_id: str | None = Query(None),
    depth: int = Query(2, ge=0, le=10),
    direction: str = Query("both"),
    relationship_types: str | None = Query(None),
    node_types: str | None = Query(None),
    limit: int = Query(100, ge=1, le=600),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> GraphNeighborhoodResponse:
    _require_graph_enabled()
    if direction not in ("both", "in", "out", "inbound", "outbound"):
        raise AppError(
            "Invalid direction.", code="GRAPH_INVALID_REQUEST", status_code=422
        )
    snapshot, is_active = await _resolve_snapshot(
        session, owner_id, repository_id, snapshot_id
    )
    max_depth = min(depth, settings.GRAPH_MAX_DEPTH, settings.GRAPH_HARD_MAX_DEPTH)
    max_nodes = min(limit, settings.GRAPH_MAX_NODES, settings.GRAPH_HARD_MAX_NODES)
    max_edges = min(settings.GRAPH_MAX_EDGES, settings.GRAPH_HARD_MAX_EDGES)
    root_uuid = None
    if node_id:
        try:
            root_uuid = UUID(node_id)
        except ValueError:
            raise AppError(
                "Invalid node_id.", code="GRAPH_INVALID_REQUEST", status_code=422
            )
    rel_types = [
        r.strip() for r in (relationship_types or "").split(",") if r.strip()
    ] or None
    n_types = [t.strip() for t in (node_types or "").split(",") if t.strip()] or None
    nodes, edges, truncated, reason = await graph_service.neighborhood(
        session,
        repository_id=repository_id,
        snapshot_id=snapshot.id,
        root_id=root_uuid,
        depth=max_depth,
        direction=direction,
        relationship_types=rel_types,
        node_types=n_types,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    sid = str(snapshot.id)
    return GraphNeighborhoodResponse(
        repository_id=str(repository_id),
        snapshot_id=sid,
        snapshot_active=is_active,
        root=node_id,
        nodes=[graph_service.node_to_dict(n, sid) for n in nodes],
        edges=[graph_service.edge_to_dict(e) for e in edges],
        truncated=truncated,
        limit_reason=reason,
        limits=GraphLimits(
            max_nodes=max_nodes, max_edges=max_edges, max_depth=max_depth
        ),
    )


@router.get("/{repository_id}/graph/nodes/{node_id}", response_model=GraphNodeResponse)
async def get_graph_node(
    repository_id: UUID,
    node_id: UUID,
    snapshot_id: str | None = Query(None),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> GraphNodeResponse:
    _require_graph_enabled()
    snapshot, _ = await _resolve_snapshot(session, owner_id, repository_id, snapshot_id)
    node = await graph_service.get_symbol(session, repository_id, snapshot.id, node_id)
    if node is None:
        raise AppError(
            "Graph node not found.", code="GRAPH_NODE_NOT_FOUND", status_code=404
        )
    edges = await graph_service.direct_edges(
        session, repository_id, snapshot.id, node.id
    )
    sid = str(snapshot.id)
    evidence = [
        {
            "repository_id": str(repository_id),
            "snapshot_id": sid,
            "kind": "graph",
            "path": node.path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "excerpt": (node.signature or "")[:500],
            "source_tool": "graph",
            "source_ref": str(node.id),
            "confidence": "direct",
            "redacted": False,
        }
    ]
    return GraphNodeResponse(
        node=graph_service.node_to_dict(node, sid),
        relationships=[graph_service.edge_to_dict(e) for e in edges],
        evidence=evidence,
    )


@router.get("/{repository_id}/graph/edges/{edge_id}", response_model=GraphEdgeResponse)
async def get_graph_edge(
    repository_id: UUID,
    edge_id: UUID,
    snapshot_id: str | None = Query(None),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> GraphEdgeResponse:
    _require_graph_enabled()
    snapshot, _ = await _resolve_snapshot(session, owner_id, repository_id, snapshot_id)
    edge = await graph_service.get_edge(session, repository_id, snapshot.id, edge_id)
    if edge is None:
        raise AppError(
            "Graph edge not found.", code="GRAPH_EDGE_NOT_FOUND", status_code=404
        )
    source = await graph_service.get_symbol(
        session, repository_id, snapshot.id, edge.source_symbol_id
    )
    target = await graph_service.get_symbol(
        session, repository_id, snapshot.id, edge.target_symbol_id
    )
    if source is None or target is None:
        raise AppError(
            "Graph edge endpoints not found.",
            code="GRAPH_EDGE_NOT_FOUND",
            status_code=404,
        )
    sid = str(snapshot.id)
    evidence = [
        {
            "repository_id": str(repository_id),
            "snapshot_id": sid,
            "kind": "graph",
            "path": edge.path,
            "start_line": edge.start_line,
            "end_line": edge.end_line,
            "excerpt": (edge.excerpt or "")[:500],
            "source_tool": "graph",
            "source_ref": str(edge.id),
            "confidence": "direct"
            if edge.provenance in ("parser", "resolver")
            else "derived",
            "redacted": False,
        }
    ]
    return GraphEdgeResponse(
        edge=graph_service.edge_to_dict(edge),
        source=graph_service.node_to_dict(source, sid),
        target=graph_service.node_to_dict(target, sid),
        evidence=evidence,
    )


@router.post("/{repository_id}/graph/explain", response_model=GraphExplainResponse)
async def explain_graph(
    repository_id: UUID,
    payload: GraphExplainRequest,
    snapshot_id: str | None = Query(None),
    owner_id: str = Depends(get_current_owner_id),
    session: AsyncSession = Depends(get_db_session),
) -> GraphExplainResponse:
    _require_graph_enabled()
    snapshot, _ = await _resolve_snapshot(session, owner_id, repository_id, snapshot_id)
    sid = str(snapshot.id)
    if not payload.edge_id and not payload.node_id:
        raise AppError(
            "Provide node_id or edge_id.", code="GRAPH_INVALID_REQUEST", status_code=422
        )
    evidence: list[dict] = []
    description = ""
    if payload.edge_id:
        try:
            eid = UUID(payload.edge_id)
        except ValueError:
            raise AppError(
                "Invalid edge_id.", code="GRAPH_INVALID_REQUEST", status_code=422
            )
        edge = await graph_service.get_edge(session, repository_id, snapshot.id, eid)
        if edge is None:
            raise AppError(
                "Graph edge not found.", code="GRAPH_EDGE_NOT_FOUND", status_code=404
            )
        source = await graph_service.get_symbol(
            session, repository_id, snapshot.id, edge.source_symbol_id
        )
        target = await graph_service.get_symbol(
            session, repository_id, snapshot.id, edge.target_symbol_id
        )
        if source is None or target is None:
            raise AppError(
                "Graph edge endpoints not found.",
                code="GRAPH_EDGE_NOT_FOUND",
                status_code=404,
            )
        evidence.append(
            {
                "path": edge.path,
                "start_line": edge.start_line,
                "end_line": edge.end_line,
                "excerpt": (edge.excerpt or "")[:500],
            }
        )
        question = payload.question or "Why does this relationship exist?"
        description = (
            f"{source.qualified_name} ({source.symbol_type}, {source.path}:"
            f"{source.start_line}-{source.end_line}) has a "
            f"{edge.relationship_type} relationship to {target.qualified_name} "
            f"({target.symbol_type}, {target.path}). The source occurrence is "
            f"{edge.path}:{edge.start_line}-{edge.end_line} "
            f"(provenance={edge.provenance}, confidence={edge.confidence:.2f}). "
            f"Question: {question}"
        )
    else:
        assert payload.node_id is not None
        try:
            nid = UUID(payload.node_id)
        except ValueError:
            raise AppError(
                "Invalid node_id.", code="GRAPH_INVALID_REQUEST", status_code=422
            )
        node = await graph_service.get_symbol(session, repository_id, snapshot.id, nid)
        if node is None:
            raise AppError(
                "Graph node not found.", code="GRAPH_NODE_NOT_FOUND", status_code=404
            )
        evidence.append(
            {
                "path": node.path,
                "start_line": node.start_line,
                "end_line": node.end_line,
            }
        )
        description = (
            f"{node.qualified_name} is a {node.symbol_type} defined in "
            f"{node.path}:{node.start_line}-{node.end_line} "
            f"(provenance={node.provenance})."
        )
    provenance_note = (
        "deterministically extracted from source" if evidence else "unavailable"
    )
    explanation = f"{description} This is {provenance_note} within snapshot {sid}."
    return GraphExplainResponse(
        explanation=explanation,
        evidence=evidence,
        confidence="high" if evidence else "low",
    )
