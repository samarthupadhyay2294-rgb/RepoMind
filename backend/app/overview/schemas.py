"""Structured overview schema (Part 3).

The LLM returns this shape as JSON — never free-form Markdown as the
primary data model. Every factual claim carries evidence IDs that are
validated against the exact (repository_id, snapshot_id) evidence set.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["confirmed", "candidate", "uncertain"]


class EntryPoint(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    type: str = Field(default="file", max_length=64)
    path: str = Field(min_length=1, max_length=1024)
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=1, ge=1)
    description: str = Field(default="", max_length=2000)
    confidence: Confidence = "candidate"
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("end_line")
    @classmethod
    def _range(cls, v: int, info: Any) -> int:
        start = (info.data or {}).get("start_line", 1)
        return v if v >= start else start


class Component(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    type: str = Field(default="module", max_length=64)
    description: str = Field(default="", max_length=3000)
    paths: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DataFlow(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)


class Boundary(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    paths: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class KeyDependency(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    purpose: str = Field(default="", max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)


class ConfigurationArea(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    description: str = Field(default="", max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)


class Uncertainty(BaseModel):
    statement: str = Field(min_length=1, max_length=2000)
    reason: str = Field(default="", max_length=2000)


class StructuredOverview(BaseModel):
    """Validated LLM output: summaries + evidence-linked claims."""

    summary: str = Field(min_length=1, max_length=6000)
    architecture_style: str | None = Field(default=None, max_length=64)
    entry_points: list[EntryPoint] = Field(default_factory=list, max_length=20)
    components: list[Component] = Field(default_factory=list, max_length=20)
    data_flows: list[DataFlow] = Field(default_factory=list, max_length=20)
    boundaries: list[Boundary] = Field(default_factory=list, max_length=20)
    key_dependencies: list[KeyDependency] = Field(default_factory=list, max_length=30)
    configuration_areas: list[ConfigurationArea] = Field(
        default_factory=list, max_length=20
    )
    uncertainties: list[Uncertainty] = Field(default_factory=list, max_length=20)


class OverviewResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    snapshot_active: bool = True
    overview_id: str
    generated_at: str
    generation_model: str
    generation_status: str
    stale: bool = False
    overview: dict[str, Any]
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False
    evidence_items_total: int = 0
    evidence_items_used: int = 0
