# 2026-02-24 - GraphManager Patch Run Dashboard

## Context

- User requested a dashboard to monitor long-running patch experiments instead of manual log polling.
- Existing dashboard at `../dag-lbmas/dashboard/server.py` was assessed but uses a different JSONL schema and run model.

## Decision

- Implemented a GraphManager-native dashboard stack:
  - `src/patch_dashboard.py` for run discovery and status aggregation.
  - `tools/patch_dashboard.py` for a live HTTP dashboard (`/` + `/api/status`).
- Kept implementation dependency-light (stdlib HTTP server + existing repo code).

## Alternatives Considered

1. Reuse `../dag-lbmas/dashboard/server.py` directly
   - Not feasible without heavy schema translation due to LbMAS-specific assumptions.
2. Build Flask dashboard from scratch
   - Viable, but adds dependency and setup friction.
3. Build stdlib HTTP dashboard + shared status module (chosen)
   - Minimal friction, easy to run in current repo, testable core logic.

## Evidence

- New files:
  - `src/patch_dashboard.py`
  - `tools/patch_dashboard.py`
  - `tests/test_patch_dashboard.py`
- Updated docs/state:
  - `docs/V2_RUN_DESIGN_2026-02-24.md`
  - `CURRENT_STATE.md`
- Test results:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` (pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (201/201 pass)
- Smoke check:
  - `tools/patch_dashboard.py` served `/api/status` and returned discovered run records.

## Consequences

- Expected benefits:
  - Live visibility into run progress, status, and outcomes without manual tailing.
  - Reusable status API for future UI/export tooling.
- Known risks:
  - Running/stalled detection for in-flight runs is heuristic when `patch_summary.json` is absent.
- Monitoring signals:
  - Compare `status` vs. partial-file age and presence/absence of final summary.

## Follow-up

1. Add optional process-liveness integration (`pgrep`) for stronger `running` vs `stalled` labeling.
2. Add filtering (method/repo/date range) and CSV export in dashboard UI.
3. Integrate dashboard start command into run orchestration scripts for full V2 sweeps.
