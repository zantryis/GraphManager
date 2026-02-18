# 2026-02-11 - Repeat Aggregation: Paired Delta + Bootstrap CI Gates (B4)

## Context

- Workstream B4 gates require repeated-run evidence and paired delta confidence intervals.
- Existing repeat aggregation (`run_experiment.py`) reported only mean/std/min/max per method and lacked explicit CI/gate status.

## Decision

- Extended repeat aggregation with paired per-run delta analysis on `mean_f1`:
  - computes ordered method deltas (`left - right`) for each run
  - computes deterministic bootstrap 95% CI on delta means
- Added repeat gate fields to aggregate output:
  - `min_repeats_met` (`n_runs >= 3`)
  - `pairwise_bootstrap_available`
  - `ci_ready` (both conditions satisfied)
- Preserved existing method aggregate stats for backward compatibility.

## Alternatives Considered

1. Keep only mean/std and defer CIs to external notebooks.
Tradeoff: lower implementation effort, weaker artifact reproducibility.
2. Use analytical normal CIs instead of bootstrap.
Tradeoff: simpler math, but less robust under small/non-normal samples.
3. Compute CIs from per-issue data only.
Tradeoff: stronger statistics, but requires broader result reshaping now.

## Evidence

- Added `tests/test_repeat_aggregation.py`:
  - validates pairwise delta payload presence and CI shape
  - validates gate status for `n_runs=3`
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 31 tests passing.

## Consequences

- Expected benefits:
  - repeat-set artifacts now include CI-ready statistical comparisons.
  - gate status is machine-readable for reporting/release checks.
- Known risks:
  - current CI uses run-level mean F1 deltas, not per-issue paired deltas.
  - deterministic bootstrap seed improves reproducibility but may hide seed sensitivity.
- Monitoring signals:
  - frequency of `ci_ready=false` outputs,
  - CI width trends across repeated experiment sets.

## Follow-up

1. Extend paired-delta CI to per-issue comparisons when multi-run issue alignment is available.
2. Add artifact validator that fails when gate fields are missing in release runs.
3. Surface CI/gate status in `visualize_results.py` and report tables.
