from fastapi import APIRouter

from app.config import embedding_config_source, settings
from app.embeddings.groq import is_embedding_configured

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    # Liveness only — no DB/Qdrant/network checks in Part 1.
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/config/diagnostics")
def config_diagnostics() -> dict[str, str | bool]:
    """Safe configuration diagnostics without exposing secrets."""
    return {
        "embedding_provider_configured": is_embedding_configured(),
        "embedding_provider_name": "mistral",
        "embedding_model": settings.MISTRAL_EMBEDDING_MODEL,
        "embedding_config_source": embedding_config_source(),
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_configured": bool(settings.OLLAMA_BASE_URL),
        "qdrant_configured": bool(settings.QDRANT_URL),
    }
