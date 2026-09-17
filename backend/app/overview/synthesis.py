"""LLM synthesis for overviews (Part 3).

Uses the existing LLM factory only (local Ollama primary, no API key).
Parses strict JSON, schema-validates into StructuredOverview, and fails
safely on malformed output. No chat-loop or agent coupling.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.overview.schemas import StructuredOverview
from app.services import llm_models

logger = logging.getLogger(__name__)


class OverviewSynthesisError(Exception):
    """LLM output unusable (unreachable model, malformed JSON, bad schema)."""

    def __init__(self, message: str, *, code: str = "OVERVIEW_SYNTHESIS_FAILED"):
        super().__init__(message)
        self.code = code


def _extract_json(text: str) -> Any:
    cleaned = (text or "").strip()
    if not cleaned:
        raise OverviewSynthesisError("LLM returned empty output.")
    # Tolerate code fences without trusting surrounding prose.
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError) as exc:
        # Last resort: outermost braces.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except (ValueError, TypeError):
                pass
        raise OverviewSynthesisError(f"LLM output is not valid JSON: {exc}") from exc


def synthesize(prompt: str, *, model_override: Any = None) -> StructuredOverview:
    """Invoke the LLM and return a schema-validated StructuredOverview."""
    model = model_override if model_override is not None else _primary_model()
    try:
        if model_override is not None and isinstance(model_override, str):
            raw = model_override
        else:
            raw = llm_models.invoke_chat_model(model, prompt)
    except Exception as exc:
        raise OverviewSynthesisError(
            f"LLM generation failed: {type(exc).__name__}."
        ) from exc
    data = _extract_json(raw if isinstance(raw, str) else str(raw))
    if not isinstance(data, dict):
        raise OverviewSynthesisError("LLM output must be a JSON object.")
    try:
        overview = StructuredOverview(**data)
    except ValidationError as exc:
        raise OverviewSynthesisError(
            f"LLM output failed schema validation: {exc.errors()[0]['loc'] if exc.errors() else 'unknown'}."
        ) from exc
    logger.info(
        "overview_synthesized components=%d entry_points=%d",
        len(overview.components),
        len(overview.entry_points),
    )
    return overview


def _primary_model() -> Any:
    return llm_models.get_primary_chat_model()


def generation_model_name() -> str:
    return settings.OLLAMA_MODEL
