# Evaluation Plan V2 (Cross-Benchmark, Cross-Domain)

Goal: produce publishable, reproducible evidence for quality + efficiency + amortization.

## Claims to prove

1. Quality: graph-guided retrieval is competitive with strong RAG baselines.
2. Efficiency: graph setup/query strategy lowers total token cost under repeated tasks.
3. Amortization: same-snapshot reuse yields materially better cost efficiency than strict track.
4. Policy efficiency: retrieval loop improvements reduce noise/tokens without quality collapse.

## Benchmark and domain matrix

Use both benchmark families and multiple domain types.

Manifested matrix file:
- `experiments_matrix_v2.yaml`

Current pinned repos:

1. SWE-bench (strict + same-snapshot for each)
- web framework: `pallets/flask`
- networking library: `psf/requests`
- testing/tooling: `pytest-dev/pytest`
- service framework: `tiangolo/fastapi`

2. SWE-PolyBench retrieval-first (strict + same-snapshot for each)
- app/CLI-heavy: `yt-dlp/yt-dlp` (`n=5`, dataset-limited diagnostic cell)
- framework/service-oriented: `langchain-ai/langchain`
- library-heavy: `keras-team/keras`

## Track definitions

1. Strict commit-fidelity
- each issue at its own `base_commit`
- no cross-commit leakage

2. Same-snapshot amortized
- fixed snapshot commit per repo
- identical issue list
- one setup reused across tasks

Report strict and same-snapshot separately. Never merge track means.

## Minimum run design

Per repo/track cell:

1. Fixed manifest with explicit `issue_set_id`
2. `n_issues >= 10` (primary table target)
3. Exception: `yt-dlp/yt-dlp` PolyBench cell is pinned at `n=5` because only 5 verified Python instances are available for that repo.
4. `repeats >= 3` (CI-ready gate)
5. same model/settings across compared methods

Primary methods for headline comparisons:

- `gm_progressive`
- `rag_progressive`
- `gm_baseline`
- `rag_baseline`

Raw methods can remain diagnostic unless quality is competitive.

## Statistics and gates

Per repeat aggregate:

1. paired deltas: `gm_progressive - rag_progressive` for mean F1
2. bootstrap 95% CI
3. gates:
- `min_repeats_met == true`
- `pairwise_bootstrap_available == true`
- `ci_ready == true`

No headline claim should use aggregates failing CI gates.

## Efficiency reporting block (required)

For each method:

1. mean F1
2. runtime tokens (`LLM + query embedding`)
3. setup embedding tokens
4. total cost tokens
5. tokens-per-F1 (where defined)

For each track:

1. `commit_repeat_ratio`
2. `cache_hit_rate`
3. pairwise break-even N

## Reproducibility contract

Every reported table must point to:

1. repeat-set json path
2. source run IDs
3. frozen bundle path under `research_report/artifacts/`

## Execution sequence

1. finalize manifest lists and `issue_set_id`s
2. run strict track repeats:
   - `./.venv/bin/python run_suite.py experiments_matrix_v2.yaml --only <strict cell indices>`
3. run same-snapshot repeats:
   - `./.venv/bin/python run_suite.py experiments_matrix_v2.yaml --only <snapshot cell indices>`
4. generate repeat aggregates and verify gates (automatic per cell from `run_suite.py`)
5. freeze artifacts and only then update report text
