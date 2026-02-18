# 2026-02-11 - Results Viewer Stale Filtering

## Context

- `results/compare.html` was mixing current evaluation-track runs with legacy runs missing track metadata, making "latest" results unclear.
- Repeated reruns with identical config also cluttered the selector.
- Affected files:
  - `visualize_results.py`
  - `tests/test_visualize_results.py`
  - `README.md`

## Decision

- Exclude stale runs by default in the dashboard loader.
- Stale definition: run/repeat aggregate with no effective evaluation track metadata.
- Collapse superseded runs by config key and keep only the newest run.
- Preserve an opt-in path for full history via `--include-stale`.

## Alternatives Considered

1. Keep all runs visible and rely on manual filtering.
Tradeoff: high noise and frequent user confusion over outdated artifacts.

2. Delete old result folders from disk.
Tradeoff: destructive and loses historical auditability.

3. Non-destructive viewer filtering + explicit override flag.
Tradeoff: slightly more loader logic, but clear default UX and preserved history.

## Evidence

- New tests:
  - `tests/test_visualize_results.py::test_load_all_runs_excludes_stale_legacy_runs_by_default`
  - `tests/test_visualize_results.py::test_load_all_runs_keeps_only_latest_superseded_run_per_config`
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v` (42/42 passing)
- Dashboard generation outputs:
  - default: `results/compare.html` (2 run(s))
  - with stale included: `results/compare_with_stale.html` (9 run(s))

## Consequences

- Default dashboard now reflects latest track-valid runs without deleting historical data.
- Historical runs remain accessible for audit/debug with `--include-stale`.

## Follow-up

1. If needed, tune stale policy further (e.g., cutoff dates or explicit manifest tags).
2. Keep repeat-set metadata complete (`evaluation_track`, `issue_set_id`, `created_at`) to maximize filter quality.
3. Use `compare_with_stale.html` only for historical forensics.
