# 2026-02-18 - Phase 0/1 Patch Robustness + Harness Capture (requests manifest)

## Context

- Scope: implement only Phase 0 and Phase 1 from `dev_logs/2026-02-18-end-to-end-improvement-plan.md`.
- Constraints honored:
  - no `run_experiment.py` / retrieval matrix reruns,
  - no langchain cell changes,
  - no `gm_deterministic` logic changes.
- Main issues addressed:
  - patch applicability was not validated before statusing as patched,
  - no automated repair/retrieval fallback loop on invalid patches,
  - harness summary stayed `null` despite completed evaluation,
  - patch/output/file-size knobs not fully manifest-driven.

## Decision

- Added manifest-level knobs and wired into runner/agent:
  - `manager_max_turns`
  - `patch_max_output_tokens`
  - `patch_max_file_chars`
- Added bounded robustness flow:
  - `git apply --check` validation post-generation,
  - repair retries with apply stderr context (max 2),
  - retrieval retry with failure feedback (max 1).
- Added run-level patch robustness metrics in `patch_summary.json`:
  - `n_apply_ok`
  - `n_apply_failed`
  - `apply_success_rate`
- Fixed harness result capture to support actual SWE-bench report outputs (including top-level `graphmanager-*.graphmanager_<run_id>.json`) with fallback parsing from per-instance reports.
- Updated manifest defaults in `patch_manifests/swebench_verified_requests_v1.yaml`:
  - `manager_max_turns: 8`
  - `patch_max_output_tokens: 12288`
  - `patch_max_file_chars: 12000`
  - `api_timeout_s: 300`

Scope boundaries:
- Did not change `gm_deterministic`.
- Did not do MAS/productization work.

## Alternatives Considered

1. Keep hardcoded patch/retrieval limits and only parse harness differently.
Tradeoff: leaves truncation/cutoff behavior and invalid patch labeling unresolved.

2. Add unbounded repair/retrieval retries.
Tradeoff: can hide failures and blow up cost/latency; rejected for determinism.

3. Retry-only without `git apply --check`.
Tradeoff: cannot distinguish text output from applicable diff; rejected.

## Evidence

- TDD (Phase 1): added failing-first tests in `tests/test_patch_runner.py` for:
  - apply check pass/fail classification,
  - repair retry + max-cap behavior,
  - retrieval retry trigger + cap behavior,
  - summary metrics (`n_apply_ok`, `n_apply_failed`, `apply_success_rate`).
- Full unit suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - result: `Ran 104 tests ... OK`.
- Ablation on exactly 3 fixed requests IDs:
  - IDs: `psf__requests-1142`, `psf__requests-1921`, `psf__requests-6028`
  - Run `20260218_132351` (`manager_max_turns=8`, `patch_max_output_tokens=8192`, `patch_max_file_chars=12000`):
    - retrieval stop reasons: all `budget`
    - patch stop reasons: one `FinishReason.MAX_TOKENS` (1142), others `FinishReason.STOP`
  - Run `20260218_132608` (`manager_max_turns=8`, `patch_max_output_tokens=12288`, `patch_max_file_chars=12000`):
    - retrieval stop reasons: all `budget`
    - patch stop reasons: all `FinishReason.STOP` (no `MAX_TOKENS`)
- Full 8-instance evaluated verification run:
  - run id: `20260218_133013`
  - summary: `results/patch_runs/20260218_133013/patch_summary.json`
  - harness report path discovered/captured:
    - `graphmanager-gm_progressive.graphmanager_20260218_133013.json`
  - metrics:
    - `n_apply_ok=2`
    - `n_apply_failed=6`
    - `apply_success_rate=0.25`
    - `harness_results.n_resolved=0` (`0/8`)
  - stop-reason checks:
    - retrieval: not universally `max_turns` (all `budget`)
    - patch: zero `FinishReason.MAX_TOKENS` in this run.

## Consequences

- Benefits:
  - patch status now distinguishes applicable vs non-applicable diffs,
  - automated repair and retrieval fallback is bounded and deterministic,
  - harness metrics are now captured in summary for evaluated runs,
  - manifest can tune core patching/retrieval budget knobs reproducibly.
- Risks:
  - apply success remains low on the current 8-instance run (`25%`),
  - long API calls still dominate wall-clock despite timeout guard.
- Monitoring signals:
  - `patch_status` distribution (`patched` vs `apply_failed`),
  - `apply_success_rate`,
  - patch/retrieval stop reasons,
  - harness `n_resolved` and `resolved_instances`.

## Follow-up

1. Keep Phase 2+ work out of this change set; next should be isolated.
2. If improving apply success, target prompt/repair context quality while keeping bounded retries.
3. Re-run evaluated manifest after any prompt/repair changes and compare paired deltas on `apply_success_rate` and `resolved_rate`.
