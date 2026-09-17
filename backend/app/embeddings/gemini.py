"""Gemini hosted embeddings behind the :class:`EmbeddingProvider` protocol.

Only place allowed to build ``GoogleGenerativeAIEmbeddings``. Batching and
bounded retries live here so RAG code never issues one request per chunk.
"""

import asyncio
import logging
from typing import Any

from pydantic import SecretStr

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

_TRANSIENT_MARKERS = (
    "temporarily",
    "unavailable",
    "overloaded",
    "timeout",
    "timed out",
    "rate limit",
    "429",
    "503",
    "resourceexhausted",
)

_MAX_ATTEMPTS = 3


def is_embedding_configured() -> bool:
    # Keep using Gemini API key for embeddings since it's still configured
    return bool(settings.GEMINI_API_KEY.strip())


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured (Gemini) embedding provider."""
    if not is_embedding_configured():
        raise EmbeddingError("GEMINI_API_KEY is not configured.")
    return GeminiEmbeddingProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )


class GeminiEmbeddingProvider:
    """Hosted Gemini embeddings with configurable batching + bounded retry."""

    def __init__(
        self,
        api_key: str,
        model: str,
        batch_size: int = 32,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingError("GEMINI_API_KEY is not configured.")
        self._model = model
        self._batch_size = max(1, batch_size)
        if client is not None:
            self._client = client
        else:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            try:
                self._client = GoogleGenerativeAIEmbeddings(
                    model=model, google_api_key=SecretStr(api_key)
                )
            except Exception as exc:
                raise EmbeddingError(
                    f"Could not initialize Gemini embeddings model {model}."
                ) from exc

    @property
    def model(self) -> str:
        return self._model

    @property
    def batch_size(self) -> int:
        return self._batch_size

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        batches = 0
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            vectors = await self._with_retry(
                lambda b=batch: self._client.embed_documents(b)
            )
            if len(vectors) != len(batch):
                raise EmbeddingError(
                    f"Embedding batch returned {len(vectors)} vectors "
                    f"for {len(batch)} texts."
                )
            out.extend([list(map(float, v)) for v in vectors])
            batches += 1
        logger.info(
            "embeddings_generated count=%d batches=%d model=%s",
            len(texts),
            batches,
            self._model,
        )
        return out

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("Cannot embed an empty query.")
        vector = await self._with_retry(lambda: self._client.embed_query(text))
        return list(map(float, vector))

    async def _with_retry(self, call: Any) -> Any:
        last: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(call)
            except EmbeddingError:
                raise
            except Exception as exc:
                last = exc
                # Log category only: never chunk text, keys, or payloads.
                logger.warning(
                    "embedding_attempt_failed attempt=%d model=%s error=%s",
                    attempt,
                    self._model,
                    type(exc).__name__,
                )
                if not _is_transient(exc) or attempt == _MAX_ATTEMPTS:
                    raise _normalize(self._model, exc) from exc
                await asyncio.sleep(2.0 ** (attempt - 1))
        assert last is not None  # unreachable; keeps mypy happy
        raise _normalize(self._model, last)


def _is_transient(exc: Exception) -> bool:
    return any(marker in str(exc).lower() for marker in _TRANSIENT_MARKERS)


def _normalize(model: str, exc: Exception) -> EmbeddingError:
    if _is_transient(exc):
        return EmbeddingError(
            f"Gemini embeddings model {model} is temporarily unavailable."
        )
    return EmbeddingError(f"Gemini embeddings model {model} request failed.")


def batch_texts(texts: list[str], batch_size: int) -> list[list[str]]:
    """Split texts into bounded batches (helper for tests/callers)."""
    size = max(1, batch_size)
    return [texts[i : i + size] for i in range(0, len(texts), size)]
