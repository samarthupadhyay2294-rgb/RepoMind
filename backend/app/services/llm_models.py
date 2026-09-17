"""LLM provider layer — the only place that builds LangChain chat models.

Application code must use ``get_chat_model`` / ``get_primary_chat_model`` /
``get_support_chat_model`` instead of constructing provider clients directly,
so provider/model changes never leak into agent logic.

Active primary provider: local Ollama (``OLLAMA_BASE_URL`` /
``OLLAMA_MODEL``, default ``http://localhost:11434`` /
``gemma4:31b-cloud``). RepoMind only talks to the user's locally running
Ollama server: no API key is required, no cloud endpoint is configured,
and RepoMind never runs ``ollama pull`` / ``ollama serve`` / ``ollama run``
— the user manages Ollama separately.
"""

import logging
import threading
import time
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from app.config import settings
from app.exceptions import AppError

logger = logging.getLogger(__name__)

ProviderName = Literal["groq", "ollama"]


class LLMError(AppError):
    pass


class LLMConfigurationError(LLMError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_NOT_CONFIGURED", status_code=500)


class LLMProviderError(LLMError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_PROVIDER_ERROR", status_code=502)


class LLMUnavailableError(LLMProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "LLM_UNAVAILABLE"
        self.status_code = 503


_TRANSIENT_MARKERS = (
    "temporarily",
    "unavailable",
    "overloaded",
    "timeout",
    "timed out",
    "rate limit",
    "429",
    "503",
)

# Ollama-local failure classification (connection / timeout / model).
_CONNECTION_MARKERS = (
    "connection refused",
    "failed to connect",
    "connecterror",
    "connectionerror",
    "not reachable",
    "all connection attempts failed",
    "name or service not known",
    "nodename nor servname",
    "errno 111",
    "errno 61",
    "connection aborted",
    "server unavailable",
)

_TIMEOUT_MARKERS = (
    "timeout",
    "timed out",
    "readtimeout",
    "connecttimeout",
    "deadline exceeded",
)

_MODEL_MISSING_MARKERS = (
    "not found",
    "does not exist",
    "doesn't exist",
    "no such model",
    "not exist",
    "not downloaded",
    "not available",
    "try pulling",
    "ollama pull",
    "404",
)


def is_groq_configured() -> bool:
    return bool(settings.GROQ_API_KEY.strip())


def is_ollama_configured() -> bool:
    """Local Ollama counts as configured when base URL + model are set.

    No API key is required: an empty/missing ``OLLAMA_API_KEY`` is valid
    for the local server.
    """
    return bool(
        settings.OLLAMA_BASE_URL.strip() and settings.OLLAMA_MODEL.strip()
    )


def get_chat_model(provider: ProviderName) -> BaseChatModel:
    if provider == "ollama":
        return get_primary_chat_model()
    if provider == "groq":
        return get_support_chat_model()
    raise LLMConfigurationError(
        f"Unknown LLM provider: {provider!r}. Expected 'ollama' or 'groq'."
    )


def default_provider() -> ProviderName:
    """Explicit default provider from ``LLM_PROVIDER`` (default ``"ollama"``).

    Credential presence is never provider selection: an ambient
    ``GROQ_API_KEY`` alone keeps the default on Ollama. Only an explicit
    ``LLM_PROVIDER=groq`` selects Groq as the default.
    """
    return settings.LLM_PROVIDER


def get_default_chat_model() -> BaseChatModel:
    """Chat model for the explicitly configured default provider."""
    return get_chat_model(default_provider())


def get_primary_chat_model() -> BaseChatModel:
    """Primary (local Ollama) reasoning model. Required for normal operation.

    Connects only to the locally running Ollama server at
    ``OLLAMA_BASE_URL`` using ``OLLAMA_MODEL`` (default
    ``gemma4:31b-cloud``). No API key is needed or sent. The client is
    built with ``validate_model_on_init=False`` so constructing it never
    touches the network (and never pulls/serves/runs models) — failures
    surface at generation time as actionable :class:`LLMError`s.
    """
    if not is_ollama_configured():
        raise LLMConfigurationError(
            "OLLAMA_BASE_URL / OLLAMA_MODEL is not configured. Set "
            "OLLAMA_BASE_URL=http://localhost:11434 and "
            "OLLAMA_MODEL=gemma4:31b-cloud, then start Ollama separately."
        )
    try:
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            validate_model_on_init=False,
        )
    except Exception as exc:
        raise _normalize_ollama(
            settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL, exc
        ) from exc


def get_support_chat_model() -> BaseChatModel:
    """Optional (Groq) supporting model. Never an automatic fallback.

    The agent's active path (:func:`get_primary_chat_model` via
    ``app/agent/service.py``) uses only local Ollama; Groq is only used
    when explicitly requested via ``get_chat_model("groq")``.
    """
    if not is_groq_configured():
        raise LLMConfigurationError(
            "GROQ_API_KEY is not configured; the optional support model "
            "is unavailable."
        )
    try:
        return ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.GROQ_API_KEY,
        )
    except Exception as exc:
        raise _normalize("groq", settings.GROQ_MODEL, exc) from exc


def is_ollama_model(model: BaseChatModel) -> bool:
    """True when ``model`` is the local-Ollama chat client."""
    return isinstance(model, ChatOllama)


def invoke_chat_model(model: BaseChatModel, prompt: str) -> str:
    """Invoke a provider model, normalizing failures to :class:`LLMError`."""
    model_name = str(getattr(model, "model", "unknown"))
    _rate_limiter().acquire()
    try:
        content = model.invoke(prompt).content
    except LLMError:
        raise
    except Exception as exc:
        if is_ollama_model(model):
            raise _normalize_ollama(
                settings.OLLAMA_BASE_URL,
                model_name if model_name != "unknown" else settings.OLLAMA_MODEL,
                exc,
            ) from exc
        raise _normalize(type(model).__name__, model_name, exc) from exc
    return content if isinstance(content, str) else str(content)


class _TokenBucket:
    """Thread-safe token bucket: free-tier quota protection (plan A.4)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Start full so normal usage is never throttled up front.
        self._tokens = float(max(0, settings.LLM_MAX_REQUESTS_PER_MINUTE))
        self._updated = time.monotonic()

    def acquire(self) -> None:
        limit = max(0, settings.LLM_MAX_REQUESTS_PER_MINUTE)
        if limit == 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    float(limit),
                    self._tokens + (now - self._updated) * (limit / 60.0),
                )
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) * (60.0 / limit)
            time.sleep(min(wait, 5.0))


_rate_limiter_state = _TokenBucket()


def _rate_limiter() -> _TokenBucket:
    return _rate_limiter_state


def reset_rate_limiter() -> None:
    """Restore a full bucket (tests; also usable after quota windows)."""
    global _rate_limiter_state
    _rate_limiter_state = _TokenBucket()


def _normalize_ollama(base_url: str, model_name: str, exc: Exception) -> LLMError:
    """Map an Ollama failure to an actionable :class:`LLMError`.

    Messages tell the user what to do (start Ollama, check the model)
    without running any ``ollama`` commands on their behalf.
    """
    # Log category only: never prompts, responses, keys, or raw payloads.
    logger.warning(
        "LLM call failed provider=ollama model=%s base_url=%s error=%s",
        model_name,
        base_url,
        type(exc).__name__,
    )
    text = f"{type(exc).__name__} {exc}".lower()
    if any(marker in text for marker in _TIMEOUT_MARKERS):
        return LLMUnavailableError(
            f"Ollama request timed out at {base_url} for model {model_name}. "
            "Check that your local Ollama server is running and responsive, "
            "then retry."
        )
    if ("model" in text or "404" in text) and any(
        marker in text for marker in _MODEL_MISSING_MARKERS
    ):
        return LLMProviderError(
            f"Ollama model {model_name} is unavailable. Ensure the model is "
            f"available in your local Ollama at {base_url} (you manage "
            "Ollama separately — RepoMind never runs `ollama pull`)."
        )
    if any(marker in text for marker in _CONNECTION_MARKERS):
        return LLMUnavailableError(
            f"Ollama is not reachable at {base_url}. Start Ollama separately "
            f"(it must already be running) and ensure model {model_name} is "
            "available, then retry."
        )
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return LLMUnavailableError(
            f"Ollama model {model_name} is temporarily unavailable at "
            f"{base_url}. Verify your local Ollama server is running, then "
            "retry."
        )
    return LLMProviderError(
        f"Ollama generation failed with model {model_name} at {base_url} "
        f"({type(exc).__name__}). Verify your local Ollama server is "
        "running and the model is available, then retry."
    )


def _normalize(provider: str, model_name: str, exc: Exception) -> LLMError:
    # Log category only: never prompts, responses, keys, or raw payloads.
    logger.warning(
        "LLM call failed provider=%s model=%s error=%s",
        provider,
        model_name,
        type(exc).__name__,
    )
    if any(marker in str(exc).lower() for marker in _TRANSIENT_MARKERS):
        return LLMUnavailableError(
            f"{provider} model {model_name} is temporarily unavailable."
        )
    return LLMProviderError(f"{provider} model {model_name} request failed.")
