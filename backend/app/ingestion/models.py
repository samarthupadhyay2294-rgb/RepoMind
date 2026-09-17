"""Internal ingestion output shapes for Part 5 (embeddings/Qdrant).

Absolute workspace paths never appear here — only repository-relative paths.
"""

from pydantic import BaseModel, Field


class IngestedChunk(BaseModel):
    repository_id: str
    commit_sha: str | None = None
    # Part 1: snapshot that produced this chunk (None = pre-snapshot data).
    snapshot_id: str | None = None
    file_path: str
    file_hash: str
    language: str
    chunk_type: str
    symbol: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    content_hash: str


class SkippedFile(BaseModel):
    file_path: str
    category: str
    reason: str


class IngestionResult(BaseModel):
    repository_id: str
    commit_sha: str | None = None
    files_processed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    chunks: list[IngestedChunk] = Field(default_factory=list)
    skipped: list[SkippedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
