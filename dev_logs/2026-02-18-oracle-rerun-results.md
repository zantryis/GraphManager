# 2026-02-18 - Oracle Rerun Results (Post B7+B8)

## Context

- B7 (empty patch submission for `apply_failed`) and B8 (missing trailing newline in extracted patch text) were fixed earlier on 2026-02-18.
- Prior patching runs were invalid for resolved-rate interpretation because harness submissions were suppressed or malformed.
- This run establishes the first valid oracle ceiling data point for Workstream B.
- Affected files/modules/experiments:
  - `run_patch.py`
  - `src/patch_agent.py`
  - `patch_manifests/swebench_verified_requests_oracle_v1.yaml`
  - `results/patch_runs/20260218_154217/`

## Decision

- Execute a full evaluated oracle run on the 8-instance `psf/requests` manifest and record outcomes as the canonical post-fix validation run.
- Do not modify retrieval codepaths or Workstream A artifacts.
- Scope boundaries:
  - No expansion to 30-instance pilot in this step.
  - No retraining/tuning of patch model.

## Alternatives Considered

1. Skip oracle and go directly to `gm_progressive` baseline.

Tradeoff: faster throughput, but no validated post-fix ceiling; baseline interpretation would remain weak.

2. Run oracle without harness (`--evaluate` off).

Tradeoff: cheaper/faster, but no pass@1/resolved evidence; does not satisfy Paper 1 end-to-end validation requirement.

3. Run full oracle with harness evaluation (chosen).

Tradeoff: higher runtime/compute cost, but produces the required validity checkpoint and resolved-instance ground truth.

## Evidence

- Test gate before run:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 112 tests passed.
- Docker readiness:
  - `docker ps`
  - Result: daemon reachable.
- Oracle command executed:
  - `PYTHONUNBUFFERED=1 ./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_oracle_v1.yaml --evaluate`
- Primary artifacts:
  - `results/patch_runs/20260218_154217/patch_summary.json`
  - `results/patch_runs/20260218_154217/predictions.json`
  - `graphmanager-oracle.graphmanager_20260218_154217.json`
  - `logs/run_evaluation/graphmanager_20260218_154217/`
- Key metrics (from `patch_summary.json` + harness report):
  - `run_id`: `20260218_154217`
  - `n_instances`: 8
  - `n_patched`: 4
  - `n_apply_ok`: 4
  - `n_apply_failed`: 3
  - `apply_success_rate`: 0.5714
  - `resolved_instances`: 3
  - `resolved_rate`: 0.375
  - `resolved_ids`: `psf__requests-1142`, `psf__requests-1724`, `psf__requests-1766`
  - Harness outcome summary: completed=6, unresolved=3, errors=1, empty_patch=1
- Notable per-instance failures:
  - `psf__requests-1921`: harness patch apply error (`malformed patch ...`)
  - `psf__requests-2317`: `no_patch`/`cannot_patch` path
  - `psf__requests-5414`, `psf__requests-6028`: submitted but unresolved

## Consequences

- Expected benefits:
  - Confirms pipeline is no longer hard-zeroing resolved rates post B7+B8.
  - Provides first valid oracle ceiling baseline for subsequent `gm_progressive` comparison.
- Known risks:
  - Oracle still has one empty patch and one harness error; remaining failures now look mixed (formatting robustness + model quality), not the previous universal pipeline suppression.
- Monitoring signals:
  - `empty_patch_instances` should remain low and explainable per run.
  - `error_instances` should be inspected via `logs/run_evaluation/.../run_instance.log`.
  - Compare upcoming `gm_progressive` 8-instance run against this oracle ceiling.

## Follow-up

1. Run 8-instance `gm_progressive` baseline with evaluation (`patch_manifests/swebench_verified_requests_v1.yaml`).
2. Confirm unit-test gate remains green before additional patching pilots.
3. If baseline is stable, proceed to 30-instance pilot matrix (none/rag_progressive/gm_progressive) per Workstream B plan.
