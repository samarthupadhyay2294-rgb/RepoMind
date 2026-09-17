# Part 3 — AI Repository Overview / Architecture Map

Snapshot-scoped, evidence-grounded first-run briefing over the existing
Next.js → FastAPI → services → PostgreSQL/Supabase + Qdrant → LangGraph/RAG
stack. The LLM synthesizes from deterministic facts only; chat/RAG behavior
is unchanged.

## Architecture

```text
snapshot → fact collector → Part 2 graph → redacted/budgeted evidence
  → structured LLM synthesis → claim validation → PG → API → UI
```

Observed facts, derived relationships, and AI summaries stay separate: the
model never invents files, dependencies, or runtime behavior.

## Deterministic facts (`backend/app/overview/facts.py`)

Languages/file counts, top directories, manifests (`package.json`,
`pyproject.toml`, `requirements*.txt`, …) with dependency names + npm
scripts, framework markers (FastAPI, Next.js, SQLAlchemy, …), entry-point
**candidates** (never `confirmed` from static analysis: `main.py`,
`FastAPI(...)`, CLI markers, Next.js `app/page|route` and `pages/index`,
`index/main/server.ts`), route hints (`APIRouter`, route decorators),
config files, DB indicators, and Part 2 graph counts + top importers —
all reused from existing discovery/parser/graph tables, no re-parsing.

## Evidence (`evidence_selection.py`)

Priority: entry points → routers → manifests → db modules → config → top
importers. Every excerpt passes through Part 1 `redact_text` (secrets become
`[REDACTED]`, flagged) and `pack_evidence` with explicit
`evidence_items_total/used`, `evidence_truncated`, `omitted_count` metadata.

## Synthesis (`prompt.py`, `synthesis.py`)

Evidence-first prompt (compact facts + numbered excerpts, bounded by
`OVERVIEW_MAX_PROMPT_CHARS`) via the existing LLM factory only:
local Ollama `gemma4:31b-cloud`, no API key. Strict JSON → `StructuredOverview`
schema. Malformed output fails safely (`OVERVIEW_SYNTHESIS_FAILED`).

## Validation (`validate.py`)

Evidence IDs must exist in the exact repo+snapshot set; paths must be
canonical and present in the snapshot's symbol inventory; line ranges sane;
backticked prose refs scrubbed via Part 1 citation utils. Entry points
require valid evidence; invalid claims are removed (counted in
`removed_claims`); everything uncertain stays in `uncertainties`.

## Storage

`architecture_overviews` (migration `0004`): summary, architecture_style
(nullable/`uncertain`), entry_points, components, data_flows, boundaries,
key_dependencies, configuration_areas, uncertainties, evidence refs,
truncation counters, model, status (`generating/completed/failed`),
`prompt_version`. Immutable history — failures never overwrite the last
successful overview. Migrate: `cd backend && alembic upgrade head`.

## Enabling

Local development default is `ARCHITECTURE_OVERVIEW=true` in
`backend/.env` (see `backend/.env.example`). The flag stays
environment-controlled — API routes call
`require_overview_enabled()` and are never bypassed. To disable in
production, set `ARCHITECTURE_OVERVIEW=false` explicitly.

Overviews generate on demand per snapshot, so repositories indexed
while the flag was off need no reindex: restart the backend, open the
repository overview page, and choose Generate.

## API

Flag off → `403 OVERVIEW_DISABLED` (chat/graph unaffected).

| Method | Route | Notes |
|---|---|---|
| `GET` | `/api/v1/repositories/{id}/overview?snapshot_id=` | Latest completed overview for active/pinned snapshot; `snapshot_active` marks staleness; missing → `404 OVERVIEW_NOT_FOUND`; unindexed → `409 OVERVIEW_NO_SNAPSHOT`. |
| `POST` | `/api/v1/repositories/{id}/overview:generate` `{snapshot_id?}` | Synchronous pipeline (same design as indexing); failure → `502`, prior overview preserved. |
| `GET` | `/api/v1/repositories/{id}/architecture-map` | Lightweight component/flow/entry-point map from the latest overview (no duplicate graph dataset); missing overview → `404 OVERVIEW_NOT_FOUND`. |

## UI

Route `/repositories/[id]/overview`: summary + style, SVG architecture map
(components as nodes, flows as arrows, click-to-inspect, keyboard
accessible), entry points with confidence badges, components, flows,
dependencies, config (values never shown — paths only), uncertainties,
evidence list with redaction marks, first-run generate card, stale-snapshot
warning with regenerate, and links to the Part 2 dependency graph and chat.

## Security

Owner-checked repos, SQL-level repo+snapshot filters everywhere (facts,
graph, evidence, overviews), redaction before any LLM contact, no secrets
in responses/logs, no prompt/log dumps.

## Tests

```bash
cd backend
python -m pytest tests/test_overview_part3.py -q   # 17 Part 3 tests
python -m pytest tests -q                            # full suite
ruff check app/overview app/api/routes_overview.py app/db/models/overview.py tests/test_overview_part3.py
mypy app/overview app/api/routes_overview.py
```

Live Ollama is checked opportunistically (`test_real_ollama_…` skips when
nothing listens on `127.0.0.1:11434`); the mocked suite is the default path.
