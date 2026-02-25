# 2026-02-24 - Dashboard overall patched/total progress

## Context

- User requested a top-level dashboard indicator for overall progress in `patched/total` form.
- Existing dashboard showed per-run patched counts and per-method completed progress, but not a global patched denominator summary.

## Decision

- Add backend aggregate summary for currently visible runs and expose it via `/api/status`.
- Render a top stat card: `Patched / Total Issues`.

Scope boundary:
- No changes to run collection/dedup logic.
- No changes to patch pipeline execution semantics.

## Alternatives Considered

1. Compute only in frontend from row list.
- Tradeoff: works, but duplicates aggregation logic and makes API less reusable.

2. Compute only in backend payload (chosen).
- Tradeoff: one extra function, but keeps aggregation canonical and testable.

3. Add both backend+frontend independent calculations.
- Tradeoff: redundant and risks drift.

## Evidence

- Added `summarize_dashboard_runs()` in `src/patch_dashboard.py`.
- `/api/status` now returns `summary` payload in `tools/patch_dashboard.py`.
- Frontend stats now render `Patched / Total Issues` card from `summary`.
- New test added:
  - `tests/test_patch_dashboard.py::test_summarize_dashboard_runs_reports_patched_over_total`
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` → pass
  - `./.venv/bin/python -m unittest discover -s tests -v` → pass (`216` tests)

## Consequences

- Dashboard now reports a single global patched progress number at a glance.
- Aggregation is deterministic and aligned with current filters/deduped rows.
- API is more useful for external consumers (scripts, alt dashboards).

## Follow-up

1. If desired, add `completed/total` card next to `patched/total` for workflow tracking.
2. If dashboard users want cross-filter consistency, add explicit summary scope text under the card.
3. Keep summary contract stable if external tooling starts consuming `/api/status`.
