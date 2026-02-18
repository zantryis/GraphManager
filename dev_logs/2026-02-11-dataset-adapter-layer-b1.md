# 2026-02-11 - Dataset Adapter Layer For Unified Issue Loading (B1)

## Context

- Workstream B1 requires a unified adapter layer for multiple dataset backends with normalized schema.
- Existing `load_issues` logic in `src/evaluation.py` was SWE-bench-specific and directly coupled to split iteration/row parsing.
- Upcoming evaluation tracks need retrieval-mode datasets (SWE-PolyBench) without rewriting evaluation internals.

## Decision

- Added `src/datasets/` adapter package with:
  - `BaseIssueAdapter`
  - `SWEBenchIssueAdapter`
  - `SWEPolyBenchIssueAdapter`
  - `build_issue_adapter(...)` factory
- Updated `src/evaluation.py::load_issues(...)` to route through adapters while preserving normalized output fields:
  - `instance_id`, `repo`, `problem_statement`, `patch`, `base_commit`, `gold_files`
- Kept commit grouping logic unchanged (`group_issues_by_base_commit`) and validated regression behavior with normalized inputs.

## Alternatives Considered

1. Keep dataset handling inline in `evaluation.py`.
Tradeoff: fewer modules, but poor extensibility and duplicated parsing logic as backends grow.
2. Build one generic adapter only.
Tradeoff: simpler API, but mixed assumptions per dataset make normalization brittle.
3. Add adapters but defer `load_issues` integration.
Tradeoff: lower immediate risk, but no practical path for multi-backend evaluation entrypoint.

## Evidence

- Added tests in `tests/test_dataset_adapters.py`:
  - SWE-bench schema normalization and gold-file extraction from patch/list fields.
  - SWE-PolyBench retrieval schema normalization.
  - adapter family selection.
  - commit-fidelity grouping regression check with normalized base commits.
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 25 tests passing.

## Consequences

- Expected benefits:
  - Evaluation entrypoint can load multiple dataset families through one normalized interface.
  - Reduced coupling between benchmark-specific row schemas and evaluation logic.
- Known risks:
  - PolyBench field-name assumptions are heuristic and may need adjustment against real artifact snapshots.
  - Adapter currently normalizes only fields needed by current evaluation loop.
- Monitoring signals:
  - dataset load warnings by split,
  - count of issues with empty `gold_files`,
  - commit-group distribution shifts by backend.

## Follow-up

1. Implement B2 amortization reporting fields in `aggregate_results`.
2. Add strict-vs-amortized track separation checks in aggregation metadata.
3. Add adapter regression fixtures from frozen dataset slices for long-term schema drift detection.
