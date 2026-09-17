"""Unit tests for the local-Ollama LLM provider layer.

No network access: every test is mocked. Covers local configuration
(empty API key valid), client construction (base URL + model, no auth,
no network validation), actionable Ollama error mapping, mocked
generation, and LangGraph agent integration through the plain string
``invoke_llm`` interface Ollama serves.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import compile_graph
from app.agent.nodes import AgentDeps
from app.agent.state import initial_state
from app.config import Settings, settings
from app.services import llm_models
from app.services.llm_models import (
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMUnavailableError,
    _normalize_ollama,
    default_provider,
    get_chat_model,
    get_default_chat_model,
    get_primary_chat_model,
    get_support_chat_model,
    invoke_chat_model,
    is_groq_configured,
    is_ollama_configured,
    is_ollama_model,
)

# Mock ChatGroq for tests (Groq is explicit opt-in support only).
class MockChatGroq:
    pass


llm_models.ChatGroq = MockChatGroq

BASE_URL = "http://localhost:11434"
MODEL = "gemma4:31b-cloud"


def _ollama_mock(**kwargs):
    """A ChatOllama stand-in that passes ``is_ollama_model`` (spec'd)."""
    mock = MagicMock(spec=ChatOllama)
    mock.model = MODEL
    for key, value in kwargs.items():
        setattr(mock, key, value)
    return mock


# -- local configuration --------------------------------------------------


def test_ollama_defaults_are_local() -> None:
    fresh = Settings()
    assert fresh.OLLAMA_BASE_URL == "http://localhost:11434"
    assert fresh.OLLAMA_MODEL == "gemma4:31b-cloud"
    assert fresh.OLLAMA_API_KEY == ""


def test_model_ids_loaded_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hermetic: fresh Settings() must reflect code defaults, not whatever
    # happens to live in the developer's ambient OS environment or .env
    # file (pydantic-settings reads backend/.env by default).
    for var in ("GROQ_MODEL", "OLLAMA_MODEL", "LLM_PROVIDER", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    configured = Settings(
        _env_file=empty_env, GROQ_MODEL="custom-groq", OLLAMA_MODEL="custom-ollama"
    )
    assert configured.GROQ_MODEL == "custom-groq"
    assert configured.OLLAMA_MODEL == "custom-ollama"
    fresh = Settings(_env_file=empty_env)
    assert fresh.GROQ_MODEL == "llama-3.1-8b-instant"
    assert fresh.OLLAMA_MODEL == "gemma4:31b-cloud"
    assert fresh.LLM_PROVIDER == "ollama"


def test_empty_api_key_is_valid_for_local_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "")
    assert is_ollama_configured()
    with patch.object(llm_models, "ChatOllama") as factory:
        model = get_primary_chat_model()
    assert model is factory.return_value


def test_missing_api_key_attr_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "   ")
    assert is_ollama_configured()


def test_ollama_construction_uses_base_url_and_model_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "")
    with patch.object(llm_models, "ChatOllama") as factory:
        model = get_chat_model("ollama")
    factory.assert_called_once_with(
        model=MODEL,
        base_url=BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        validate_model_on_init=False,
    )
    assert model is factory.return_value
    call_kwargs = factory.call_args.kwargs
    assert "api_key" not in call_kwargs
    assert "client_kwargs" not in call_kwargs


def test_ollama_key_never_sent_even_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local-only: a stray key must not leak into client auth headers."""
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "stray-key")
    with patch.object(llm_models, "ChatOllama") as factory:
        get_primary_chat_model()
    call_kwargs = factory.call_args.kwargs
    assert "stray-key" not in str(call_kwargs)


def test_primary_provider_is_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "")
    with patch.object(llm_models, "ChatOllama") as factory:
        assert get_primary_chat_model() is factory.return_value


def test_is_ollama_model() -> None:
    assert is_ollama_model(_ollama_mock())
    assert not is_ollama_model(MagicMock())


# -- no hidden fallback ----------------------------------------------------


def test_support_provider_is_groq_explicit_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    with patch.object(llm_models, "ChatGroq") as factory:
        assert get_support_chat_model() is factory.return_value
        assert get_chat_model("groq") is factory.return_value


def test_missing_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        get_support_chat_model()
    assert not is_groq_configured()


def test_missing_ollama_config_no_silent_groq_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    with pytest.raises(LLMConfigurationError, match="OLLAMA"):
        get_primary_chat_model()
    assert not is_ollama_configured()


def test_missing_ollama_model_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "  ")
    with pytest.raises(LLMConfigurationError, match="OLLAMA"):
        get_primary_chat_model()
    assert not is_ollama_configured()


def test_invalid_provider() -> None:
    with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
        get_chat_model("gemini")  # type: ignore[arg-type]
    with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
        get_chat_model("mistral")  # type: ignore[arg-type]


# -- actionable Ollama errors (no server needed) ----------------------------


def test_ollama_server_unavailable_actionable() -> None:
    err = _normalize_ollama(
        BASE_URL, MODEL, ConnectionError("connection refused")
    )
    assert isinstance(err, LLMUnavailableError)
    assert f"Ollama is not reachable at {BASE_URL}" in err.message


def test_ollama_connect_error_class_actionable() -> None:
    class ConnectError(Exception):
        pass

    ConnectError.__name__ = "ConnectError"
    err = _normalize_ollama(BASE_URL, MODEL, ConnectError("All connection attempts failed"))
    assert isinstance(err, LLMUnavailableError)
    assert "not reachable" in err.message


def test_ollama_timeout_actionable() -> None:
    err = _normalize_ollama(BASE_URL, MODEL, TimeoutError("request timed out"))
    assert isinstance(err, LLMUnavailableError)
    assert "timed out" in err.message
    assert BASE_URL in err.message


def test_ollama_model_unavailable_actionable() -> None:
    err = _normalize_ollama(
        BASE_URL, MODEL, RuntimeError(f"model '{MODEL}' not found, try pulling it")
    )
    assert isinstance(err, LLMProviderError)
    assert f"Ollama model {MODEL} is unavailable" in err.message


def test_ollama_generation_failure_actionable() -> None:
    err = _normalize_ollama(BASE_URL, MODEL, RuntimeError("provider exploded"))
    assert isinstance(err, LLMProviderError)
    assert "Ollama generation failed" in err.message
    assert MODEL in err.message
    assert BASE_URL in err.message


def test_invoke_connection_refused_is_actionable() -> None:
    model = _ollama_mock()
    model.invoke.side_effect = ConnectionError("connection refused")
    with pytest.raises(LLMUnavailableError, match="not reachable"):
        invoke_chat_model(model, "hello")


def test_invoke_model_missing_is_actionable() -> None:
    model = _ollama_mock()
    model.invoke.side_effect = RuntimeError("model not found")
    with pytest.raises(LLMProviderError, match="unavailable"):
        invoke_chat_model(model, "hello")


def test_invoke_timeout_is_actionable() -> None:
    model = _ollama_mock()
    model.invoke.side_effect = TimeoutError("read timed out")
    with pytest.raises(LLMUnavailableError, match="timed out"):
        invoke_chat_model(model, "hello")


def test_construction_failure_normalized_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    with (
        patch.object(
            llm_models, "ChatGroq", side_effect=RuntimeError("boom")
        ),
        pytest.raises(LLMProviderError),
    ):
        get_support_chat_model()


# -- successful mocked generation --------------------------------------------


def test_mocked_ollama_generation_returns_text() -> None:
    model = _ollama_mock()
    model.invoke.return_value = AIMessage(content="hello from ollama")
    assert invoke_chat_model(model, "hello") == "hello from ollama"
    model.invoke.assert_called_once_with("hello")


def test_error_hides_api_key() -> None:
    secret = "super-secret-key-abc123"
    model = MagicMock()
    model.invoke.side_effect = RuntimeError(f"auth failed for {secret}")
    with pytest.raises(LLMError) as exc_info:
        invoke_chat_model(model, "hello")
    assert secret not in str(exc_info.value)
    assert secret not in exc_info.value.message


def test_availability_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    assert is_groq_configured()
    assert not is_ollama_configured()


# -- explicit default provider selection (credential presence is not selection)


def test_ambient_groq_key_does_not_change_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambient GROQ_API_KEY must not flip the default provider to Groq."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    assert default_provider() == "ollama"
    with patch.object(llm_models, "ChatOllama") as factory:
        assert get_default_chat_model() is factory.return_value


def test_explicit_groq_provider_selects_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    assert default_provider() == "groq"
    with patch.object(llm_models, "ChatGroq") as factory:
        assert get_default_chat_model() is factory.return_value


def test_explicit_ollama_provider_ignores_groq_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key-no-real-secret")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", BASE_URL)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", MODEL)
    assert default_provider() == "ollama"
    with patch.object(llm_models, "ChatOllama") as factory:
        assert get_default_chat_model() is factory.return_value


def test_default_provider_setting_rejects_unknown_values() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Settings(LLM_PROVIDER="gemini")  # type: ignore[arg-type]


# -- LangGraph agent integration (mocked string LLM, real tools) -------------


class _CannedOllamaLLM:
    """Mimics local Ollama: plain string in/out, JSON plans, no tool API."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        if "classify repository questions" in prompt:
            return json.dumps({"request_type": "bug_investigation", "confidence": 0.9})
        if "plan read-only" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "action": "search_code",
                            "target": "authenticate",
                            "purpose": "find auth code",
                        }
                    ]
                }
            )
        if "judge whether" in prompt:
            return json.dumps(
                {"sufficient": True, "confidence": 0.9, "missing_information": []}
            )
        return "Auth lives in `src/auth.py:4-6`."


def test_agent_runs_end_to_end_on_ollama_string_interface(
    tmp_path: Path,
) -> None:
    """Agent executes plan → real tool → grounded answer via string I/O only."""
    from app.tools.context import make_context

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(
        '"""Auth."""\n\n\ndef authenticate(name):\n    """Log in."""\n    return name == "admin"\n',
        encoding="utf-8",
    )
    llm = _CannedOllamaLLM()

    async def no_hits(repository_id: str, query: str, top_k: int | None = None):
        return []

    deps = AgentDeps(
        invoke_llm=llm,
        retrieve=no_hits,
        tool_context=make_context("repo-a", root),
    )
    final = asyncio.run(
        compile_graph(MemorySaver()).ainvoke(
            initial_state("where is auth?", "repo-a", "thread-ollama"),
            config={"configurable": {"thread_id": "thread-ollama", "deps": deps}},
        )
    )
    # Tool-calling behavior: the JSON plan dispatched a real search_code call.
    tool_names = [r.get("tool_name") for r in final.get("tool_calls", [])]
    assert "search_code" in tool_names
    assert any(
        item.get("tool_name") == "search_code" for item in final.get("evidence", [])
    )
    # Grounded answer with an evidence-backed citation.
    assert final.get("answer")
    assert final.get("citations")
    assert llm.calls  # classify/plan/evaluate/answer all went through Ollama I/O


def test_agent_survives_ollama_generation_failure(
    tmp_path: Path,
) -> None:
    """An Ollama outage degrades to a controlled 503, never a raw traceback."""
    from app.services.llm_models import LLMUnavailableError
    from app.tools.context import make_context

    root = tmp_path / "repo"
    root.mkdir()

    def _down(_prompt: str) -> str:
        raise LLMUnavailableError(
            f"Ollama is not reachable at {BASE_URL}. Start Ollama separately."
        )

    async def no_hits(repository_id: str, query: str, top_k: int | None = None):
        return []

    deps = AgentDeps(
        invoke_llm=_down,
        retrieve=no_hits,
        tool_context=make_context("repo-a", root),
    )
    # Classification failure falls back to 'general'; the fatal answer-step
    # failure must surface as LLMUnavailableError (mapped to HTTP 503).
    with pytest.raises(LLMUnavailableError, match="not reachable"):
        asyncio.run(
            compile_graph(MemorySaver()).ainvoke(
                initial_state("where is auth?", "repo-a", "thread-down"),
                config={"configurable": {"thread_id": "thread-down", "deps": deps}},
            )
        )
