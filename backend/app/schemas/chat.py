"""Chat request/response schemas. No graph internals leak here."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: UUID
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


class ChatCitation(BaseModel):
    repository_id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    source_type: str = ""
    reason: str = ""


class ChatMetrics(BaseModel):
    """Honest per-run counters (Gap #8). Token fields stay ``None``: the
    provider layer returns text only, and invented counts are worse than
    none. Steps/tool calls come from graph state; latency is measured."""

    latency_ms: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    steps: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    steps_taken: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    request_type: str = "general"
    session_id: str
    metrics: ChatMetrics | None = None
    # Part 1 additive fields (existing fields unchanged).
    snapshot_id: str | None = None
    stop_reason: str = ""
    evidence_items_total: int = 0
    evidence_items_used: int = 0
    evidence_truncated: bool = False


class ChatTraceResponse(BaseModel):
    """Investigation trace for a past session (from the graph checkpointer)."""

    session_id: str
    repository_id: str
    request_type: str = "general"
    steps_taken: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)
    answer: str = ""
