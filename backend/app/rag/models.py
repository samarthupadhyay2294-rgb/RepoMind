"""Part 5 RAG contracts: indexing stats and retrieval evidence.

Chunk identity/content still comes from Part 4 (``app.ingestion.models``);
these models only describe what indexing and retrieval produce.
"""

from pydantic import BaseModel, Field


class IndexingResult(BaseModel):
    repository_id: str
    commit_sha: str | None = None
    files_processed: int = 0
    chunks_seen: int = 0
    chunks_indexed: int = 0
    chunks_skipped: int = 0
    chunks_failed: int = 0
    embeddings_generated: int = 0
    embedding_batches: int = 0
    stale_points_removed: int = 0


class RetrievalResult(BaseModel):
    content: str
    score: float
    repository_id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    language: str = ""
    symbol: str | None = None
    chunk_type: str = ""
    commit_sha: str | None = None
    content_hash: str = ""
    # Part 1 snapshot isolation (additive; None = pre-snapshot legacy point).
    snapshot_id: str | None = None

    @property
    def citation(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"
