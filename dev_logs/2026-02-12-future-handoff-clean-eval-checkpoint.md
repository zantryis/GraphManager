# Future Agent Handoff: Deterministic Retrieval + Clean Eval Checkpoint

Last updated: 2026-02-12
Project status: prototype (research-track, partial clean-root regeneration)

## What Was Completed

1. Deterministic retrieval implementation and wiring (`gm_deterministic`)
- New module: `src/deterministic_retrieval.py`
- Evaluation integration: `src/evaluation.py`
- Runner config plumbing: `run_experiment.py`, `run_suite.py`
- Viewer and artifact method support: `visualize_results.py`, `src/report_artifacts.py`

2. TDD and regression coverage
- Added deterministic retrieval tests: `tests/test_deterministic_retrieval.py`
- Updated integration tests for method/config/view/artifact handling:
  - `tests/test_evaluation_logic.py`
  - `tests/test_suite_config.py`
  - `tests/test_visualize_results.py`
  - `tests/test_report_artifacts.py`
- Full suite result:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - 61 tests passed.

3. Clean-root regeneration checkpoint
- Clean root: `results/clean_eval_20260211_193241/`
- API sanity checks passed (embedding + generation).
- Stage-1 minimal deterministic comparison completed.
- Phase A started with exact strict indices (`0,2,4,6`), first cell completed, second cell partially executed before interruption.

## Primary Artifacts (Current)

- Stage-1 minimal run summary:
  - `results/clean_eval_20260211_193241/runs/20260211_193305/summary.json`

- Completed repeat-set (Flask strict, CI-ready, 3 repeats):
  - `results/clean_eval_20260211_193241/repeat_sets/20260211_194653_swe_bench_pallets_flask_strict_commit_fidelity_issues_swebench_flask_v2_10.json`
  - source runs:
    - `results/clean_eval_20260211_193241/runs/20260211_193401/summary.json`
    - `results/clean_eval_20260211_193241/runs/20260211_193837/summary.json`
    - `results/clean_eval_20260211_193241/runs/20260211_194249/summary.json`

- Partial run directory (requests strict repeat-1, interrupted):
  - `results/clean_eval_20260211_193241/runs/20260211_194653/`

- Viewer regenerated from clean root:
  - `results/compare_matrix_v2.html`

- Frozen artifact bundle from completed runs only:
  - `research_report/artifacts/clean_eval_20260211_193241_partial/manifest.json`
  - `research_report/artifacts/clean_eval_20260211_193241_partial/summary_bundle.json`

## Phase Status (Exact)

### Phase A (strict indices: `0,2,4,6`)

- `0` (`pallets/flask`, strict): completed, repeat-set written, CI gates all true.
- `2` (`psf/requests`, strict): partial, interrupted during repeat 1 (`psf__requests-1713`, GM progressive call).
- `4` (`pytest-dev/pytest`, strict): not started.
- `6` (`tiangolo/fastapi`, strict): not started.

### Phase B (same-snapshot indices: `1,3,5,7`)

- not started.

### Phase C1 (PolyBench strict indices: `8,10,12`)

- not started.

### Phase C2 (PolyBench same-snapshot indices: `9,11,13`)

- not started.

## Interruption Record

- Approx interruption timestamp: `2026-02-11 19:51 -0700`
- Terminal traceback ended with:
  - `KeyboardInterrupt`
- Stack location at interruption:
  - `src/manager_agent.py` in `self.client.models.generate_content(...)`

## Quantitative Snapshot

### Stage-1 minimal strict comparison (`run_id=20260211_193305`)

- `gm_deterministic`: F1 `0.2857`, runtime tokens `57`, stop reason `deterministic_complete`
- `gm_progressive`: F1 `0.6667`, runtime tokens `7157`, stop reason `max_turns`
- `rag_progressive`: F1 `0.2857`, runtime tokens `4660`

### Completed strict repeat-set (Flask, 3 repeats, CI-ready)

- `gm_deterministic`: mean F1 `0.2781` (std `0.0000`), mean runtime tokens `1316`
- `gm_progressive`: mean F1 `0.6122` (std `0.0385`), mean runtime tokens `42101`
- `rag_progressive`: mean F1 `0.2610` (std `0.0601`), mean runtime tokens `15754.667`

Paired deltas (mean F1, bootstrap 95% CI):
- `gm_deterministic - gm_progressive`: `-0.3341` `[-0.3786, -0.3119]`
- `gm_deterministic - rag_progressive`: `+0.0171` `[-0.0505, +0.0643]` (inconclusive)
- `gm_progressive - rag_progressive`: `+0.3513` `[+0.2614, +0.4429]`

## Strict Vs Same-Snapshot Reporting (Separated)

### Strict track

| Cell | Status | CI gates | Key delta |
|---|---|---|---|
| SWE-bench Flask strict (`idx=0`) | Complete | all true | `gm_deterministic - gm_progressive = -0.3341` |
| SWE-bench Requests strict (`idx=2`) | Partial | n/a | interrupted before summary |
| SWE-bench Pytest strict (`idx=4`) | Not started | n/a | n/a |
| SWE-bench FastAPI strict (`idx=6`) | Not started | n/a | n/a |

### Same-snapshot track

No completed clean-root repeat-sets yet in this cycle.

## Recommended Next Commands (Resume)

1. Resume Phase A from remaining strict cells (re-run `2` cleanly + run `4,6`):
```bash
./.venv/bin/python run_suite.py experiments_matrix_v2.yaml \
  --results-dir results/clean_eval_20260211_193241 \
  --only 2,4,6
```

2. Run Phase B:
```bash
./.venv/bin/python run_suite.py experiments_matrix_v2.yaml \
  --results-dir results/clean_eval_20260211_193241 \
  --only 1,3,5,7
```

3. Run Phase C1 and C2:
```bash
./.venv/bin/python run_suite.py experiments_matrix_v2.yaml \
  --results-dir results/clean_eval_20260211_193241 \
  --only 8,10,12

./.venv/bin/python run_suite.py experiments_matrix_v2.yaml \
  --results-dir results/clean_eval_20260211_193241 \
  --only 9,11,13
```

4. After each phase, validate gates in `results/clean_eval_20260211_193241/repeat_sets/*.json` and regenerate:
```bash
./.venv/bin/python visualize_results.py \
  --results-dir results/clean_eval_20260211_193241 \
  --output results/compare_matrix_v2.html
```

5. Freeze only completed run summaries with explicit `--run` arguments.
