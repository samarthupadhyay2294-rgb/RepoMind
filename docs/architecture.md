# RepoMind architecture

```text
Browser (Next.js + shadcn/ui)
        |
        v
FastAPI (`backend/app/main.py`)
        |-- RequestContextMiddleware  (X-Request-ID in/out, access log)
        |-- /api/v1/repositories      (CRUD, owner-scoped, URL-validated)
        |-- /api/v1/repositories/{id}/index   (synchronous indexing)
        |-- /api/v1/chat              (LangGraph investigation)
        |-- /health                   (liveness, no external checks)
        |
        +-- Repository service  --> Supabase PostgreSQL via SQLAlchemy
        |      (repositories table; owner_id on every lookup;
        |       status: pending -> indexing -> indexed | failed)
        |
        +-- Acquisition  --> workspace <storage>/<uuid>/repo/
        |      (local: ingest in place; git: validated shallow clone,
        |       bounded timeout, post-clone size cap, partial cleanup)
        |
        +-- Indexing worker (synchronous; wraps the same stages a
        |   future async worker would call)
        |      discovery -> filtering -> parsing -> chunking
        |        -> Gemini embeddings (batched, content-hash skip)
        |        -> Qdrant (repo-scoped payloads, stale-point removal)
        |
        +-- LangGraph agent  --> Gemini (primary) [+ optional Mistral]
               classify -> retrieve -> plan -> tool_call -> evaluate
                 -> answer (`path:start-end` citations, validated)
               read-only tools only; bounded steps/evidence/tokens;
               Postgres checkpointer w/ in-memory fallback
```

## Stores

- **Supabase PostgreSQL** (`app/db/`): `repositories` table only
  (no users/jobs/chat tables yet — chat traces persist via the
  LangGraph checkpointer). Tests use per-test SQLite files.
- **Qdrant** (`app/services/qdrant_service.py`, the only module that
  touches `qdrant-client`): every point carries `repository_id`;
  retrieval always filters on it; deletion is scoped to it.
- **Filesystem**: one workspace per repository UUID; `safe_join`
  confinement everywhere; secret filenames never indexed.

## Security boundaries

- Owner checks at every repository/chat boundary (same 404 either way).
- URL allowlist (`http/https/ssh/git`, scp-like) on create, update,
  and again before clone; `file://` and credentialed URLs rejected.
- Tools take `ToolContext`, never bare paths. No shell tools;
  `run_validation` is an allowlisted registry, disabled by default.
- Repository content is untrusted data: delimiter blocks + injection
  pattern flags; injected instructions are never executed.
- `DEV_OWNER_ID` is development-only; `APP_ENV=production` refuses to
  serve until real auth replaces the stub (`app/api/deps.py`).

## Deliberate non-adoptions / deferred work

- No `langchain-qdrant` (raw client works, tested), no Mistral verify
  node, no Gemini native `bind_tools` (deterministic JSON planner).
- No `GET /jobs/{id}`: indexing is synchronous, so a job id would be
  theater — poll `GET /api/v1/repositories/{id}` instead.
- No BM25 hybrid / reranking / summaries / answer cache: the golden
  set (11/11 tool recall) shows no measurable recall problem; add
  vector-level eval first, then justify.
- No token counters: the provider layer returns text only, so
  `metrics.prompt_tokens` stays `None` rather than invented.
- Deployment (Docker/K8s/cloud/CI) intentionally postponed.
