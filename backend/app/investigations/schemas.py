"""Investigation schemas (Part 4/5)."""

from pydantic import BaseModel, Field


class InvestigationCreate(BaseModel):
    error_text: str = Field(min_length=1, max_length=4000)
    stack_trace: str | None = Field(default=None, max_length=8000)
    affected_route: str | None = Field(default=None, max_length=512)
    environment: str | None = Field(default=None, max_length=256)
    expected_behavior: str | None = Field(default=None, max_length=2000)
    actual_behavior: str | None = Field(default=None, max_length=2000)
    reproduction_steps: str | None = Field(default=None, max_length=2000)
    snapshot_id: str | None = None


class InvestigationFinding(BaseModel):
    claim: str
    confidence: str = "likely"
    evidence_refs: list[str] = Field(default_factory=list)


class InvestigationResponse(BaseModel):
    id: str
    repository_id: str
    snapshot_id: str
    snapshot_active: bool = True
    status: str
    verdict: str | None = None
    confidence: str | None = None
    summary: str = ""
    findings: list[dict] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    stop_reason: str = ""
    tool_calls: int = 0
    llm_calls: int = 0
    duration_ms: float = 0.0
    evidence_truncated: bool = False
    session_id: str | None = None
    created_at: str = ""
