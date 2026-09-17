"""Embedding configuration gate for indexing (no network access).

Missing MISTRAL_API_KEY must fail fast with an actionable message before
any ingestion, snapshot, or Qdrant work — never as a late failure after
partial work. Error text and logs must never carry the key value.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.embeddings.groq import (
    embedding_not_configured_error,
    get_embedding_provider,
)
from app.exceptions import EmbeddingError
from tests.conftest import use_owner
from tests.test_indexing_api import _register_local


def test_missing_key_fails_before_any_pipeline_work(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.ingestion as ingestion_mod

    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")

    def _must_not_run(repository):  # type: ignore[no-untyped-def]
        raise AssertionError("ingestion must not run without embedding config")

    monkeypatch.setattr(ingestion_mod, "ingest_repository", _must_not_run)
    use_owner("owner-A")
    created = _register_local(client, tmp_path)
    response = client.post(f"/api/v1/repositories/{created['id']}/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert (body["error_message"] or "").startswith("[EMBEDDING_NOT_CONFIGURED]")
    assert "MISTRAL_API_KEY is not configured" in (body["error_message"] or "")
    assert "backend/.env" in (body["error_message"] or "")


def test_missing_key_error_carries_actionable_code_and_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "  ")
    with pytest.raises(EmbeddingError) as exc_info:
        get_embedding_provider()
    assert exc_info.value.code == "EMBEDDING_NOT_CONFIGURED"
    assert "backend/.env" in exc_info.value.message


def test_config_error_never_contains_key_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sk-test-sentinel-never-log-me"
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", sentinel)
    err = embedding_not_configured_error()
    assert sentinel not in err.message
    assert sentinel not in repr(err)
