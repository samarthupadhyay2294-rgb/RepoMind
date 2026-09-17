"""Centralized environment configuration (load + validate only)."""

import os
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources import EnvSettingsSource

# Absolute path anchored to this module, so backend/.env loads identically
# whether Uvicorn starts from the repository root or the backend directory.
_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_path, env_file_encoding="utf-8", extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Blank OS variables (empty/whitespace-only) are treated as unset so a
        # value in backend/.env still applies. Without this, an empty OS-level
        # MISTRAL_API_KEY silently overrides a valid .env entry and the app
        # reports "not configured" despite the file looking correct.
        class _NonBlankEnvSource(EnvSettingsSource):
            def __call__(self) -> dict[str, object]:
                data = super().__call__()
                filtered: dict[str, object] = {}
                for k, v in data.items():
                    raw_val = (
                        os.environ.get(k)
                        or os.environ.get(k.upper())
                        or os.environ.get(k.lower())
                    )
                    if raw_val is not None and raw_val.strip() == "":
                        continue
                    filtered[k] = v
                return filtered

        return (
            init_settings,
            _NonBlankEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("MISTRAL_API_KEY", mode="before")
    @classmethod
    def _strip_mistral_key(cls, value: object) -> object:
        # Trim accidental surrounding whitespace (e.g. "KEY=  abc  ");
        # interior key content is never altered.
        if isinstance(value, str):
            return value.strip()
        return value

    APP_NAME: str = "RepoMind"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Explicit default chat-provider selection. The default is local Ollama;
    # ambient GROQ_API_KEY presence alone NEVER switches it (credential
    # presence is not provider selection). Groq stays explicit opt-in via
    # LLM_PROVIDER=groq or get_chat_model("groq") / get_support_chat_model().
    LLM_PROVIDER: Literal["ollama", "groq"] = "ollama"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    # Local Ollama (primary chat provider). No key required: empty is valid.
    # OLLAMA_API_KEY is reserved for env-file compatibility only and is
    # never sent anywhere — RepoMind talks to the local server exclusively.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:31b-cloud"
    OLLAMA_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""

    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"
    EMBEDDING_BATCH_SIZE: int = 32
    # Single source of truth for the embedding→Qdrant contract. Must equal
    # the output dimension of MISTRAL_EMBEDDING_MODEL (verified: mistral-embed
    # emits 1024-dimensional vectors). Change only when changing the model —
    # indexing validates every vector against this before any Qdrant write,
    # and ensure_collection enforces it on the collection side. Never pad,
    # truncate, or reshape vectors to fit.
    EMBEDDING_DIMENSION: int = 1024

    LLM_TEMPERATURE: float = 0.0
    # Token-bucket rate limit for LangChain chat-model calls (plan A.4):
    # free-tier quota protection. 0 disables limiting (tests may use this).
    LLM_MAX_REQUESTS_PER_MINUTE: int = 0

    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "repomind"

    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_MAX_TOP_K: int = 20

    # Part 6 investigation-tool limits (centralized; no magic numbers in tools).
    MAX_SEARCH_RESULTS: int = 20
    MAX_SEARCH_QUERY_LENGTH: int = 500
    MAX_READ_FILE_BYTES: int = 200000
    MAX_READ_LINES: int = 500
    MAX_READ_OUTPUT_CHARS: int = 50000
    MAX_DIRECTORY_ENTRIES: int = 200
    MAX_GIT_LOG_ENTRIES: int = 50
    MAX_BLAME_LINES: int = 200
    MAX_REFERENCE_RESULTS: int = 50
    MAX_DEPENDENCY_NODES: int = 200
    MAX_DEPENDENCY_EDGES: int = 500
    MAX_DEPENDENCY_DEPTH: int = 5
    VALIDATION_TIMEOUT_SECONDS: int = 60
    MAX_VALIDATION_OUTPUT_BYTES: int = 100000
    # Plan v2: run_validation is high-risk surface → disabled unless
    # explicitly allowlisted per deployment (risk A.4, tool table §10).
    ENABLED_VALIDATIONS: str = ""

    # Part 7 agent bounds (centralized; the graph enforces them in code).
    AGENT_MAX_STEPS: int = 8
    AGENT_MAX_TOOL_CALLS: int = 10
    AGENT_MAX_EVIDENCE_ITEMS: int = 20
    AGENT_MAX_EVIDENCE_CHARS: int = 50000
    AGENT_MAX_TOOL_OUTPUT_CHARS: int = 20000
    AGENT_TOKEN_BUDGET: int = 60000
    MAX_QUESTION_LENGTH: int = 4000

    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    DEV_OWNER_ID: str = "local-dev-owner"

    REPOSITORY_STORAGE_PATH: str = "./data/repositories"

    # Git acquisition bounds (Gap #1): bounded clone, post-clone size cap.
    # Git cannot enforce transfer size natively — the size cap is checked
    # after clone and oversized workspaces are rejected before ingestion.
    REPOSITORY_CLONE_TIMEOUT_SECONDS: int = 120
    MAX_REPOSITORY_BYTES: int = 524288000

    MAX_FILE_SIZE_BYTES: int = 524288
    MAX_FILES_PER_REPOSITORY: int = 5000
    MAX_CHUNK_SIZE: int = 8000
    MAX_CHUNK_LINES: int = 120

    LANGGRAPH_CHECKPOINT_BACKEND: str = "postgres"
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""

    # Part 1 (shared foundation) feature flags. Rollout is opt-in:
    # unfinished user-facing features stay off; agent improvements
    # default on because the JSON-plan path already implements them.
    AGENT_SELECTABLE_RETRIEVAL: bool = True
    STRUCTURED_TOOL_ARGS: bool = True
    SNAPSHOT_INDEXING: bool = True
    # Future user-facing features (later parts; never auto-activated).
    ARCHITECTURE_OVERVIEW: bool = True
    DEPENDENCY_GRAPH: bool = True
    DEBUG_INVESTIGATOR: bool = False

    # Part 2 graph bounds + flags (server-side enforced maximums).
    GRAPH_MAX_DEPTH: int = 3
    GRAPH_MAX_NODES: int = 100
    GRAPH_MAX_EDGES: int = 200
    GRAPH_HARD_MAX_DEPTH: int = 5
    GRAPH_HARD_MAX_NODES: int = 300
    GRAPH_HARD_MAX_EDGES: int = 600
    GRAPH_ENABLE_INFERRED_RELATIONSHIPS: bool = False

    # Part 3 overview bounds (server-side enforced maximums).
    OVERVIEW_MAX_EVIDENCE_ITEMS: int = 24
    OVERVIEW_MAX_EXCERPT_CHARS: int = 1500
    OVERVIEW_MAX_PROMPT_CHARS: int = 24000
    OVERVIEW_LLM_TIMEOUT_SECONDS: int = 180


def embedding_config_source() -> str:
    """Report where the embedding key came from without exposing any secret.

    Returns one of "environment" (non-blank OS variable), "dotenv"
    (non-blank entry in backend/.env), or "unconfigured".
    """
    if os.environ.get("MISTRAL_API_KEY", "").strip():
        return "environment"
    try:
        last = ""
        for line in _env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() == "MISTRAL_API_KEY":
                last = value.strip().strip("'\"").strip()
        if last:
            return "dotenv"
    except OSError:
        pass
    return "unconfigured"


settings = Settings()
