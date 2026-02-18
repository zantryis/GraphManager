# GraphManager Experimental Report (Internal Research Artifact)

Last updated: 2026-02-11  
Status: experiment report (paper-ready source material, not manuscript text)

## Matrix-v2 Refresh (2026-02-11)

Fresh manifest-pinned repeats were regenerated for `psf/requests` (`n=10`) on both tracks:

- strict: `results/repeat_sets/20260211_183938_swe_bench_psf_requests_strict_commit_fidelity_issues_swebench_requests_v2_10.json`
- same-snapshot: `results/repeat_sets/20260211_185205_swe_bench_psf_requests_same_snapshot_amortized_issues_swebench_requests_v2_10.json`

Key deltas (`gm_progressive` vs `rag_progressive`, mean F1):

- strict: `+0.1805` (bootstrap 95% CI `[0.1200, 0.2333]`)
- same-snapshot: `+0.2857` (bootstrap 95% CI `[0.2190, 0.3333]`)

Amortization split:

- strict: `commit_repeat_ratio=0.0`, `cache_hit_rate=0.0`
- same-snapshot: `commit_repeat_ratio=0.9`, `cache_hit_rate=0.9`

Frozen bundle for these runs:

- `research_report/artifacts/frozen-20260211-matrix-v2-requests/manifest.json`
- `research_report/artifacts/frozen-20260211-matrix-v2-requests/summary_bundle.json`

Matrix-v2 PolyBench reruns on `yt-dlp/yt-dlp` were attempted but failed under embedding request quota (`429 RESOURCE_EXHAUSTED`), so cross-benchmark matrix completion is currently partial.

## 1. Scope and Research Question

This document summarizes the current retrieval experiments in this repository.

Primary question:
- Can graph-navigated retrieval (Manager over AST graph + vector entry) improve file-level retrieval quality and/or cost-efficiency versus RAG baselines on SWE-bench issues?

This report is intended for:
- future experimental planning,
- reproducibility tracking,
- direct reuse of methods/results text in a later paper draft.

## 2. Runs Included (Fresh Regeneration)

All numbers below are from fresh runs on 2026-02-11 with current code:

- `results/runs/20260211_111336` (repo: `pallets/flask`)
- `results/runs/20260211_112336` (repo: `psf/requests`)
- `results/runs/20260211_113229` (repo: `pytest-dev/pytest`)

Operational note:
- Initial suite attempt (`results/runs/20260211_111939`, `results/runs/20260211_112301`) failed due transient Gemini `503 UNAVAILABLE`.
- Final numbers in this report use the three successful runs above.

## 3. Experimental Protocol

### 3.1 Dataset and Task

- Dataset: `SWE-bench/SWE-bench`
- Task: file-level retrieval for issue resolution context
- Repos evaluated: Flask, Requests, Pytest
- Issues per repo: `n=10`
- Gold labels: file paths extracted from patch diffs (`diff --git ... b/<path>`)

Issue sampling:
- Deterministic first-`n` selection after split sweep and dedupe.
- No randomized sampling in this run set.

### 3.2 Methods Compared (6)

- `gm_progressive`
- `gm_baseline`
- `rag_progressive`
- `rag_baseline`
- `raw_rag_function`
- `raw_rag_fixed`

### 3.3 Retrieval Infrastructure

- Graph: tree-sitter AST -> file/class/function graph with typed edges
- Graph semantic entry: FAISS over graph-node text
- RAG: FAISS over function chunks or fixed chunks
- LLM: `gemini-2.0-flash`
- Embedding model: `gemini-embedding-001`

### 3.4 Commit Fidelity

Each issue is evaluated on its own `base_commit`:
- Issues are grouped by commit.
- Repo checkout and index build are done per commit group.
- Each included run has `n_commit_groups = 10` for `n_issues = 10`.

### 3.5 Metrics

Reported per method:
- Precision / Recall / F1 at file level
- `n_errors`, `error_rate`
- `total_llm_tokens`
- `total_query_embedding_tokens`
- `setup_embedding_tokens`
- `total_cost_tokens = setup + query-embed + llm`

## 4. Main Results

### 4.1 Per-Repo F1

| Repo | GM (prog) | GM (base) | RAG (prog) | RAG (base) | Raw-func | Raw-fixed |
|---|---:|---:|---:|---:|---:|---:|
| Flask | 0.803 | **0.809** | 0.704 | 0.802 | 0.340 | 0.321 |
| Requests | 0.700 | 0.534 | **0.733** | **0.733** | 0.256 | 0.221 |
| Pytest | 0.550 | 0.473 | **0.602** | 0.567 | 0.242 | 0.185 |

Winner by repo:
- Flask: `GM baseline`
- Requests: `RAG progressive` / `RAG baseline` (tie)
- Pytest: `RAG progressive`

### 4.2 Cross-Repo Macro F1 (equal weight by repo)

| Method | Macro F1 |
|---|---:|
| RAG (baseline) | **0.701** |
| GM (progressive) | 0.684 |
| RAG (progressive) | 0.680 |
| GM (baseline) | 0.605 |
| Raw-func | 0.279 |
| Raw-fixed | 0.242 |

### 4.3 Token Cost Summary Across 3 Repos (30 issues total)

| Method | Runtime tokens (LLM + query embed) | Setup embed tokens | Total cost tokens |
|---|---:|---:|---:|
| GM (progressive) | 297,690 | 701,054 | **998,744** |
| GM (baseline) | 333,893 | 701,054 | 1,034,947 |
| RAG (progressive) | 123,317 | 2,268,044 | 2,391,361 |
| RAG (baseline) | 354,930 | 2,268,044 | 2,622,974 |
| Raw-func | 12,769 | 2,268,044 | 2,280,813 |
| Raw-fixed | 12,769 | 1,478,791 | 1,491,560 |

Interpretation:
- `GM progressive` and `RAG progressive` are near-tied in macro F1 (0.684 vs 0.680).
- `GM progressive` has much higher runtime token use than `RAG progressive` (2.41x), but much lower setup cost (0.31x), yielding lower total cost (0.42x).
- `RAG baseline` has best macro F1 but highest total cost.

## 5. Key Findings (Current State)

1. No universal winner on quality:
- Graph wins on Flask, RAG wins on Requests/Pytest.
- Current evidence supports repo-dependent tradeoffs.

2. Strong setup-cost advantage for graph methods:
- Across these runs, GM setup is ~3.2x lower than RAG setup (`701k` vs `2.27M` tokens).

3. Progressive mode behaves differently by method family:
- GM progressive improves macro F1 over GM baseline (`0.684` vs `0.605`).
- RAG baseline slightly beats RAG progressive on macro F1 (`0.701` vs `0.680`) but costs more.

4. Raw retrieval remains high-recall/low-precision:
- Raw methods are not competitive on F1 despite near-zero LLM runtime.

## 6. Threats to Validity

1. Sample size:
- Only `10` issues per repo; no confidence intervals in this report.

2. Single run per repo:
- No repeated-run variance estimate for these exact corrected runs.

3. API nondeterminism/outages:
- Transient 429/503 events occurred during execution, though final reported runs completed cleanly.

4. Metric scope:
- Retrieval-only evaluation (file-level), not patch-generation success.

5. Setup-cost accounting context:
- Commit-fidelity design forces many index rebuilds (10 commit groups per run), inflating absolute setup totals while preserving within-run method comparisons.

## 7. Directly Actionable Next Experiments

1. Repeat each repo 3-5x with identical issue sets:
- produce mean/std for F1 and cost metrics.

2. Add ablations:
- graph edge subsets (`CALLS` off / `INHERITS` off),
- no vector entry point vs vector+graph.

3. Add retrieval depth diagnostics:
- tool calls per issue, neighborhood fanout, candidate set size.

4. Add stronger statistical comparison:
- paired per-issue delta analysis (`GM prog - RAG prog`), bootstrap confidence intervals.

5. Expand repository diversity:
- include at least one larger app-style repo and one library-style repo beyond current three.

## 8. Reproducibility Pointers

Commands used for regenerated runs:

```bash
./.venv/bin/python run_experiment.py --repo-name pallets/flask --source-prefix src/flask --n-issues 10 --manager-max-turns 6 --rag-max-turns 6
./.venv/bin/python run_experiment.py --repo-name psf/requests --source-prefix requests --n-issues 10 --manager-max-turns 6 --rag-max-turns 6
./.venv/bin/python run_experiment.py --repo-name pytest-dev/pytest --source-prefix src/_pytest --source-prefix src/pytest --n-issues 10 --manager-max-turns 6 --rag-max-turns 6
./.venv/bin/python visualize_results.py
```

Primary artifacts:
- `results/runs/20260211_111336/summary.json`
- `results/runs/20260211_112336/summary.json`
- `results/runs/20260211_113229/summary.json`
- `results/compare.html`
