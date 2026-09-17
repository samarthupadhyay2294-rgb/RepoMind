"""Pydantic schemas for the Part 2 graph API."""

from pydantic import BaseModel, Field


class GraphLimits(BaseModel):
    max_nodes: int
    max_edges: int
    max_depth: int


class GraphNeighborhoodResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    snapshot_active: bool = True
    root: str | None = None
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    truncated: bool = False
    limit_reason: str | None = None
    limits: GraphLimits


class GraphNodeResponse(BaseModel):
    node: dict
    relationships: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)


class GraphEdgeResponse(BaseModel):
    edge: dict
    source: dict
    target: dict
    evidence: list[dict] = Field(default_factory=list)


class GraphExplainRequest(BaseModel):
    node_id: str | None = None
    edge_id: str | None = None
    question: str = Field(default="", max_length=2000)


class GraphExplainResponse(BaseModel):
    explanation: str
    evidence: list[dict] = Field(default_factory=list)
    confidence: str = "medium"
