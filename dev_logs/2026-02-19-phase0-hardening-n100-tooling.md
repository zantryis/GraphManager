# 2026-02-19 - Phase 0 Hardening + N100 Split/Manifest Tooling

## Context

- User requested implementation of the paper-ready master plan, including:
  - aggressive bounded backoff,
  - gm_deterministic coefficient-tuning interface,
  - N=100 SWE-bench Verified patching split/manifest freeze,
  - cost-per-resolved-ready summary fields,
  - B5/B6 fixes as mandatory gates.
- Repository already had substantial Workstream B rerun history and existing requests/flask/pytest manifests.

## Decision

- Implement the plan in two executable layers:
  1. **Runtime hardening + schema changes** in patching pipeline (`run_patch.py`, `src/patch_agent.py`, manifests, tests).
  2. **Reproducibility tooling** for deterministic tuning and N=100 split/manifests (`src/deterministic_*`, `tools/*`, split + ledger artifacts).
- Keep heavy experiment execution (full N=100 patching runs and full retrieval reruns) as next actions; do not block implementation delivery on long-running API jobs.

## Alternatives Considered

1. Implement only docs/planning and defer code changes.
   Tradeoff: low immediate risk, but no runnable protocol hardening.
2. Execute large-scale runs first, then harden code based on failures.
   Tradeoff: high compute waste and confounded diagnostics.
3. Implement hardening + deterministic artifact generation first (chosen).
   Tradeoff: requires broader code touch, but yields immediate reproducible run readiness.

## Evidence

### Code/Config changes

- `run_patch.py`
  - Added per-call hard deadline support in `_run_with_rate_limit_backoff(..., deadline_monotonic=...)`, including blocking-call timeout behavior.
  - Added `_compute_cost_summary_fields(...)` and summary schema fields:
    `retrieval_setup_tokens`, `retrieval_runtime_tokens`, `patch_runtime_tokens`, `total_cost_tokens`, `n_resolved`, `resolved_instances`, `cost_per_resolved_issue`.
  - Added manifest knobs:
    `instance_wall_clock_cap_s`, `patch_redact_paths_in_issue_text`, `retrieval_redact_paths_in_issue_text`.
  - Added timeout status propagation: `timeout_budget_exceeded`.
- `src/patch_agent.py`
  - B6 fix: no longer short-circuits on empty file list; now performs issue-only model call.
  - Prompt now explicitly states when no repository files are provided.
- Patch manifests updated (`patch_manifests/swebench_verified_*.yaml`)
  - Backoff policy pinned to:
    `max_retries=2`, `initial_delay=0.5`, `multiplier=1.7`, `max_delay=5.0`, `jitter=0.2`.
  - Repair/retrieval policy pinned to:
    `patch_apply_repair_retries=1`, `patch_retrieval_retry_max=0`, `patch_max_turns=1`.
  - Added:
    `instance_wall_clock_cap_s=480`, `patch_redact_paths_in_issue_text=false`,
    `retrieval_redact_paths_in_issue_text=true`.

### New deterministic tuning interface

- `src/deterministic_config.py`
  - JSON/YAML loader + validator for machine-loadable gm_deterministic configs.
- `run_experiment.py`
  - Added `--deterministic-config-path`; overrides deterministic CLI knobs from file.
- `run_suite.py`
  - Added `deterministic_config_path` support in suite resolution and metadata.
- `src/deterministic_tuning.py`
  - Candidate sampler + stability guard + selector utilities.
- `tools/tune_gm_deterministic.py`
  - `sample` and `select` subcommands for candidate generation and frozen config selection.

### New N=100 split/manifest tooling

- `src/patch_study_split.py`
  - Deterministic split allocator with anchor continuity + capped extras.
- `tools/generate_n100_verified_manifests.py`
  - Generates frozen N=100 split JSON and per-repo/per-method manifests + hash ledger.
- Generated artifacts:
  - `patch_manifests/verified_n100_split_v1.json`
  - `patch_manifests/n100_verified/manifest_ledger_v1.json`
  - `patch_manifests/n100_verified/*_v1.yaml` (9 repos × 4 methods).

### Tests

- New tests:
  - `tests/test_deterministic_config.py`
  - `tests/test_deterministic_tuning.py`
  - `tests/test_patch_study_split.py`
- Updated tests:
  - `tests/test_patch_agent.py`
  - `tests/test_patch_runner.py`
  - `tests/test_suite_config.py`
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: **126 tests passed**.

### Smoke behavior checks

- Attempted evaluated smoke run (flask none): `results/patch_runs/20260218_193903` stalled in live API call (terminated).
- Non-evaluated short-cap smoke (temporary manifest in `/tmp`) confirmed timeout path and new schema:
  - Run: `/tmp/patch_runs/20260218_194651/patch_summary.json`
  - `patch_status=timeout_budget_exceeded`
  - New cost/summary fields present.

## Consequences

- Expected benefits:
  - Patch pipeline now enforces bounded runtime behavior and emits money-table-ready summaries.
  - N=100 study can be executed reproducibly from frozen split + hashed manifests.
  - gm_deterministic tuning outputs are now machine-loadable into retrieval reruns.
- Known risks:
  - Live model calls may still stall intermittently in this environment; timeout path now limits per-instance impact.
  - Heavy compute phases (full reruns and N=100 patch execution) remain pending.
- Monitoring signals:
  - Frequency of `timeout_budget_exceeded` in patch summaries.
  - `cost_per_resolved_issue` completeness and null-rate (`n_resolved=0`).
  - Deterministic config traceability in `_meta.deterministic_retrieval`.

## Follow-up

1. Execute oracle-first N=100 patching runs from `patch_manifests/n100_verified/`.
2. Run gm_deterministic tuning evaluation loop, then freeze selected config for Gemini-3 retrieval reruns.
3. Populate paper tables from frozen artifacts only (run IDs + manifest hashes).
