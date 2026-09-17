"""Gap #8: request IDs + per-run chat metrics."""

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.service import run_chat
from app.db.models.repository import SourceType
from tests.test_agent_part7 import ScriptLLM, make_deps, make_hit


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_id_propagates_caller_value(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "demo-123"})
    assert response.headers["X-Request-ID"] == "demo-123"


def test_chat_response_carries_honest_metrics(tmp_path: Path) -> None:
    from app.db.models.repository import Repository

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    repository = Repository(
        owner_id="o",
        name="n",
        source_type=SourceType.LOCAL,
        local_path=str(root),
    )
    llm = ScriptLLM(request_type="symbol_lookup", answer="Found in `src/auth.py:1-2`.")
    deps = make_deps(root, llm, [make_hit(path="src/auth.py", start=1, end=2)])
    response = asyncio.run(run_chat(repository, "Where is f?", deps=deps))
    assert response.metrics is not None
    assert response.metrics.llm_calls == len(llm.calls) > 0
    assert response.metrics.steps > 0
    assert response.metrics.latency_ms >= 0
    # Token counts are unavailable from the provider layer — never invented.
    assert response.metrics.prompt_tokens is None
    assert response.metrics.completion_tokens is None
