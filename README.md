# Graph-Augmented Manager

**Can agentic navigation over a structured code graph compete with or beat vector-search RAG for file-level issue localization?**

This project evaluates graph-guided retrieval versus RAG baselines on real [SWE-bench](https://www.swebench.com/) issues, with explicit quality and token-cost accounting.

## Architecture

```
GitHub Issue ──▶ Retrieval Agent ──▶ Relevant Files
                 (Gemini + tools)
                       │
            Knowledge Graph or RAG Index
```

## Methods

Six methods are evaluated on the same issue sets:

| Method | Strategy | LLM? |
|---|---|---|
| `gm_progressive` | Graph Manager, constrained/progressive tool use | Yes |
| `gm_baseline` | Graph Manager, exploratory baseline tool use | Yes |
| `rag_progressive` | RAG Agent, constrained/progressive search | Yes |
| `rag_baseline` | RAG Agent, exploratory baseline search | Yes |
| `raw_rag_function` | Pure vector similarity over function chunks | No |
| `raw_rag_fixed` | Pure vector similarity over fixed-size chunks | No |

Both agentic families use the same model (`gemini-2.0-flash`) and comparable prompting, changing only the retrieval backend and tool interface.

## Knowledge Graph

Built from static AST analysis (`tree-sitter`):

- Nodes: files, classes, functions
- Edges: `DEFINES`, `IMPORTS`, `CALLS`, `CONTAINS`, `INHERITS`
- Semantic entry: FAISS over node text (names/docstrings/signatures)

## Evaluation Protocol (Current)

- Dataset support: `SWE-bench/*` and `AmazonScience/SWE-PolyBench_*` (via adapters in `src/datasets/`)
- Metric target: file-level precision/recall/F1 with explicit error accounting
- Cost accounting: `setup_embedding_tokens + total_query_embedding_tokens + total_llm_tokens`
- Track separation: strict commit-fidelity vs same-snapshot amortized
- Repeat statistics: paired deltas + bootstrap CI via repeat-set aggregates

## Latest Validated Evidence (2026-02-18)

Frozen artifact bundle (11 valid cells, all `ci_ready=True`, 3 repeats each):

- `research_report/artifacts/frozen-20260212-matrix-v2-clean/manifest.json`
- `research_report/artifacts/frozen-20260212-matrix-v2-clean/summary_bundle.json`

Results directory: `results/clean_eval_20260211_201431/`

Repeat sets: `results/clean_eval_20260211_201431/repeat_sets/`

> **Note on langchain-ai/langchain:** The langchain strict cell is excluded (`valid: false`) because
> `source_prefixes: [libs/langchain]` matched no Python files at the pinned commit (the monorepo
> layout didn't exist yet at that commit). The correct prefix is `[langchain]`. The repeat set file
> is preserved but flagged invalid and filtered from all dashboard views.

### Headline: GM-progressive vs RAG-progressive (gm_progressive − rag_progressive, mean F1 delta, bootstrap 95% CI)

| Repo | Track | GM F1 | RAG F1 | Delta | 95% CI |
|---|---|---:|---:|---:|---|
| pallets/flask | strict | 0.654 | 0.354 | +0.301 | [+0.211, +0.415] |
| psf/requests | strict | 0.456 | 0.267 | +0.189 | [+0.130, +0.280] |
| pytest-dev/pytest | strict | 0.502 | 0.452 | +0.051 | [−0.015, +0.103] ¹ |
| tiangolo/fastapi | strict | 0.480 | 0.411 | +0.069 | [+0.028, +0.128] |
| yt-dlp/yt-dlp | strict | 0.382 | 0.163 | +0.219 | [+0.133, +0.267] |
| keras-team/keras | strict | 0.319 | 0.140 | +0.179 | [+0.095, +0.255] |
| pallets/flask | same-snapshot | 0.740 | 0.341 | +0.399 | [+0.361, +0.461] |
| psf/requests | same-snapshot | 0.544 | 0.308 | +0.237 | [+0.233, +0.238] |
| pytest-dev/pytest | same-snapshot | 0.570 | 0.499 | +0.071 | [+0.015, +0.128] |
| tiangolo/fastapi | same-snapshot | 0.530 | 0.412 | +0.119 | [+0.098, +0.151] |
| yt-dlp/yt-dlp | same-snapshot | 0.391 | 0.217 | +0.174 | [+0.097, +0.280] |

¹ Inconclusive (CI spans zero). All other deltas have CI entirely above zero.

All strict SWE-bench cells have `commit_repeat_ratio=0.0` (each issue at its own commit).
Same-snapshot cells have `commit_repeat_ratio≥0.8` (world-model reuse enabled by design).

## End-to-End Patching (2026-02-18)

| Run ID | Repo | Instances | Patch rate | Resolved rate (Pass@1) | Harness outcomes | Retrieval method | Models |
|---|---|---:|---:|---:|---|---|---|
| `20260218_120541` | `psf/requests` | 8 | 8/8 (100.0%) | 1/8 (12.5%) | 1 resolved, 3 unresolved, 4 patch-apply errors | `gm_progressive` | manager=`gemini-3-flash-preview`, patch=`gemini-2.5-flash` |

Artifacts:
- Patch summary: `results/patch_runs/20260218_120541/patch_summary.json`
- SWE-bench harness report: `graphmanager-gm_progressive.graphmanager_20260218_120541.json`

## Quick Start

```bash
git clone <repo-url> && cd GraphManager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set GEMINI_API_KEY=...
```

## Run Experiments

Single-repo run:

```bash
./.venv/bin/python run_experiment.py \
  --repo-name pallets/flask \
  --source-prefix src/flask \
  --n-issues 10 \
  --manager-max-turns 6 \
  --rag-max-turns 6
```

Multi-repo suite:

```bash
./.venv/bin/python run_suite.py experiments.yaml
```

Cross-benchmark matrix (manifest-pinned, strict + same-snapshot):

```bash
./.venv/bin/python run_suite.py experiments_matrix_v2.yaml
```

## Visualize

```bash
./.venv/bin/python visualize_results.py
# writes results/compare.html
```

By default this excludes stale legacy runs and superseded reruns (latest per config only).  
Use `--include-stale` to inspect all historical runs:

```bash
./.venv/bin/python visualize_results.py --include-stale --output results/compare_with_stale.html
```

You can also render a specific run directory:

```bash
./.venv/bin/python visualize_results.py --run results/clean_eval_20260211_201431
```

Render a specific repeat aggregate (useful for strict vs same-snapshot amortization views):

```bash
# Flask strict
./.venv/bin/python visualize_results.py \
  --run results/clean_eval_20260211_201431/repeat_sets/20260211_202654_swe_bench_pallets_flask_strict_commit_fidelity_issues_swebench_flask_v2_10.json \
  --output results/flask_strict_compare.html

# Flask same-snapshot
./.venv/bin/python visualize_results.py \
  --run results/clean_eval_20260211_201431/repeat_sets/20260211_203650_swe_bench_pallets_flask_same_snapshot_amortized_issues_swebench_flask_v2_10.json \
  --output results/flask_snapshot_compare.html
```

The dashboard now includes:

- `Global Cost-Quality Frontier` (cross-run tradeoff landscape)
- `Tradeoff Outliers` (worst tokens/F1 regime points)
- `Regime Shift Detector` (strict vs same-snapshot deltas by method)
- run-level cards for amortization, CI gates, and manager telemetry

## Project Structure

```
run_experiment.py          Single experiment runner
run_suite.py               Suite runner from YAML config
visualize_results.py       HTML dashboard generator
src/
  graph_builder.py         AST -> graph + graph index
  manager_agent.py         Graph navigation agent/tools
  rag_baseline.py          RAG agents + raw RAG baselines
  evaluation.py            dataset loading, orchestration, metrics
  run_ids.py               stable issue/suite identifiers
tests/                     evaluation and graph-resolution tests
```

## Planning And Reporting

- Execution roadmap: `EXECUTION_PLAN.md`
- Evaluation protocol: `EVALUATION_SPEC.md`
- Decision logs: `dev_logs/README.md`
- Report scaffold (LaTeX): `research_report/README.md`
- Documentation index: `docs/README.md`

## Limitations

1. Small sample in headline runs (`n=10` per repo; `n=5` for yt-dlp due to dataset size).
2. End-to-end patching is now wired and runnable; patch apply robustness is still a major limiter on resolved rate.
3. `gm_deterministic` uses default untuned scoring weights. Coefficient tuning (frozen dev split grid search) is planned.
4. `langchain-ai/langchain` cell is currently excluded pending source_prefix fix and re-run.
5. Static analysis still misses some dynamic Python behavior.
6. API nondeterminism/rate limits can affect run stability and latency.

## Dependencies

- `tree-sitter` + `tree-sitter-python`
- `networkx`
- `google-genai`
- `faiss-cpu`
- `datasets`
- `gitpython`
- `pyyaml`
