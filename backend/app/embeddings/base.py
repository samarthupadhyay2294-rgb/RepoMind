"""Embedding provider abstraction (Part 5).

Application code depends on :class:`EmbeddingProvider`; provider-specific
clients stay in ``app/embeddings/groq.py`` so the embedding backend can
be replaced without touching RAG logic.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunk texts. Order of outputs matches inputs."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single retrieval query."""
        ...
