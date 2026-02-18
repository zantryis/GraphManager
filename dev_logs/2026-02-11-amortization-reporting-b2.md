# 2026-02-11 - Amortization-First Aggregation Block (B2)

## Context

- Workstream B2 requires amortization reporting as a first-class output, including repeat ratio, cache metrics, break-even analysis, and strict-vs-amortized track separation.
- Existing aggregation focused on quality/token totals only and did not enforce track consistency.

## Decision

- Extended `aggregate_results(...)` with:
  - `track_name` (default `strict_commit_fidelity`)
  - `cache_stats` (optional lookups/hits input)
- Added `_amortization` block to summary output with:
  - `track_name`
  - `n_issues`, `n_unique_commits`
  - `commit_repeat_ratio`
  - `cache_lookups`, `cache_hits`, `cache_hit_rate`
  - `pairwise_break_even_n` across methods
- Added mixed-track guard:
  - raises `ValueError` when aggregation input contains multiple `track_name` values.
- Updated `run_experiment(...)` to:
  - track commit-context cache stats (`lookups/hits/misses`),
  - include per-issue `track_name`,
  - pass track/cache metadata into aggregation and summary meta.

## Alternatives Considered

1. Add amortization fields directly to each method row only.
Tradeoff: simpler shape, but less clear global report semantics and harder to compare tracks.
2. Compute cache/repeat metrics only in post-processing scripts.
Tradeoff: low code churn now, but weaker reproducibility and higher mismatch risk.
3. Ignore track consistency checks.
Tradeoff: fewer failures, but high risk of accidental strict/amortized metric mixing.

## Evidence

- Updated tests in `tests/test_evaluation_logic.py`:
  - validates `_amortization` fields and values,
  - validates mixed-track aggregation rejection.
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 27 tests passing.

## Consequences

- Expected benefits:
  - Summary artifacts now expose amortization metrics explicitly for report scripts.
  - Evaluation can fail fast on accidental cross-track merges.
- Known risks:
  - Break-even formula currently token-based and assumes linear per-issue runtime cost.
  - Cache-hit metric depends on caller-provided counters when available.
- Monitoring signals:
  - rate of mixed-track guard failures in CI/runs,
  - stability of `commit_repeat_ratio` and `cache_hit_rate` across repeated runs,
  - downstream plot scripts consuming `_amortization`.

## Follow-up

1. Add strict vs same-snapshot experiment entrypoints that set `evaluation_track` explicitly.
2. Extend reporting scripts to visualize break-even curves from `_amortization`.
3. Add bootstrap CI integration for pairwise deltas in Workstream B4.
