# 2026-02-18 - B9 Thinking-Budget Fix Validation (Oracle + GM Reruns)

## Context

- Bug B9 was identified as a patch-generation budget issue for `gemini-3-flash-preview`.
- Root cause: Gemini 3 is a thinking model; `max_output_tokens` is shared between hidden reasoning and visible output text.
- With `patch_max_output_tokens=12288`, three requests instances (`psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`) consumed most budget in thinking and repeatedly ended with ~490 visible output tokens, causing `no_patch` extraction failures.
- Fix applied before this run pair: `patch_max_output_tokens` raised to `65536` in patch manifests (and intended as the new default policy).

## Decision

- Validate B9 by rerunning oracle first, then conditionally rerunning `gm_progressive` only if oracle resolved >= 4/8.
- Keep other run controls unchanged (same 8-instance requests set, same zero-shot gm manifest).
- Scope boundaries:
  - No retrieval-eval reruns.
  - No 30-instance expansion in this step.

## Alternatives Considered

1. Keep `12288` and add retries/repair loops.

Tradeoff: may reduce some apply failures, but does not address fundamental output truncation from thinking-budget exhaustion.

2. Switch patch model away from thinking model.

Tradeoff: could avoid this class of issue, but changes core model axis and confounds current ablation lineage.

3. Raise `patch_max_output_tokens` substantially (chosen).

Tradeoff: higher token spend/latency, but directly unblocks full patch emission.

## Evidence

- Pre-run status docs read:
  - `CURRENT_STATE.md`
  - `RESEARCH_INTENT.md`
- Docker ready: `docker ps` succeeded.
- B9 settings confirmed in manifests:
  - `patch_manifests/swebench_verified_requests_oracle_v1.yaml` (`patch_max_output_tokens: 65536`)
  - `patch_manifests/swebench_verified_requests_v1.yaml` (`patch_max_output_tokens: 65536`)

### Before/After (Oracle)

- Pre-B9 oracle (new model/file-context, old token cap):
  - Run `20260218_163915`
  - `resolved=3/8` (37.5%), `n_patched=2/8`, `apply_success_rate=0.4000`
  - `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`: `no_patch` with `FinishReason.MAX_TOKENS`

- B9 oracle rerun:
  - Command: `./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_oracle_v1.yaml --evaluate`
  - Run `20260218_172903`
  - Artifacts:
    - `results/patch_runs/20260218_172903/patch_summary.json`
    - `results/patch_runs/20260218_172903/predictions.json`
    - `graphmanager-oracle.graphmanager_20260218_172903.json`
  - Metrics:
    - `resolved=4/8` (50.0%)
    - `n_patched=6/8`
    - `apply_success_rate=0.7500`
  - Resolved IDs:
    - `psf__requests-1142`, `psf__requests-1724`, `psf__requests-1766`, `psf__requests-2317`
  - B9-affected IDs now produce patches (`patch_status=patched`, `stop_reason=FinishReason.STOP`):
    - `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`

### GM Progressive Rerun (post-gate)

- Gate condition met: oracle resolved `4/8` (>= 4/8), so gm run executed.
- Command: `./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml --evaluate`
- Run `20260218_175605`
- Artifacts:
  - `results/patch_runs/20260218_175605/patch_summary.json`
  - `results/patch_runs/20260218_175605/predictions.json`
  - `graphmanager-gm_progressive.graphmanager_20260218_175605.json`
- Metrics:
  - `resolved=2/8` (25.0%)
  - `n_patched=5/8`
  - `apply_success_rate=0.6250`
- Resolved IDs:
  - `psf__requests-1724`, `psf__requests-1766`
- B9-affected IDs also now patch in gm run (`stop_reason=FinishReason.STOP`):
  - `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`

## Consequences

- Expected benefits:
  - B9 fix is validated: emission bottleneck from MAX_TOKENS was removed for the target three instances.
  - Oracle ceiling improved from `3/8` to `4/8` under otherwise comparable upgraded settings.
- Known risks:
  - GM resolved rate did not improve (remained `2/8`) despite better patch emission/apply rates.
  - Remaining unresolveds are now primarily semantic correctness/hunk quality issues, not empty/no-patch failures.
- Monitoring signals:
  - `empty_patch_instances` should remain near zero with `65536` budget.
  - Track malformed/apply failures in harness logs (`1142`, `1921`) and unresolved-after-apply instances.

## Follow-up

1. Analyze `logs/run_evaluation/graphmanager_20260218_175605/` for unresolved patched instances (`2931`, `5414`, `6028`) to separate semantic vs formatting failures.
2. Run a targeted patch-quality ablation (e.g., non-zero repair retries or limited multi-turn patching) on the same 8-instance set.
3. Use stabilized settings to proceed toward 30-instance pilot only after resolving recurring malformed patch failures.
