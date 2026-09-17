# Part 2 — Interactive Dependency & Code Graph

Snapshot-scoped, evidence-backed code graph over the existing
Next.js → FastAPI → services → PostgreSQL/Supabase + Qdrant → LangGraph/RAG
stack. The graph is an exploration feature; RAG/chat behavior is unchanged.

## Architecture

```text
index → snapshot → file discovery → extractor → persist → bounded API → UI/tools
```

- **Extractor** (`backend/app/graph/extractor.py`): deterministic stdlib-only
  parsing. Python via `ast`, JS/TS via targeted regexes. Never executes code;
  one bad file degrades to a file node, never fails indexing.
- **Tiers**: Tier 1 (files, directories, imports, exports, contains) from
  parser structure; Tier 2 (calls, references, inherits, implements,
  uses_type) only when safely resolvable (same-file definitions or explicit
  imports — `from app import auth` resolves `auth.authenticate()` to
  `app/auth.py`); Tier 3 (inferred) exists in the data model but is filtered
  at persist time unless `GRAPH_ENABLE_INFERRED_RELATIONSHIPS=true`
  (default `false`), and is always labeled `provenance=inferred`.
- **Storage**: `code_symbols` / `code_relationships` (migration `0003`),
  always `(repository_id, snapshot_id)` scoped at the SQL layer.
  Migration: `cd backend && alembic upgrade head`.
- **Indexing hook**: `run_indexing` begins a snapshot, runs RAG, then
  best-effort graph extraction, then activates. Graph failure never fails
  indexing. Old snapshots keep their exact graph.
- **Qdrant**: unchanged — `mistral-embed`, 1024 dims, `repository_id` +
  `snapshot_id` filters.

## Supported languages / relationships

- Languages: Python (full AST), JavaScript/TypeScript (regex; graceful
  degradation). Unknown languages keep file nodes, no fabricated edges.
- Relationships: `contains, imports, exports, defines→contains, calls,
  references, inherits, implements, overrides, uses_type`.
- Provenance: `parser` (1.0/0.9), `resolver` (0.7–0.9), `inferred`
  (filtered by default). Confidence is not truth; inferred links never
  appear as confirmed facts in UI/API.

## Enabling

Local development default is `DEPENDENCY_GRAPH=true` in
`backend/.env` (see `backend/.env.example`). The flag stays
environment-controlled — API routes read `settings.DEPENDENCY_GRAPH`
and are never hardcoded. To disable in production, set
`DEPENDENCY_GRAPH=false` explicitly in the deployment environment.

Repositories indexed while the graph was disabled must be reindexed
(`POST /api/v1/repositories/{id}/index`) before graph data appears:
graph extraction runs after repository indexing (`run_indexing` →
`_build_snapshot_graph` → activate), and graph endpoints return data
only for an indexed (READY) snapshot.

## API

Flag off → `403 GRAPH_DISABLED` (chat unaffected).

| Method | Route | Notes |
|---|---|---|
| `GET` | `/api/v1/repositories/{id}/graph?node_id=&depth=&direction=&relationship_types=&node_types=&limit=&snapshot_id=` | Bounded neighborhood; no `node_id` = seed files (25 max). `truncated` + `limit_reason` always explicit. |
| `GET` | `/api/v1/repositories/{id}/graph/nodes/{node_id}?snapshot_id=` | Node + direct relationships + graph evidence. |
| `GET` | `/api/v1/repositories/{id}/graph/edges/{edge_id}?snapshot_id=` | Edge + endpoints + provenance/confidence + evidence. |
| `POST` | `/api/v1/repositories/{id}/graph/explain` `{node_id?, edge_id?, question?}` | Deterministic evidence-grounded synthesis; no chain-of-thought. |

Limits (server-clamped): `GRAPH_MAX_DEPTH=3`, `GRAPH_MAX_NODES=100`,
`GRAPH_MAX_EDGES=200` (hard caps 5/300/600). No `snapshot_id` → active
snapshot, response marks `snapshot_active`.

## Tool integration

- Existing filesystem tools (`dependency_graph`, `get_symbol`,
  `find_references`) unchanged.
- DB-backed counterparts in `backend/app/graph/tools.py`
  (`graph_dependency`, `graph_get_symbol`, `graph_find_references`):
  UUID-validated, bounded, repo+snapshot isolated, every hit normalized to
  `EvidenceItem(kind=graph)`.

## Frontend

Route `/repositories/[id]/graph`: SVG canvas (zoom/pan, click select),
relationship/node-type filters, depth selector, evidence panel, snapshot
badge, lazy one-hop expansion with node/edge merge, truncation/loading/empty/
error states, text list alternative for accessibility, URL state
(`?node=&depth=`).

## Security

Owner-checked repository fetch, SQL-level repo+snapshot filters, traversal-
rejecting paths, workspace-confined reads, no shell/network/install, no
secrets in responses/logs, no source dumps in logs.

## Tests

```bash
cd backend
python -m pytest tests/test_graph_part2.py -q   # 11 Part 2 tests
python -m pytest tests -q                        # full suite
ruff check app/graph app/api/routes_graph.py app/services/indexing_service.py app/db/models/graph.py tests/test_graph_part2.py
mypy app/graph app/api/routes_graph.py
```
