# 2026-02-12 - Deterministic Retrieval Precision Hardening Pilot

## Context

- `gm_deterministic` showed high recall but low precision/F1 in early clean-root runs, mainly due to over-returning files.
- Objective for this pass: reduce low-signal tail files without reintroducing loop-heavy retrieval.
- Affected modules:
  - `src/deterministic_retrieval.py`
  - `src/evaluation.py`
  - `run_experiment.py`
  - `run_suite.py`
  - `tests/test_deterministic_retrieval.py`
  - `tests/test_suite_config.py`

## Decision

- Added two deterministic precision controls:
  1. Adaptive score cutoff for returned file list:
     - keep files while `score >= score_ratio_cutoff * top_score`
     - always keep at least `min_return_files`
  2. Hub-file penalty:
     - compute file hubness from aggregated node degree per file
     - add a penalty term once hubness exceeds `hub_degree_threshold`

- New deterministic retrieval knobs (plumbed through experiment/suite):
  - `deterministic_min_return_files`
  - `deterministic_score_ratio_cutoff`
  - `deterministic_min_score_cutoff`
  - `deterministic_hub_degree_threshold`
  - `deterministic_hub_penalty_scale`

- Defaults selected for pilot:
  - `min_return_files=1`
  - `score_ratio_cutoff=0.70`
  - `min_score_cutoff=0.0`
  - `hub_degree_threshold=20`
  - `hub_penalty_scale=0.35`

## Alternatives Considered

1. Lower static `max_return_files` only
- Tradeoff: simple, but brittle across issue difficulty and can under-retrieve on broader issues.

2. Hard filter by edge type (e.g., drop structural edges)
- Tradeoff: helps precision, but risks recall regressions when structural context is needed.

3. Replace deterministic scoring with a second-stage LLM reranker
- Tradeoff: could improve precision but reintroduces token/latency variability and nondeterminism.

## Evidence

- New failing-first tests added and passed:
  - `test_adaptive_score_cutoff_trims_low_scoring_tail_files`
  - `test_hub_penalty_demotes_generic_high_degree_file`
  - file: `tests/test_deterministic_retrieval.py`

- Full unit suite:
  - command: `./.venv/bin/python -m unittest discover -s tests -v`
  - result: 63 tests passed.

- Pilot run artifact:
  - `results/pilot_precision_20260211_200947/runs/20260211_200953/summary.json`
  - `results/pilot_precision_20260211_200947/runs/20260211_200953/detailed_results.json`

- Before/after on same strict issue (`pallets__flask-4045`):
  - Before: `results/clean_eval_20260211_193241/runs/20260211_193305/summary.json`
    - `gm_deterministic` precision `0.1667`, recall `1.0`, F1 `0.2857`, runtime tokens `57`
  - After: `results/pilot_precision_20260211_200947/runs/20260211_200953/summary.json`
    - `gm_deterministic` precision `0.5`, recall `1.0`, F1 `0.6667`, runtime tokens `57`

## Consequences

- Expected benefits:
  - Better precision/F1 when score tails are noisy.
  - Reduced generic high-degree file over-selection.
  - Determinism and low runtime-token profile preserved.

- Known risks:
  - Over-pruning for issues that genuinely require many files.
  - Hub penalty may suppress legitimate central files in some repos.

- Monitoring signals:
  - File-count distribution per issue.
  - Recall regressions in multi-file gold cases.
  - Paired F1 deltas vs `gm_progressive` across strict and same-snapshot tracks.

## Follow-up

1. Run multi-issue pilot cells for at least one strict and one same-snapshot repo track with new defaults.
2. Add targeted regression tests for multi-file gold cases where adaptive cutoff must not over-prune.
3. Tune `score_ratio_cutoff` and `hub_penalty_scale` on frozen dev split; freeze selected values in artifacts.
