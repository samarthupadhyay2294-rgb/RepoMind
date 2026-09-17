"""Agent domain models (Part 7). Repository content inside Evidence is
untrusted data — provenance is kept so citations stay evidence-backed."""

from typing import Any

from pydantic import BaseModel, Field

REQUEST_TYPES = (
    "code_location",
    "code_explanation",
    "architecture",
    "bug_investigation",
    "dependency_question",
    "git_history",
    "symbol_lookup",
    "reference_lookup",
    "repository_structure",
    "documentation_question",
    "repository_improvement",
    "general",
)

# Trivial lookups skip the plan/tool loop when retrieval already answers.
SIMPLE_REQUEST_TYPES = frozenset(
    {
        "code_location",
        "symbol_lookup",
        "reference_lookup",
        "repository_structure",
        "documentation_question",
    }
)


class Evidence(BaseModel):
    source_type: str  # "retrieval" | "tool"
    repository_id: str
    file_path: str = ""
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=1, ge=1)
    content: str = ""
    relevance_score: float = 0.0
    tool_name: str | None = None

    @property
    def citation_key(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


class Citation(BaseModel):
    repository_id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    source_type: str = ""
    reason: str = ""


class AgentStep(BaseModel):
    node: str
    detail: str = ""


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    ok: bool = True
    result_count: int = 0
    warning: str = ""
    duration_ms: float = 0.0


class RequestClassification(BaseModel):
    request_type: str = "general"
    confidence: float = 0.0
    # P2: the classifier may advise skipping the fixed retrieval pass
    # (e.g. pure file inspection). Defaults True → legacy behavior.
    needs_retrieval: bool = True


class InvestigationStep(BaseModel):
    action: str
    target: str = ""
    purpose: str = ""
    # P3: structured per-tool arguments. Empty → legacy single-target
    # mapping via ``target``. When non-empty, ``args`` wins.
    args: dict[str, Any] = Field(default_factory=dict)


class InvestigationPlan(BaseModel):
    steps: list[InvestigationStep] = Field(default_factory=list)


class Evaluation(BaseModel):
    sufficient: bool = False
    confidence: float = 0.0
    missing_information: list[str] = Field(default_factory=list)
