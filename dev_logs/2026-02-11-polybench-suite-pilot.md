# 2026-02-11 - PolyBench Suite Wiring And Pilot Run

## Context

- `EVALUATION_SPEC.md` recommends retrieval-first evaluation on SWE-PolyBench as Phase A.
- `run_suite.py` previously ignored dataset family/name fields, so suite configs could not actually target PolyBench.
- Affected files:
  - `run_suite.py`
  - `tests/test_suite_config.py`
  - `experiments_polybench.yaml`

## Decision

- Extend suite resolution/execution to propagate `task_family` and `dataset_name` into `run_experiment`.
- Add a small PolyBench pilot suite (`experiments_polybench.yaml`) for retrieval validation before scaling.
- Keep pilot size small (`n_issues=3`, `max_turns=4`) to control exploratory token spend.

## Alternatives Considered

1. Run PolyBench only via `run_experiment.py` one-off CLI flags.
Tradeoff: works ad hoc but not reproducible in suite workflow.

2. Hardcode PolyBench into existing `experiments.yaml`.
Tradeoff: mixes benchmark families and makes historical comparison noisy.

3. Add generic suite wiring + dedicated PolyBench config file.
Tradeoff: one-time code change, but clearer and reusable evaluation setup.

## Evidence

- New/updated tests:
  - `tests/test_suite_config.py::test_resolve_experiment_includes_dataset_family_defaults`
  - `tests/test_suite_config.py::test_resolve_experiment_allows_dataset_family_override`
- Full tests passing:
  - `./.venv/bin/python -m unittest discover -s tests -v` (44/44)
- Pilot run command:
  - `./.venv/bin/python run_suite.py experiments_polybench.yaml --results-dir results`
- Pilot artifact:
  - `results/runs/20260211_162555`

## Consequences

- Suite runner now supports SWE-bench and SWE-PolyBench from YAML config.
- PolyBench retrieval pilot is reproducible and visible in dashboard.
- Pilot quality is currently weak on `yt-dlp/yt-dlp`, indicating scaling requires policy/index tuning rather than immediate benchmark expansion.

## Follow-up

1. Add PolyBench-focused low-context retrieval mode (smaller snippet payloads, stricter tool-call cap).
2. Add a non-LLM graph baseline for cleaner attribution of graph value vs manager policy.
3. Expand PolyBench pilot to a second Python repo (`keras-team/keras` or `langchain-ai/langchain`) with fixed manifest.
