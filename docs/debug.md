# Part 4 — AI Debug Investigator

Evidence-first debugging on top of the existing bounded LangGraph loop —
no parallel agent implementation. The loop, budgets, stop reasons, tool
registry, and citation validation are all shared with chat.

## Flow

```text
redacted structured input → snapshot resolution → debug-framed question
  → shared _run_graph (classify → retrieve/plan → tools → evaluate → answer)
  → deterministic verdict mapping → investigations + investigation_actions
```

## Verdict rules (deterministic, never model self-grading)

- `confirmed`: a stack frame parsed from the report matches a validated
  citation (same path, overlapping lines) **and** ≥2 validated citations.
- `likely`: ≥1 validated citation.
- `unresolved`: no validated citations (with an explicit limitation).

`likely` is never upgraded without the confirmed-rule evidence. Every run
ships limitations (e.g. missing stack frames, truncated evidence).

## Input

`error_text` (required) plus optional `stack_trace`, `affected_route`,
`environment`, `expected_behavior`, `actual_behavior`,
`reproduction_steps`, `snapshot_id`. All fields pass through Part 1
`redact_text` before storage or prompting — pasted secrets become
`[REDACTED]`. Stack frames (`file.py:line`, `at fn (file:line:col)`,
`File "…", line N`) are parsed deterministically for verdict mapping.

## Storage

`investigations` (migration `0005`, snapshot-scoped, immutable history) +
`investigation_actions` (one row per agent tool record: tool, sanitized
args, ok, result counts, warnings, timings). Failures mark the new row
failed and preserve prior completed runs. Migrate:
`cd backend && alembic upgrade head`.

## API

Flag off → `403 INVESTIGATION_DISABLED` (chat/graph/overview unaffected).

| Method | Route | Notes |
|---|---|---|
| `POST` | `/api/v1/repositories/{id}/investigations` | Synchronous bounded run (same design as indexing/overview). Failure → `502`, prior runs preserved. |
| `GET` | `/api/v1/repositories/{id}/investigations/{run_id}` | Verdict, citations, actions, stop reason, snapshot pinning. |

## UI

Route `/repositories/[id]/debug`: structured symptom form (with no-secrets
warning), phase indicator, verdict + confidence badge, findings,
evidence/citations, investigation trail, limitations, and links to the
dependency graph and chat. Unresolved runs say so explicitly.

## Related

The lightweight component/flow map lives at
`GET /api/v1/repositories/{id}/architecture-map` (see `docs/overview.md`) —
derived from the latest overview, not a duplicate graph dataset.

## Tests

```bash
cd backend
python -m pytest tests/test_debug_part5.py -q   # 18 Part 4/5 tests
```
