# 2026-02-19 - gm_deterministic Strict Reruns (Flask/Requests/Pytest)

## Context

- Phase 1 tuning completed earlier in the day and froze `cfg-0054` at `configs/gm_deterministic_selected_v1.json`.
- Workstream A still lacked Gemini-3 gm_deterministic reruns for paper-minimum retrieval rows.
- User approved proceeding with execution immediately.

## Decision

- Execute paper-minimum strict reruns first for the 3 anchor repos using:
  - `--methods gm_deterministic`
  - `--deterministic-config-path configs/gm_deterministic_selected_v1.json`
- Keep runs single-pass (`repeats=1`) to unblock table population and next-stage planning.
- Scope boundary: this step does not complete same-snapshot reruns or extended matrix repos.

## Alternatives Considered

1. Run full suite with `run_suite.py`.
Main tradeoff: would rerun all methods (not just gm_deterministic), increasing cost and time.
2. Run strict + same-snapshot for all repos in one batch now.
Main tradeoff: more complete immediately, but slower to unblock current reporting milestone.
3. Wait and batch all remaining gm_deterministic cells later.
Main tradeoff: keeps state cleaner but delays downstream paper/table work.

## Evidence

- Commands executed:
  - `./.venv/bin/python run_experiment.py --repo-name pallets/flask --source-prefix src/flask --n-issues 10 --manager-max-turns 6 --rag-max-turns 6 --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json --notes gm-deterministic-rerun-selected-v1`
  - `./.venv/bin/python run_experiment.py --repo-name psf/requests --source-prefix requests --n-issues 10 --manager-max-turns 6 --rag-max-turns 6 --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json --notes gm-deterministic-rerun-selected-v1`
  - `./.venv/bin/python run_experiment.py --repo-name pytest-dev/pytest --source-prefix src/_pytest --source-prefix src/pytest --n-issues 10 --manager-max-turns 6 --rag-max-turns 6 --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json --notes gm-deterministic-rerun-selected-v1`
- Run outputs:
  - `results/runs/20260218_220114/summary.json` (Flask strict): F1 `0.6785714285714286`, query tokens `1316`, setup tokens `153750`
  - `results/runs/20260218_220148/summary.json` (Requests strict): F1 `0.52`, query tokens `1727`, setup tokens `107557`
  - `results/runs/20260218_220227/summary.json` (Pytest strict): F1 `0.47333333333333333`, query tokens `2361`, setup tokens `439747`

## Consequences

- Paper-minimum strict gm_deterministic rows for Flask/Requests/Pytest are now available from Gemini-3 runs.
- Workstream C can populate strict Table 1 gm_deterministic entries without waiting on same-snapshot reruns.
- Remaining gap: same-snapshot gm_deterministic reruns (and any extended matrix cells still required by final scope).

## Follow-up

1. Run same-snapshot gm_deterministic reruns for Flask/Requests/Pytest with pinned snapshot commits.
2. Update retrieval tables/figures to use new strict rerun artifacts.
3. Reconcile "7 pending cells" bookkeeping with executed strict runs and lock remaining cell list.
