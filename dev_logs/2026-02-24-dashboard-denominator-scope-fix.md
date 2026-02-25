# 2026-02-24 - Dashboard denominator scope fix (visible vs started vs planned)

## Context

- Dashboard showed `patched/total` using only currently visible rows (often active-only), which led to misleading totals (e.g., `99`) versus expected campaign denominator.
- User flagged this as incorrect for full SWE-bench V2 tracking.

## Decision

- Keep filtered/visible summary, but add explicit additional denominator scopes:
  - `summary_visible`: totals for rows currently shown under filters.
  - `summary_started`: totals across all discovered started manifests in results root.
  - `summary_plan`: totals from manifest-list plan (`--manifest-list`), i.e., full campaign denominator.
- Update dashboard cards to render all three scopes side-by-side.

Scope boundary:
- No change to run execution.
- No change to dedupe/stall heuristics in run collection.

## Alternatives Considered

1. Keep single summary and add a tooltip.
- Tradeoff: still easy to misread denominator.

2. Compute campaign denominator implicitly from started runs only.
- Tradeoff: undercounts queue/not-yet-started manifests.

3. Add explicit visible/started/planned scopes (chosen).
- Tradeoff: slightly denser UI, but unambiguous.

## Evidence

- Added `load_manifest_plan_summary()` in `src/patch_dashboard.py`.
- Added API payload fields in `tools/patch_dashboard.py`:
  - `summary_visible`, `summary_started`, `summary_plan`.
- Added dashboard CLI option:
  - `--manifest-list <path>`.
- Added test:
  - `tests/test_patch_dashboard.py::test_load_manifest_plan_summary_counts_instances_and_methods`.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` (13/13 pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (217 tests pass)

## Consequences

- Dashboard now clearly distinguishes:
  - what is visible now,
  - what has started so far,
  - and what is planned overall.
- Campaign denominator for current V2 full run correctly reports planned `2000` issues (`48` manifests).

## Follow-up

1. Keep dashboard started with manifest list for V2 runs:
   - `--manifest-list logs/v2_full_manifests_20260223_222457.txt`.
2. Optionally add a compact legend in UI clarifying scope definitions.
3. If manifest list rotates, restart dashboard with the new list path.
