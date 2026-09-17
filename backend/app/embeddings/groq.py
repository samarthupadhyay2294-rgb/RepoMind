"""Mistral embeddings.

This module provides Mistral embeddings for the RAG system.
Batching and bounded retries live here so RAG code never issues
one request per chunk.
"""

import asyncio
import logging
from typing import Any

from pydantic import SecretStr

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

_AUTH_MARKERS = (
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "forbidden",
    " 401",
    "401 ",
    "(401)",
    "status 401",
)

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


EMBEDDING_SETUP_HINT = (
    "Add MISTRAL_API_KEY to backend/.env and restart the backend, then retry indexing."
)


def is_embedding_configured() -> bool:
    key = settings.MISTRAL_API_KEY.strip()
    return bool(key and key != "")


def embedding_not_configured_error() -> EmbeddingError:
    err = EmbeddingError(f"MISTRAL_API_KEY is not configured. {EMBEDDING_SETUP_HINT}")
    err.code = "EMBEDDING_NOT_CONFIGURED"
    return err


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured (Mistral) embedding provider."""
    api_key = settings.MISTRAL_API_KEY.strip()
    if not api_key:
        raise embedding_not_configured_error()
    return GroqEmbeddingProvider(
        api_key=api_key,
        model=settings.MISTRAL_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )


class GroqEmbeddingProvider:
    """Hosted Mistral embeddings with configurable batching + bounded retry."""

    def __init__(
        self,
        api_key: str,
        model: str,
        batch_size: int = 32,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise embedding_not_configured_error()
        self._model = model
        self._batch_size = max(1, batch_size)
        if client is not None:
            self._client = client
        else:
            from langchain_mistralai import MistralAIEmbeddings

            try:
                self._client = MistralAIEmbeddings(
                    model=model,
                    api_key=SecretStr(api_key),
                )
            except Exception as exc:
                raise EmbeddingError(
                    f"Could not initialize Mistral embeddings model {model}."
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
            out.extend(vectors)
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
        return await self._with_retry(lambda: self._client.embed_query(text))

    async def _with_retry(self, call: Any) -> Any:
        last: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(call)
            except EmbeddingError:
                raise
            except Exception as exc:
                last = exc
                logger.warning(
                    "embedding_attempt_failed attempt=%d model=%s error=%s",
                    attempt,
                    self._model,
                    type(exc).__name__,
                )
                if not _is_transient(exc) or attempt == _MAX_ATTEMPTS:
                    raise _normalize(self._model, exc) from exc
                await asyncio.sleep(2.0 ** (attempt - 1))
        assert last is not None
        raise _normalize(self._model, last)


def _is_transient(exc: Exception) -> bool:
    return any(marker in str(exc).lower() for marker in _TRANSIENT_MARKERS)


def _is_auth_failure(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return any(marker in lowered for marker in _AUTH_MARKERS)


def _normalize(model: str, exc: Exception) -> EmbeddingError:
    if _is_auth_failure(exc):
        err = EmbeddingError(
            f"Mistral embeddings rejected the configured key for model {model} "
            "(authentication failed). Check MISTRAL_API_KEY in backend/.env "
            "and restart the backend, then retry indexing."
        )
        err.code = "EMBEDDING_AUTH_FAILED"
        return err
    if _is_transient(exc):
        err = EmbeddingError(
            f"Mistral embeddings model {model} is temporarily unavailable."
        )
        err.code = "EMBEDDING_PROVIDER_UNAVAILABLE"
        return err
    err = EmbeddingError(f"Mistral embeddings model {model} request failed.")
    err.code = "EMBEDDING_PROVIDER_ERROR"
    return err


def batch_texts(texts: list[str], batch_size: int) -> list[list[str]]:
    """Split texts into bounded batches (helper for tests/callers)."""
    size = max(1, batch_size)
    return [texts[i : i + size] for i in range(0, len(texts), size)]
