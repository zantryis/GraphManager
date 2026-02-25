# 2026-02-24 - Dashboard method grouping and pending-status hardening

## Context

- Dashboard readability was poor for live V2 monitoring: flat table, no method grouping, and ambiguous pending rows.
- User requested method-organized collapsibles and clearer explanation of `not_started` rows.
- Active view still surfaced some stale placeholder attempts because they had fresh-enough metadata timestamps.

## Decision

- Rework dashboard UI into method-grouped collapsible sections.
- Add per-row phase hints for pending attempts.
- Harden pending/stale classification in backend:
  - treat zero-progress runs older than stale threshold as stalled
  - use run PID liveness (when available) to classify abandoned runs as stalled
- Add PID to `run_meta.json` at run start for future runs.

Scope boundaries:
- No changes to retrieval/patch algorithm behavior.
- No schema migration for historical run_meta files (old runs may not have PID).

## Alternatives Considered

1. Keep flat table and add more columns
Tradeoff: still hard to scan at 10+ concurrent attempts.

2. Group by repo instead of method
Tradeoff: method comparisons remain hard, which is the primary dashboard use during sweeps.

3. Group by method with collapsibles (chosen)
Tradeoff: slightly denser frontend code, but major readability gain for baseline comparison.

## Evidence

- UI rewrite: `tools/patch_dashboard.py`
  - method accordion (`<details class="method-group">`)
  - summary pills and grouped progress
  - row-level phase hint for `not_started`
- Backend hardening: `src/patch_dashboard.py`
  - stale/no-progress detection based on age
  - PID liveness checks via `run_meta.pid`
- Run metadata extension: `run_patch.py` now writes `pid` to `run_meta.json`
- Tests added/updated: `tests/test_patch_dashboard.py`
  - dead PID before progress => stalled
  - alive PID before progress => not_started
  - old no-progress run_meta => stalled
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` (11 pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (211 pass)

## Consequences

- Dashboard is easier to read during concurrent sweeps and directly supports method-level tracking.
- Fewer false pending rows in active view; stale placeholders age out into `stalled` and are hidden by default.
- Historical runs without PID still rely on stale-age logic (not perfect but improved).

## Follow-up

1. Add `started_at` and periodic heartbeat fields to run metadata for stronger liveness semantics.
2. Optionally add explicit `queued/setup/running` phase in backend payload.
3. If needed, add a compact mode for mobile-width browsing.
