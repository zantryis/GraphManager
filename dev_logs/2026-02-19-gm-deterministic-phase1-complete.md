# 2026-02-19 - gm_deterministic Phase 1 Completed (cfg-0054 selected)

## Context

- Workstream A required completion of Phase 1 deterministic tuning before Gemini-3 reruns of missing gm_deterministic cells.
- Previous run had been interrupted by API limits and resumed from checkpoints.
- This session resumed `tools/run_gm_deterministic_tuning_phase1.py` and monitored it through artifact freeze.

## Decision

- Keep the existing Phase 1 protocol unchanged and complete it from checkpoints:
  - `coarse-limit=60`, `top-k=10`, `max-drop=0.03`
  - 3 Flask repeats per top candidate + Requests/Pytest holdout checks
- Freeze selected config exactly as produced by selector (no manual edits).
- Scope boundary: this log does not execute the gm_deterministic reruns; it only finalizes tuning/selection artifacts.

## Alternatives Considered

1. Restart Phase 1 from scratch.
Main tradeoff: cleaner single run history, but unnecessary extra cost/time versus checkpoint resume.
2. Manually pick a config from coarse leaderboard.
Main tradeoff: faster but violates reproducible selection/guard protocol.
3. Relax holdout guard to force a higher Flask config.
Main tradeoff: risks overfitting and weakens claim discipline.

## Evidence

- Resume command:
  - `./.venv/bin/python tools/run_gm_deterministic_tuning_phase1.py --coarse-limit 60 --top-k 10 --max-drop 0.03`
- Completion signals:
  - `results/gm_deterministic_tuning/final_candidates_v1.json` has 10 rows
  - `results/gm_deterministic_tuning/selection_v1.json` exists
  - `configs/gm_deterministic_selected_v1.json` exists
- Selected result summary:
  - `config_id=cfg-0054`
  - Flask train mean F1 `0.6785714285714285`, std `0.0`
  - Holdout scores: Requests `0.52`, Pytest `0.47333333333333333`
  - Baseline scores: Requests `0.43`, Pytest `0.45`
  - Holdout deltas: Requests `+0.09`, Pytest `+0.023333...`
  - `passes_stability_guard=true`

## Consequences

- Phase 1 gate is now satisfied: a locked deterministic config is available for all reruns.
- Workstream A bottleneck shifts from tuning to execution of missing gm_deterministic matrix cells.
- Risk: gm_deterministic reruns may still drift due model/API variance; report must cite frozen artifact and run IDs.

## Follow-up

1. Run gm_deterministic reruns on Flask/Requests/Pytest with `--deterministic-config-path configs/gm_deterministic_selected_v1.json`.
2. Validate new rerun artifacts are Gemini-3 and aligned with matrix tracks used in Paper 1.
3. Update retrieval tables and mark gm_deterministic rows as complete in `CURRENT_STATE.md` once reruns finish.
