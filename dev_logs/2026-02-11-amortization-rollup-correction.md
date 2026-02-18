# 2026-02-11 - Amortization Rollup Correction For Same-Snapshot Track

## Context

- The results dashboard surfaced amortization track metadata, but same-snapshot amortization values were derived from issue `base_commit` instead of evaluated `used_commit`.
- This underreported reuse in `same_snapshot_amortized` runs and made repeat-set dashboard cards less informative.
- Affected modules:
  - `src/evaluation.py`
  - `run_experiment.py`
  - `tests/test_evaluation_logic.py`
  - `tests/test_repeat_aggregation.py`

## Decision

- Compute amortization commit reuse from `used_commit` first, with `base_commit` fallback.
- Compute `cache_hit_rate` from issue-level reuse (`(n_issues - n_unique_commits) / n_issues`) per `EVALUATION_SPEC.md`; keep commit-group probe counters as observed diagnostics only.
- Extend repeat aggregation to emit an `_amortization` rollup block so repeat dashboards can show track-level reuse stats directly.
- Keep scope limited to metric correctness and aggregation payload shape; no changes to retrieval logic or benchmark sampling.

## Alternatives Considered

1. Keep using `base_commit` for all tracks
Tradeoff: simpler but incorrect for same-snapshot track where evaluated commit is intentionally fixed.

2. Recompute amortization in the viewer from per-run files
Tradeoff: would duplicate metric logic in frontend and risk drift from backend definitions.

3. Correct backend aggregation and pass rollups through repeat aggregate
Tradeoff: small schema extension, but keeps source-of-truth metrics in evaluation pipeline.

## Evidence

- Failing-then-passing regression test:
  - `tests/test_evaluation_logic.py::test_aggregate_results_amortization_uses_evaluated_commit_when_available`
- Failing-then-passing regression test:
  - `tests/test_evaluation_logic.py::test_aggregate_results_cache_hit_rate_uses_issue_level_reuse_formula`
- New repeat rollup coverage:
  - `tests/test_repeat_aggregation.py::test_repeat_aggregate_includes_amortization_rollup`
- Full test verification:
  - `./.venv/bin/python -m unittest discover -s tests -v` (39/39 passing)
- Same-snapshot repeated run in progress while this correction was applied:
  - session-backed command on `psf/requests` with `--evaluation-track same_snapshot_amortized --snapshot-commit 22623bd8c265`
- Corrected same-snapshot artifact values after summary refresh:
  - `results/runs/20260211_154923/summary.json`
  - `results/runs/20260211_155345/summary.json`
  - `results/runs/20260211_155821/summary.json`
  - `results/repeat_sets/20260211_160315.json`

## Consequences

- Same-snapshot amortization fields now represent actual evaluated snapshot reuse.
- Repeat aggregate JSON now carries amortization values consumable by `visualize_results.py` without per-run drilldown.
- Existing consumers that ignore `_amortization` remain unaffected.

## Follow-up

1. Regenerate/refresh summaries for any same-snapshot runs produced before this correction if they are used in report artifacts.
2. Regenerate dashboard output after repeat run completion (`visualize_results.py`).
3. Freeze updated artifacts for report tables (`research_report/generate_artifacts.py`).
