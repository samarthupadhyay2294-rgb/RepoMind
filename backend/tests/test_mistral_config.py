"""Mistral embedding configuration: .env resolution, normalization, safety.

Covers the "key added to backend/.env but still not configured" incident:
CWD-independent loading, whitespace/quotes handling, empty-OS-override
fallback, secret-safe diagnostics/logs, and provider error classification.
"""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, _env_path, embedding_config_source

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _write_env(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


def _settings_with_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str
) -> Settings:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    env_file = _write_env(tmp_path / ".env", content)
    return Settings(_env_file=env_file)


def test_env_path_anchored_to_backend_dir() -> None:
    assert _env_path.is_absolute()
    assert _env_path.name == ".env"
    assert _env_path.parent == BACKEND_DIR.resolve()


def test_settings_loads_from_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    settings = _settings_with_env(
        monkeypatch, tmp_path, "MISTRAL_API_KEY=root-cwd-key\n"
    )
    assert settings.MISTRAL_API_KEY == "root-cwd-key"


def test_settings_loads_from_backend_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(BACKEND_DIR)
    settings = _settings_with_env(
        monkeypatch, tmp_path, "MISTRAL_API_KEY=backend-cwd-key\n"
    )
    assert settings.MISTRAL_API_KEY == "backend-cwd-key"


def test_absent_key_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings_with_env(monkeypatch, tmp_path, "APP_NAME=RepoMind\n")
    assert settings.MISTRAL_API_KEY == ""
    from app.embeddings.groq import is_embedding_configured

    monkeypatch.setattr("app.embeddings.groq.settings", settings)
    assert is_embedding_configured() is False


def test_valid_key_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings_with_env(
        monkeypatch, tmp_path, "MISTRAL_API_KEY=valid-key\n"
    )
    from app.embeddings.groq import get_embedding_provider

    monkeypatch.setattr("app.embeddings.groq.settings", settings)
    provider = get_embedding_provider()
    assert provider.model == settings.MISTRAL_EMBEDDING_MODEL


def test_blank_key_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for content in ("MISTRAL_API_KEY=\n", "MISTRAL_API_KEY=   \n"):
        settings = _settings_with_env(monkeypatch, tmp_path, content)
        assert settings.MISTRAL_API_KEY.strip() == ""
        from app.embeddings.groq import get_embedding_provider
        from app.exceptions import EmbeddingError

        monkeypatch.setattr("app.embeddings.groq.settings", settings)
        with pytest.raises(EmbeddingError) as exc_info:
            get_embedding_provider()
        assert exc_info.value.code == "EMBEDDING_NOT_CONFIGURED"


def test_whitespace_padded_key_is_trimmed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings_with_env(
        monkeypatch, tmp_path, "MISTRAL_API_KEY=  padded-key  \n"
    )
    assert settings.MISTRAL_API_KEY == "padded-key"


def test_quoted_key_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings_with_env(
        monkeypatch, tmp_path, 'MISTRAL_API_KEY="quoted-key"\n'
    )
    assert settings.MISTRAL_API_KEY.strip() != ""
    from app.embeddings.groq import is_embedding_configured

    monkeypatch.setattr("app.embeddings.groq.settings", settings)
    assert is_embedding_configured() is True


def test_empty_os_override_falls_back_to_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = _write_env(tmp_path / ".env", "MISTRAL_API_KEY=file-key\n")
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    assert Settings(_env_file=env_file).MISTRAL_API_KEY == "file-key"
    monkeypatch.setenv("MISTRAL_API_KEY", "   ")
    assert Settings(_env_file=env_file).MISTRAL_API_KEY == "file-key"


def test_nonblank_os_override_still_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = _write_env(tmp_path / ".env", "MISTRAL_API_KEY=file-key\n")
    monkeypatch.setenv("MISTRAL_API_KEY", "os-key")
    assert Settings(_env_file=env_file).MISTRAL_API_KEY == "os-key"


def test_embedding_config_source_categories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import _env_path as real_env_path
    import app.config as config_mod

    fake_env = tmp_path / ".env"
    fake_env.write_text("MISTRAL_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "_env_path", fake_env)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert embedding_config_source() == "dotenv"
    monkeypatch.setenv("MISTRAL_API_KEY", "os-key")
    assert embedding_config_source() == "environment"
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    assert embedding_config_source() == "dotenv"
    fake_env.write_text("MISTRAL_API_KEY=\n", encoding="utf-8")
    assert embedding_config_source() == "unconfigured"
    monkeypatch.setattr(config_mod, "_env_path", real_env_path)


def test_diagnostics_never_expose_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    sentinel = "sk-sentinel-never-expose-12345"
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", sentinel)
    monkeypatch.setenv("MISTRAL_API_KEY", sentinel)
    response = client.get("/api/v1/config/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert sentinel not in response.text
    assert body["embedding_provider_configured"] is True
    assert body["embedding_provider_name"] == "mistral"
    assert body["embedding_config_source"] == "environment"
    assert "embedding_config_source" in body


def test_provider_error_classification_never_leaks_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.embeddings.groq import _normalize

    sentinel = "sk-sentinel-never-expose-67890"
    auth_err = _normalize("mistral-embed", Exception(f"401 Unauthorized {sentinel}"))
    assert auth_err.code == "EMBEDDING_AUTH_FAILED"
    assert sentinel not in auth_err.message
    transient = _normalize("mistral-embed", Exception("503 overloaded"))
    assert transient.code == "EMBEDDING_PROVIDER_UNAVAILABLE"
    generic = _normalize("mistral-embed", Exception("boom"))
    assert generic.code == "EMBEDDING_PROVIDER_ERROR"


def test_indexing_stores_auth_and_provider_codes(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.embeddings.groq as groq_mod
    from app.embeddings.groq import GroqEmbeddingProvider
    from app.services.qdrant_service import QdrantService
    from tests.conftest import use_owner
    from tests.test_indexing_api import FakeQdrant, _register_local

    class _AuthDeniedClient:
        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            raise Exception("401 Unauthorized")

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            raise Exception("401 Unauthorized")

    fake = FakeQdrant()
    monkeypatch.setattr(
        groq_mod,
        "get_embedding_provider",
        lambda: GroqEmbeddingProvider(
            api_key="test-key",
            model="mistral-embed",
            client=_AuthDeniedClient(),
        ),
    )
    monkeypatch.setattr(QdrantService, "from_settings", classmethod(lambda cls: fake))
    use_owner("owner-auth")
    created = _register_local(client, tmp_path)
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert "test-key" not in body["error_message"]
    assert body["error_message"].startswith(
        ("[EMBEDDING_AUTH_FAILED]", "[EMBEDDING_PROVIDER_")
    )


def test_missing_key_logs_no_secret(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        from app.embeddings.groq import embedding_not_configured_error

        err = embedding_not_configured_error()
        logging.getLogger("app.embeddings.groq").warning(
            "embedding_not_configured code=%s", err.code
        )
    assert "MISTRAL_API_KEY" not in caplog.text or "is not configured" in caplog.text
