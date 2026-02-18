# 2026-02-18 - psf/requests Patch Run (Complete, Evaluated)

## Context

- Goal: execute the full patch pipeline for `psf/requests` SWE-bench Verified manifest and record pass@1.
- Blocking issue: repeated Gemini `429 RESOURCE_EXHAUSTED` failures aborted earlier runs before harness evaluation.
- Affected files/modules:
  - `run_patch.py`
  - `src/patch_agent.py`
  - `patch_manifests/swebench_verified_requests_v1.yaml`
  - `tests/test_patch_runner.py`
  - `tests/test_patch_agent.py`

## Decision

- Added explicit transient API retry/backoff handling in `run_patch.py` with configurable manifest knobs.
- Added manifest-level model selection (`manager_model`, `patch_model`) and used:
  - manager: `gemini-3-flash-preview`
  - patch: `gemini-2.5-flash`
- Added patch extraction fallback for raw unified diffs without `<patch>...</patch>` wrappers in `src/patch_agent.py`.
- Kept scope bounded:
  - no retrieval evaluation reruns,
  - no `langchain` cell changes,
  - no `gm_deterministic` tuning.

## Alternatives Considered

1. Keep current pipeline behavior and retry manually after each 429.
   - Tradeoff: high operator load, frequent incomplete runs.
2. Use `gemini-2.5-pro` for patching.
   - Tradeoff: better potential quality, but in this setup it repeatedly returned `MAX_TOKENS` with no usable patch text.
3. Pause until quota reset and avoid code changes.
   - Tradeoff: no reproducible mitigation for transient throttling; still brittle.

## Evidence

- Test outputs:
  - `./.venv/bin/python -m unittest discover -s tests -v` → `96` tests passed.
- Patch run artifacts:
  - `results/patch_runs/20260218_120541/patch_summary.json`
  - `graphmanager-gm_progressive.graphmanager_20260218_120541.json`
- Run summary (`20260218_120541`):
  - Instances: `8`
  - Non-empty patches: `8/8` (`100.0%`)
  - Harness: `1 resolved`, `3 unresolved`, `4 patch-apply errors`
  - Pass@1 resolved rate: `1/8` (`12.5%`)

## Consequences

- Benefits:
  - End-to-end patch run now completes under transient API pressure.
  - Model/policy controls are explicit and reproducible in manifest.
  - Patch extraction is more tolerant to model output format variance.
- Risks:
  - Patch quality remains unstable; apply failures are currently the dominant failure mode.
  - Harness report path emitted by SWE-bench may differ from expected in-run parser path.
- Monitoring signals:
  - `n_patched`, `resolved_instances`, `error_instances` in run outputs.
  - frequency of `patch unexpectedly ends in middle of line` apply errors.

## Follow-up

1. Add pre-harness patch validation (`git apply --check`) and regeneration loop for malformed diffs.
2. Add robust harness report path discovery/parsing in `run_patch.py`.
3. Re-run the same manifest with the validated-patch loop and compare:
   - apply-error rate,
   - pass@1 resolved rate,
   - token/time overhead.
