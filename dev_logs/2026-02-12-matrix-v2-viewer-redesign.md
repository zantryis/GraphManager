# 2026-02-12 Matrix V2 + Viewer Redesign

## Context

The next-agent mission required four linked changes in order:

1. redesign evaluation around a broader benchmark/domain matrix,
2. redesign visualization around cross-task tradeoff evidence,
3. regenerate repeat evidence,
4. sync report/docs from frozen artifacts.

Prior state was requests-heavy with limited matrix pinning and a run viewer centered on per-run/per-issue panels.

## Decision

1. Added manifest-pinned matrix execution support in the runtime path:
- dataset adapters accept explicit `instance_ids` ordering,
- evaluator/suite metadata records `issue_set_id`, `domain`, `seed`, `instance_ids`, track/snapshot,
- suite config supports per-cell repeats and writes repeat aggregates per experiment.

2. Added explicit matrix config:
- `experiments_matrix_v2.yaml` with strict + same-snapshot cells across SWE-bench and SWE-PolyBench domains.

3. Reworked viewer to emphasize cross-task evidence:
- global cost-quality frontier,
- tradeoff outlier table,
- regime-shift detector (strict vs same-snapshot),
- benchmark/domain/track filters.

4. Regenerated CI-ready requests track pair on matrix-v2 manifest and froze artifacts.

## Alternatives considered

1. Keep existing run-level viewer and only add minor filters.
- Rejected: did not satisfy cross-task tradeoff requirement.

2. Run full matrix immediately including all PolyBench cells.
- Attempted but blocked by provider embedding quota (`429 RESOURCE_EXHAUSTED`) during yt-dlp setup embeddings.

3. Build a separate matrix orchestration script.
- Rejected for now: extending `run_suite.py` was lower-risk and reused tested flow.

## Evidence

Code/tests:
- `src/datasets/adapters.py`
- `src/evaluation.py`
- `run_experiment.py`
- `run_suite.py`
- `visualize_results.py`
- `tests/test_dataset_adapters.py`
- `tests/test_suite_config.py`
- `tests/test_visualize_results.py`

Matrix config:
- `experiments_matrix_v2.yaml`

Fresh CI-ready repeat artifacts:
- `results/repeat_sets/20260211_183938_swe_bench_psf_requests_strict_commit_fidelity_issues_swebench_requests_v2_10.json`
- `results/repeat_sets/20260211_185205_swe_bench_psf_requests_same_snapshot_amortized_issues_swebench_requests_v2_10.json`

Frozen bundle:
- `research_report/artifacts/frozen-20260211-matrix-v2-requests/manifest.json`
- `research_report/artifacts/frozen-20260211-matrix-v2-requests/summary_bundle.json`

PolyBench blocking evidence:
- run logs for `results/runs/20260211_185205` through `results/runs/20260211_185446` with `429 RESOURCE_EXHAUSTED` on embedding requests.

## Consequences

1. Requests strict/snapshot comparisons are now reproducible with pinned issue manifests and CI-ready uncertainty.
2. Viewer now surfaces cross-task frontier/outlier/regime behavior directly.
3. Cross-benchmark matrix completion is still partial until embedding quota permits PolyBench runs.

## Follow-up

1. Re-run PolyBench matrix cells from `experiments_matrix_v2.yaml` once embedding quota resets.
2. Freeze an updated cross-benchmark bundle including PolyBench repeats.
3. Update report result sections to cite the new cross-benchmark frozen bundle as primary source.
