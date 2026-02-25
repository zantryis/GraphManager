# 2026-02-24 - Stage-1 Workers=8 Safety + Throughput Hardening

## Context

- V2 full-stage patch generation was running with repo-level concurrency, but each manifest process remained issue-sequential.
- We needed faster throughput without dropping data, while preserving resume safety.
- Dashboard/progress logic needed to account for worker checkpoint files.
- A key contention risk existed: concurrent manifests reused global clone dirs (`*_repo`, `*_repo_worker_*`).

## Decision

- Enabled true issue-level parallel stage-1 execution through `run_patch.py --workers N` with worker checkpoints.
- Isolated repo clones per run under `results/patch_runs/<run_id>/_repos/*` to eliminate cross-manifest git-dir contention.
- Made checkpoint loading worker-aware and precedence-safe (canonical partial file wins on duplicate instance IDs).
- Extended manifest-pool orchestration to pass worker count via `--run-workers`.
- Updated dashboard and pool activity logic to include `predictions_worker_*.jsonl` in progress/staleness.

Scope boundaries:
- No Stage-2 harness execution changes in this step (still stage1-only local path).
- No claim changes or V2 method set changes in this step.

## Alternatives Considered

1. Keep sequential per-manifest execution
- Lowest risk, but wall-clock too slow for full V2 queue.

2. Add only manifest-level parallelism (existing behavior)
- Better than pure sequential, but still bottlenecked by per-manifest sequential issue loop.

3. Add issue-level workers without per-run clone isolation
- Faster in theory, but unsafe under concurrent manifests due shared git dirs.

Chosen: (2)+(3) with run-scoped clone isolation and checkpoint hardening.

## Evidence

- Code paths updated:
  - `run_patch.py`
  - `tools/run_manifest_pool.py`
  - `src/patch_dashboard.py`
  - `tests/test_checkpoint_resume.py`
  - `tests/test_manifest_pool.py`
  - `tests/test_patch_dashboard.py`
- Test runs:
  - `./.venv/bin/python -m unittest tests/test_checkpoint_resume.py -v` (pass)
  - `./.venv/bin/python -m unittest tests/test_manifest_pool.py -v` (pass)
  - `./.venv/bin/python -m unittest tests/test_patch_dashboard.py -v` (pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (224 tests, all pass)
- Live execution check:
  - Pool command includes `--run-workers 8` and child manifests show `run_patch.py ... --workers 8`.
  - `run_meta.json` in resumed runs now records `"n_workers": 8`.
  - Persistent PTY runner session ID: `81147` (log: `logs/v2_repo_pool_live_20260224_0917.log`).

## Consequences

- Expected benefits:
  - Higher stage-1 throughput via issue-level parallelism.
  - Lower contention/corruption risk from isolated per-run clone paths.
  - Better resume guarantees by loading worker and canonical checkpoint files together.
  - Dashboard progress/stale detection remains accurate with worker checkpoints.

- Known risks:
  - Worker parallelism increases API pressure (rate-limit retries may rise).
  - For index-heavy retrieval methods, per-worker setup can duplicate setup work within a manifest.

- Monitoring signals:
  - Failure log growth in `logs/v2_repo_pool_failures_*.log`.
  - Rate-limit retry bursts in run logs.
  - Per-run `patch_summary.json` completion cadence.

## Follow-up

1. Let current workers=8 stage1 pool finish and verify all remaining pending manifests produce summaries.
2. Run dashboard spot-check for worker-checkpoint progress correctness on active runs.
3. When Modal credits are restored, schedule stage2 evaluate-only sweep over completed run dirs.
