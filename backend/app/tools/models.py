"""Structured tool I/O. Repository content inside these models is
untrusted data (evidence for a future agent) — never instructions."""

from pydantic import BaseModel, Field


class CodeMatch(BaseModel):
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    snippet: str = ""


class SearchCodeResult(BaseModel):
    repository_id: str
    matches: list[CodeMatch] = Field(default_factory=list)
    total_matches: int = 0
    truncated: bool = False


class ReferenceMatch(BaseModel):
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    snippet: str = ""


class FindReferencesResult(BaseModel):
    repository_id: str
    symbol: str
    matches: list[ReferenceMatch] = Field(default_factory=list)
    total_matches: int = 0
    truncated: bool = False


class ReadFileResult(BaseModel):
    repository_id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = ""
    truncated: bool = False


class DirectoryEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" | "directory"


class ListDirectoryResult(BaseModel):
    repository_id: str
    path: str
    entries: list[DirectoryEntry] = Field(default_factory=list)
    truncated: bool = False


class SymbolResult(BaseModel):
    name: str
    kind: str  # "function" | "class" | "method" (+ "fallback" marker below)
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: str = ""
    fallback: bool = False


class GetSymbolResult(BaseModel):
    repository_id: str
    symbol: str
    matches: list[SymbolResult] = Field(default_factory=list)
    truncated: bool = False


class GitCommit(BaseModel):
    commit_sha: str
    author: str = ""
    timestamp: str = ""
    message: str = ""


class GitLogResult(BaseModel):
    repository_id: str
    commits: list[GitCommit] = Field(default_factory=list)
    truncated: bool = False


class BlameLine(BaseModel):
    line: int = Field(ge=1)
    commit_sha: str = ""
    author: str = ""
    timestamp: str = ""
    summary: str = ""


class GitBlameResult(BaseModel):
    repository_id: str
    file_path: str
    lines: list[BlameLine] = Field(default_factory=list)


class DependencyNode(BaseModel):
    id: str  # repo-relative path, or "external:<name>" when unresolvable
    external: bool = False


class DependencyEdge(BaseModel):
    source: str
    target: str
    kind: str = "import"


class DependencyGraph(BaseModel):
    repository_id: str
    nodes: list[DependencyNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    truncated: bool = False


class ValidationResult(BaseModel):
    repository_id: str
    validation_id: str
    exit_code: int
    timed_out: bool = False
    truncated: bool = False
    output: str = ""
