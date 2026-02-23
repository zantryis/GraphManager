# 2026-02-18 - Oracle + GM Progressive Reruns (Gemini-3 Patch Config)

## Context

- Workstream B required a clean oracle ceiling and a matched gm_progressive baseline after config upgrades.
- Config changes applied before this rerun pair:
  - patch model: `gemini-2.5-flash` -> `gemini-3-flash-preview`
  - `patch_max_file_chars`: `12000` -> `200000`
- Affected pipeline artifacts:
  - `patch_manifests/swebench_verified_requests_oracle_v1.yaml`
  - `patch_manifests/swebench_verified_requests_v1.yaml`
  - `results/patch_runs/20260218_163915/`
  - `results/patch_runs/20260218_165447/`

## Decision

- Run two sequential evaluated patch runs on the same 8 `psf/requests` instances:
  1. `oracle` (ceiling)
  2. `gm_progressive` (zero-shot baseline)
- Gating rule used: proceed to Run 2 only if Run 1 resolves >= 2/8.
- Scope boundaries:
  - No retrieval-workstream reruns (`run_experiment.py`) in this step.
  - No 30-instance expansion in this step.

## Alternatives Considered

1. Run only oracle and defer gm baseline.

Tradeoff: would validate ceiling only, but leave comparative retrieval-to-patch baseline missing.

2. Run gm baseline first, then oracle.

Tradeoff: risks interpreting baseline without a same-config ceiling anchor.

3. Run oracle then gm baseline sequentially with explicit gate (chosen).

Tradeoff: longer runtime, but preserves interpretability and run-order rigor.

## Evidence

- Test gate before runs:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 112 tests passed.
- Docker gate before runs:
  - `docker ps` succeeded.

### Run 1 - Oracle (ceiling)

- Command:
  - `PYTHONUNBUFFERED=1 ./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_oracle_v1.yaml --evaluate`
- Run ID: `20260218_163915`
- Artifacts:
  - `results/patch_runs/20260218_163915/patch_summary.json`
  - `results/patch_runs/20260218_163915/predictions.json`
  - `graphmanager-oracle.graphmanager_20260218_163915.json`
- Primary metrics:
  - `n_patched=2/8`
  - `n_apply_ok=2`, `n_apply_failed=3`
  - `apply_success_rate=0.4000`
  - `resolved=3/8` (`37.5%`)
  - `resolved_ids`: `psf__requests-1724`, `psf__requests-1766`, `psf__requests-2317`
  - harness summary: completed=4, unresolved=1, errors=1, empty_patch=3
- Gate decision:
  - `resolved=3 >= 2` -> Run 2 allowed.

Per-instance summary (Run 1):
- `patched`: `psf__requests-1724`, `psf__requests-2317`
- `apply_failed`: `psf__requests-1142`, `psf__requests-1766`, `psf__requests-1921`
- `no_patch`: `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`

### Run 2 - GM Progressive baseline (zero-shot)

- Command:
  - `PYTHONUNBUFFERED=1 ./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml --evaluate`
- Run ID: `20260218_165447`
- Artifacts:
  - `results/patch_runs/20260218_165447/patch_summary.json`
  - `results/patch_runs/20260218_165447/predictions.json`
  - `graphmanager-gm_progressive.graphmanager_20260218_165447.json`
- Primary metrics:
  - `n_patched=3/8`
  - `n_apply_ok=3`, `n_apply_failed=4`
  - `apply_success_rate=0.4286`
  - `resolved=2/8` (`25.0%`)
  - `resolved_ids`: `psf__requests-1724`, `psf__requests-5414`
  - harness summary: completed=5, unresolved=3, errors=2, empty_patch=1

Per-instance summary (Run 2):
- `patched`: `psf__requests-1724`, `psf__requests-2317`, `psf__requests-6028`
- `apply_failed`: `psf__requests-1142`, `psf__requests-1766`, `psf__requests-1921`, `psf__requests-5414`
- `no_patch`: `psf__requests-2931`

## Consequences

- Expected benefits:
  - Produced a same-config oracle ceiling and a directly comparable gm baseline.
  - Confirmed Run 2 was executed under valid gating from Run 1.
- Known risks:
  - Recurrent malformed/apply failures remain on key instances (`1142`, `1766`, `1921`).
  - MAX_TOKENS/no-patch behavior persists in some cases (`2931`, and oracle on `5414`/`6028`).
- Monitoring signals:
  - Track `error_instances` and `empty_patch_instances` in harness report per run.
  - Compare resolved IDs overlap between oracle and gm to separate retrieval vs patch bottlenecks.

## Follow-up

1. Investigate failure modes for `psf__requests-1142` and `psf__requests-1766` using `logs/run_evaluation/graphmanager_*/.../run_instance.log`.
2. Run a controlled patch-generation ablation (e.g., limited repair retries or increased `patch_max_turns`) on the same 8-instance set.
3. Proceed to 30-instance pilot only after selecting a stabilized config from the 8-instance diagnostics.
