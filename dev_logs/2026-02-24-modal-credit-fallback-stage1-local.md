# 2026-02-24 - Modal credit fallback and parallel stage1-only continuation

## Context

- Active V2 full-run pool was executing all manifests with `--evaluate --modal`.
- User reported Modal credit exhaustion and requested fallback to local parallel execution.
- Existing pool launcher had no execution-mode switch; it always appended `--modal`.

## Decision

- Add scheduler controls to decouple execution backend and evaluation stage:
  - `--execution-mode {modal,local}`
  - `--evaluate-mode {stage12,stage1_only}`
- Because local Docker harness is unavailable in this environment, switch to `stage1_only` continuation now.
- Preserve `--resume-incomplete` and 8-way repo concurrency so progress is not lost.

Scope boundary:
- No implementation of `repomap_like` / `agentless_like_localization` in this step.
- No harness evaluation semantics change; only orchestration and fallback controls.

## Alternatives Considered

1. Keep Modal pool running and wait for new credits.
- Tradeoff: repeated failures/idle time; poor progress.

2. Switch to local harness immediately.
- Tradeoff: blocked because Docker daemon/socket unavailable here.

3. Continue with Stage 1 patch generation only (chosen), evaluate later.
- Tradeoff: no immediate resolved metrics, but preserves throughput and data capture.

## Evidence

- Tests added/updated:
  - `tests/test_manifest_pool.py`
    - modal flag present in modal mode
    - modal flag omitted in local mode
    - stage1_only omits `--evaluate` and `--modal`
- Validation:
  - `./.venv/bin/python -m unittest tests.test_manifest_pool -v` passed
  - `./.venv/bin/python -m unittest discover -s tests -v` passed (`220` tests)
- Environment checks:
  - `docker info` failed: no daemon/socket
  - `/var/run/docker.sock` missing
  - rootless Docker startup failed: `newuidmap` missing
- Runtime cutover:
  - stopped old modal pool + modal run_patch workers
  - launched new pool:
    - `./.venv/bin/python tools/run_manifest_pool.py --manifest-list logs/v2_full_manifests_20260223_222457.txt --results-dir results/v2_full_runs --max-parallel-repos 8 --manifest-timeout-s 0 --resume-incomplete --execution-mode local --evaluate-mode stage1_only --log logs/v2_repo_pool_20260224_083920_stage1_local.log --failure-log logs/v2_repo_pool_failures_20260224_083920_stage1_local.log`

## Consequences

- Patch generation continues in parallel without Modal/Docker dependency.
- Evaluation remains pending until Modal credentials are restored or local Docker is made available.
- Existing partial checkpoints are reused via `--resume-incomplete`.

## Follow-up

1. When new Modal credentials are available, run Stage 2 evaluation pass (`--evaluate-only`) over completed run directories.
2. If local harness is still desired, provision Docker daemon (or rootless prerequisites incl. `newuidmap`) and relaunch with `--execution-mode local --evaluate-mode stage12`.
3. Keep dashboard denominator scopes enabled (visible/started/planned) to avoid misinterpreting campaign progress.
