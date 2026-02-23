# 2026-02-19 - gm_deterministic Phase 1 runner + method-scoped evaluation

## Context

- Phase 1 tuning requires 60 coarse Flask configs, then top-10 reruns + holdout checks on Requests/Pytest.
- Existing evaluation path always executed all methods, which made tuning runs unnecessarily expensive and slow due agentic LLM calls.
- We needed a reproducible, resumable runner that can checkpoint and select a config artifact under the stability guard.

## Decision

- Added method-scoped execution support to retrieval evaluation:
  - `src/evaluation.py::run_experiment(..., methods=...)`
  - `run_experiment.py --methods` CLI flag.
- Updated commit-context validation/build to only require/build indices for enabled method families.
- Added Phase 1 orchestration script:
  - `tools/run_gm_deterministic_tuning_phase1.py`
  - runs baseline holdout (default config), coarse 60, top-k reruns, holdout checks, and writes selection artifacts.
- Launched Phase 1 protocol run with checkpoints:
  - `./.venv/bin/python tools/run_gm_deterministic_tuning_phase1.py --coarse-limit 60 --top-k 10 --max-drop 0.03`

Scope boundaries:
- Did not complete full Phase 1 to final selection in this session window (run is long and in progress).
- Did not start Phase 2 retrieval reruns or Phase 4 patching while tuning run is active.

## Alternatives Considered

1. Keep current all-method execution for tuning.
- Rejected: wastes tokens/time and violates practical tuning throughput.

2. Write a separate deterministic-only evaluator bypassing `run_experiment`.
- Rejected for now: duplicates evaluation logic and increases divergence risk.

3. Manual shell loops for 60+ runs.
- Rejected: no robust checkpoint/resume and hard to audit.

## Evidence

- Files changed:
  - `src/evaluation.py`
  - `run_experiment.py`
  - `tests/test_evaluation_logic.py`
  - `tools/run_gm_deterministic_tuning_phase1.py`
- Tests:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 134 tests passed.
- Smoke for method-scoped path:
  - `run_experiment.py --methods gm_deterministic ...` produced gm-only retrieval with zero LLM runtime for disabled methods.
- Phase 1 progress artifacts:
  - baseline holdout: `results/gm_deterministic_tuning/baseline_holdout_v1.json`
  - coarse checkpoint: `results/gm_deterministic_tuning/coarse_flask_v1.json`

## Consequences

- Tuning now runs with deterministic retrieval only, reducing runtime cost and making 60-config sweep feasible.
- Protocol artifacts are checkpointed and resumable mid-run.
- Selection can be made using a locked artifact that includes guard outcomes and leaderboard.

Known risks:
- Full Phase 1 wall-clock remains significant due per-candidate full 10-issue strict-track runs.
- If interrupted, resumed run relies on checkpoint integrity (JSON writes after each candidate).

Monitoring signals:
- `coarse_flask_v1.json` row count approaches 60.
- `final_candidates_v1.json` rows approach top-k.
- `selection_v1.json` emitted with `selected` and `n_guard_passing`.

## Follow-up

1. Let Phase 1 runner finish and verify `configs/gm_deterministic_selected_v1.json`.
2. Launch Phase 2 Gemini-3 retrieval reruns using selected deterministic config.
3. Freeze artifacts and fill gm_deterministic rows in report tables.
