# 2026-02-12 - Deterministic Retrieval Integration And Clean-Eval Attempt

## Context

- Implemented the `gm_deterministic` retrieval redesign from `docs/RETRIEVAL_REDESIGN_V1.md`.
- Required wiring across evaluation, suite runner config, viewer, and frozen artifact generation.
- Began clean-slate regeneration under `results/clean_eval_20260211_193241/` using `experiments_matrix_v2.yaml` phase indices.

Affected modules:
- `src/deterministic_retrieval.py`
- `src/evaluation.py`
- `run_experiment.py`
- `run_suite.py`
- `visualize_results.py`
- `src/report_artifacts.py`
- tests under `tests/`

## Decision

- Added deterministic graph-first retrieval as a first-class method: `gm_deterministic`.
- Kept existing methods unchanged (`gm_progressive`, `gm_baseline`, `rag_progressive`, `rag_baseline`, raw RAG variants) for comparability.
- Exposed deterministic traversal/scoring parameters in experiment and suite config plumbing:
  - `seed_k`, `depth`, `neighbor_cap`
  - `w_sem`, `w_graph`, `w_conf`, `w_hint`, `w_pen`
- Continued matrix execution from a clean root until partial checkpoint, then stopped phase execution after prolonged runtime to preserve completed artifacts and avoid an unbounded long-running terminal session.

Scope boundaries:
- Did not tune deterministic coefficients yet.
- Did not complete all matrix phases in this cycle.

## Alternatives Considered

1. Keep deterministic logic outside the evaluation method list
- Tradeoff: lower integration risk but no reproducible side-by-side comparison in main pipeline.

2. Replace existing progressive manager with deterministic mode
- Tradeoff: simpler code surface but breaks baseline comparability and prior evidence continuity.

3. Complete the entire matrix in one uninterrupted run
- Tradeoff: ideal for freshness, but wall-clock runtime is multi-hour; partial checkpointing was preferred for reliable handoff.

## Evidence

- Full unit suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 61 tests passed.

- Stage-1 minimal strict comparison run:
  - `results/clean_eval_20260211_193241/runs/20260211_193305/summary.json`

- Completed repeat-set (Phase A cell, Flask strict, 3 repeats, CI-ready):
  - `results/clean_eval_20260211_193241/repeat_sets/20260211_194653_swe_bench_pallets_flask_strict_commit_fidelity_issues_swebench_flask_v2_10.json`

- Partial interrupted run checkpoint (Requests strict repeat-1 in progress):
  - `results/clean_eval_20260211_193241/runs/20260211_194653/`

- Interruption/error trace captured at approximately `2026-02-11 19:51 -0700`:
  - Terminal traceback ended with `KeyboardInterrupt` during `ManagerAgent.find_relevant_files` API generation call.

- Regenerated viewer and frozen artifact bundle (completed runs only):
  - `results/compare_matrix_v2.html`
  - `research_report/artifacts/clean_eval_20260211_193241_partial/manifest.json`

## Consequences

- Positive:
  - Deterministic retrieval is now runnable in all experiment/suite flows with reproducible scoring traces.
  - Clean-root evidence exists and includes one CI-ready strict cell with paired bootstrap deltas.
  - Viewer and artifact pipeline can include deterministic method outputs.

- Risks:
  - Current clean-root evidence is phase-partial; same-snapshot and PolyBench tracks are incomplete.
  - Deterministic defaults underperform `gm_progressive` on the completed Flask strict repeat-set.

- Monitoring signals:
  - Repeat-set gates per cell (`min_repeats_met`, `pairwise_bootstrap_available`, `ci_ready`).
  - Paired deltas for `gm_deterministic` vs `gm_progressive` and `rag_progressive` across additional repos/tracks.

## Follow-up

1. Resume clean-root phase execution with explicit remaining indices:
- Phase A remaining strict cells: `2,4,6` (re-run to completion for consistency).
- Phase B: `1,3,5,7`
- Phase C1: `8,10,12`
- Phase C2: `9,11,13`

2. Keep phase-level logs with timestamps and exact exception text if interrupted again.

3. After each completed cell, verify repeat-set gates and regenerate:
- `results/compare_matrix_v2.html`
- `research_report/artifacts/<new_id>/...`

4. Run deterministic coefficient tuning only after broader strict/snapshot coverage is available.
