"""Test .env loading from different working directories."""

from pathlib import Path

import pytest

from app.config import Settings


def test_env_path_resolution():
    """Test that .env path is resolved relative to config module."""
    from app.config import _env_path
    
    # The env path should be backend/.env relative to the config module
    assert _env_path.name == ".env"
    assert _env_path.parent.name == "backend"


def test_env_path_is_absolute():
    """Test that .env path is absolute for reliable loading."""
    from app.config import _env_path
    
    # The env path should be absolute
    assert _env_path.is_absolute()


def test_settings_has_default_values():
    """Test that Settings has expected default values."""
    settings = Settings()
    
    # Check that required fields have defaults
    assert settings.APP_NAME == "RepoMind"
    assert settings.APP_ENV == "development"
    assert settings.DEBUG == True
    assert settings.LOG_LEVEL == "INFO"
    assert settings.LLM_PROVIDER == "ollama"
    assert settings.MISTRAL_EMBEDDING_MODEL == "mistral-embed"
    assert settings.EMBEDDING_DIMENSION == 1024


def test_os_env_override_takes_precedence():
    """Test that OS env override takes precedence over .env."""
    import os
    from unittest.mock import patch
    
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "os_env_key"}):
        settings = Settings()
        assert settings.MISTRAL_API_KEY == "os_env_key"


def test_empty_os_env_override_ignored_and_falls_back():
    """Test that empty OS env vars (e.g. ARCHITECTURE_OVERVIEW='') fall back to .env value."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"ARCHITECTURE_OVERVIEW": ""}):
        settings = Settings()
        assert settings.ARCHITECTURE_OVERVIEW is True


def test_explicit_false_os_env_override():
    """Test that explicit ARCHITECTURE_OVERVIEW=false in OS env overrides .env."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"ARCHITECTURE_OVERVIEW": "false"}):
        settings = Settings()
        assert settings.ARCHITECTURE_OVERVIEW is False

