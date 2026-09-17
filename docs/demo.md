# RepoMind demo walkthrough

Needs: backend running (`uvicorn app.main:app`), plus `GEMINI_API_KEY`
and `QDRANT_URL` for the indexing/chat steps (registration and
index-failure display work without them).

```text
1. Seed a demo repository
     python scripts/seed_demo_repo.py demo-repo
2. Register it (local source ingests in place)
     POST /api/v1/repositories
     {"name": "demo", "source_type": "local", "local_path": "<abs>/demo-repo"}
3. Index it
     POST /api/v1/repositories/{id}/index
     -> {"status": "indexed", ...}   (or "failed" + error_message)
4. Ask a question
     POST /api/v1/chat
     {"repository_id": "{id}", "question": "Where is authentication implemented?"}
     -> answer + `path:start-end` citations + metrics
5. Inspect a cited file range, then delete the repository
     DELETE /api/v1/repositories/{id}   (vectors + workspace go too)
```

The same flow is clickable in the frontend: repositories list → detail
(Start indexing → Completed) → chat with citation cards. Every response
carries `X-Request-ID` for correlating with backend logs.
