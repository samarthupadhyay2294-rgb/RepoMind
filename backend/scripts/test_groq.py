"""Manual Groq connectivity check. Needs a real GROQ_API_KEY.

Run from ``backend/``:  ``python scripts/test_groq.py``
Sends one tiny fixed prompt — never repository data or secrets.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_models import (  # noqa: E402
    LLMError,
    get_chat_model,
    invoke_chat_model,
    is_groq_configured,
)

PROMPT = "Reply with exactly: RepoMind Groq connection successful"


def main() -> int:
    if not is_groq_configured():
        print("GROQ_API_KEY is not configured; skipping live Groq check.")
        return 2
    try:
        text = invoke_chat_model(get_chat_model("groq"), PROMPT)
    except LLMError as exc:
        print(f"Groq connectivity FAILED: {exc.message}")
        return 1
    print("RepoMind Groq connection successful.")
    print(f"Model reply: {text.strip()[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
