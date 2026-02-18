# 2026-02-11 - Evaluation Track Grouping Contract (B4 Foundation)

## Context

- Workstream B4 defines two key evaluation tracks:
  - strict commit fidelity
  - same-snapshot amortized
- Existing experiment flow always grouped by `base_commit`, so same-snapshot studies required ad-hoc modifications.

## Decision

- Added explicit grouping helper in `src/evaluation.py`:
  - `build_issue_groups(issues, evaluation_track, snapshot_commit=None)`
- Supported tracks:
  - `strict_commit_fidelity` -> `group_issues_by_base_commit(...)`
  - `same_snapshot_amortized` -> single group with optional forced `snapshot_commit`
- Updated `run_experiment(...)` to use `build_issue_groups(...)` and persist:
  - `evaluation_track`
  - `snapshot_commit`
  in summary metadata.

## Alternatives Considered

1. Keep a single strict grouping path.
Tradeoff: simpler path, but blocks controlled amortization experiments.
2. Implement same-snapshot logic only in outer scripts.
Tradeoff: lower code churn, but inconsistent grouping semantics across callers.
3. Introduce full track orchestration framework now.
Tradeoff: future-ready, but too large for current incremental hardening step.

## Evidence

- Added test in `tests/test_evaluation_logic.py`:
  - `test_build_issue_groups_supports_strict_and_same_snapshot_tracks`
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 30 tests passing.

## Consequences

- Expected benefits:
  - track behavior is now explicit and test-covered,
  - same-snapshot amortization runs can use existing experiment entrypoint.
- Known risks:
  - same-snapshot mode currently uses a single commit key without verifying working tree state matches that commit.
- Monitoring signals:
  - grouped issue counts per track,
  - commit cache behavior differences between tracks.

## Follow-up

1. Add run-gate checker enforcing repeat-count/CI artifact requirements.
2. Integrate track-aware plotting/report generation from `_amortization`.
3. Execute repeated strict + same-snapshot runs for primary retrieval comparison.
