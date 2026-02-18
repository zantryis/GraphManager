# GraphManager Evaluation Specification (v1)

Last updated: 2026-02-11

## 1. Objective

This document defines a practical, defensible evaluation plan for this repository, with amortization as a first-class concern.

Primary claims to test:

1. `Quality`: Graph-guided retrieval is competitive with strong RAG baselines for issue localization.
2. `Cost`: Graph setup + query policy can reduce total token/compute cost.
3. `Amortization`: A shared "world model" becomes more efficient as tasks per snapshot increase.
4. `Policy efficiency`: Manager behavior is not wasting tokens relative to retrieval gain.

## 2. Current Baseline In This Repo

Current code already supports:

- file-level retrieval metrics (`precision/recall/f1`),
- method-level error accounting with zero-scored failures,
- per-method cost fields:
  - `setup_embedding_tokens`
  - `total_query_embedding_tokens`
  - `total_llm_tokens`
  - `total_cost_tokens`
- commit-fidelity evaluation by `base_commit` grouping.

Relevant implementation:

- `src/evaluation.py`
- `src/manager_agent.py`
- `src/rag_baseline.py`

## 3. Source-Validated Benchmark Landscape

### 3.1 SWE-bench family (execution benchmark)

What it is:

- Issue -> patch generation, evaluated in Docker with repository tests.
- Each instance is tied to `repo + base_commit + problem_statement`.

Why it matters:

- It is still the strongest external anchor for "does this actually fix software issues?"

Current dataset sizes (checked on 2026-02-11 in this environment):

- `SWE-bench/SWE-bench`: test 2294, dev 225, train 19008
- `SWE-bench/SWE-bench_Verified`: test 500
- `SWE-bench/SWE-bench_Lite`: test 300

Fit for this project:

- Excellent for end-to-end patch validity.
- Weak for amortization signal when commit reuse is low (many issue-specific commits).

### 3.2 SWE-PolyBench (repo-level + retrieval-aware)

What it is:

- Multi-language repo-level benchmark (Java/JS/TS/Python).
- Includes full (2110), PB500 (500), and verified (382) sets.
- Evaluator supports:
  - `--metrics-only` (retrieval metrics without pass-rate run),
  - `--node-metrics` (node-level retrieval scoring),
  - full Docker-based pass-rate evaluation.

Why it matters:

- Gives a clean retrieval track and a patch execution track in one framework.
- Node metrics align well with your "compressed world model" narrative.

Fit for this project:

- Best primary benchmark for your current stage.

### 3.3 RepoBench v1.1 (next-line completion benchmark)

What it is:

- Repository-level next-line completion (`cross_file_first`, `cross_file_random`, `in_file`).
- Reported metrics: EM, Edit Similarity, CodeBLEU.
- Current public v1.1 tooling focuses on first non-comment next-line prediction.

Why it matters:

- Cheap diagnostic for cross-file context retrieval quality under long context.

Limitations for your claim:

- Not issue-level patching.
- No execution harness.
- Not directly measuring manager amortization.

Fit for this project:

- Useful as an auxiliary diagnostic, not the headline benchmark.

### 3.4 RepoExec (repository-level executable function completion)

What it is:

- Executable repository-level function generation benchmark.
- Context variants: `full_context`, `medium_context`, `small_context`.
- Includes execution metrics/scripts for `pass@k` and `DIR`.

Why it matters:

- Good for "context sufficiency under constrained context" studies.

Limitations for your claim:

- Dataset schema is function-completion style (not issue + `base_commit` style).
- Does not directly test issue localization or commit-aware amortization.

Fit for this project:

- Secondary benchmark for policy/context sensitivity, not core evidence.

## 4. Amortization Reality Check (Important)

SWE-bench is commit-specific, so amortization opportunity depends on repeated `base_commit` within a repo sample.

Measured on 2026-02-11 from `SWE-bench/SWE-bench`:

| Repo | Issues | Unique `base_commit` | Repeat ratio |
|---|---:|---:|---:|
| `pallets/flask` | 11 | 11 | 0.0% |
| `psf/requests` | 44 | 41 | 6.8% |
| `pytest-dev/pytest` | 119 | 114 | 4.2% |

Across repos with >=10 issues (49 repos), median repeat ratio is ~6.82%.

Examples with higher repeat opportunity in the same snapshot (measured 2026-02-11):

| Repo | Issues | Unique `base_commit` | Repeat ratio |
|---|---:|---:|---:|
| `pandas-dev/pandas` | 5049 | 3724 | 26.2% |
| `tiangolo/fastapi` | 28 | 21 | 25.0% |
| `conda/conda` | 629 | 488 | 22.4% |
| `conan-io/conan` | 855 | 676 | 20.9% |
| `Lightning-AI/lightning` | 377 | 299 | 20.7% |

These ratios can change as datasets are versioned; rerun the probing script before final experiments.

Implication:

- In strict commit-fidelity sweeps, amortization is structurally limited for many repos.
- You should evaluate amortization on both:
  - strict commit-fidelity track, and
  - controlled same-snapshot track (where world-model reuse is intentionally enabled).

## 5. Recommended Evaluation Program

### Phase A: Retrieval-first signal (now)

Goal:

- Prove graph retrieval quality and policy efficiency before full MAS integration.

Dataset:

- Primary: `AmazonScience/SWE-PolyBench_Verified` (382)
- Optional scale check: `AmazonScience/SWE-PolyBench_500` (500)

Protocol:

1. Run retrieval-only mode (`--metrics-only`) for all methods.
2. Enable node metrics (`--node-metrics`) for graph methods.
3. Compare:
   - `gm_progressive`
   - `gm_baseline`
   - `rag_progressive`
   - `rag_baseline`
   - non-LLM baselines (`raw_rag_*` and a non-LLM graph baseline once added)

Primary outputs:

- file precision/recall/F1
- node precision/recall/F1 (graph methods)
- runtime tokens
- setup tokens
- total cost

### Phase B: Execution anchor (small but credible)

Goal:

- Show retrieval gains are not decoupled from executable outcomes.

Dataset:

- `SWE-bench/SWE-bench_Verified` (start with a fixed subset, then expand)

Protocol:

1. Keep strict `base_commit` fidelity.
2. Use SWE-bench harness for patch-level success.
3. Evaluate at least top 2 methods from Phase A + 1 strong RAG baseline.

Primary outputs:

- resolved rate / pass@1-style success
- retrieval metrics
- cost metrics
- per-instance error stats

### Phase C: Explicit amortization study (core to thesis)

Run two tracks side-by-side.

Track C1: Strict commit fidelity

- Per issue at its own `base_commit`.
- Cache index builds by commit hash (if repeated commits exist).
- This is your "realistic conservative" estimate.

Track C2: Same-snapshot amortized setting

- Fix one repo snapshot (single commit/tag).
- Evaluate many tasks against that one snapshot (retrieval or patch tasks).
- Build index once, query many.
- This is your "world-model reuse" estimate.

Report both. Do not mix them into one number.

### Phase D: Incremental evolution microbenchmark (future-ready)

Goal:

- Evaluate cheap graph updates when code changes (even before full MAS).

Protocol:

1. Pick one repo snapshot.
2. Apply a sequence of controlled commits/diffs.
3. Compare:
   - full rebuild cost/time
   - incremental update cost/time
   - retrieval quality drift after updates

## 6. Metrics And Formulas (Use Exactly)

Per issue:

- `P_i`, `R_i`, `F1_i` at file level
- optional node-level `P_i_node`, `R_i_node`, `F1_i_node`
- `LLM_i`, `QEMB_i` query embedding tokens
- `setup_tokens_m` for method `m` (per built index context)

Aggregates:

- Mean quality: `mean(F1_i)`, `mean(P_i)`, `mean(R_i)`
- Error rate: `n_errors / n_issues`
- Runtime tokens: `sum_i (LLM_i + QEMB_i)`
- Total cost tokens: `setup_tokens_m + sum_i (LLM_i + QEMB_i)`

Amortized vs unamortized:

- Unamortized per-issue cost:
  - `C_unamortized_i = setup_tokens_m + LLM_i + QEMB_i`
- Amortized average cost over `N` issues:
  - `C_amortized = (setup_tokens_m + sum_i(LLM_i + QEMB_i)) / N`

Break-even task count vs baseline `b`:

- Solve for `N` in:
  - `setup_m + N * runtime_m <= setup_b + N * runtime_b`
- `N_break_even = (setup_m - setup_b) / (runtime_b - runtime_m)` (when denominator > 0)

Amortization opportunity descriptors:

- `commit_repeat_ratio = 1 - (unique_base_commits / n_issues)`
- `cache_hit_rate = reused_commit_builds / n_issues`

## 7. Statistical Protocol

Use paired analysis per issue (not only macro means):

1. Compute per-issue deltas, e.g. `delta_i = F1_i(graph) - F1_i(rag)`.
2. Report mean delta + bootstrap 95% CI.
3. Repeat each setting at least 3 runs when LLM stochasticity is non-trivial.
4. Keep issue sets fixed across methods.

## 8. Practical Benchmark Selection Guidance

If you need one core benchmark right now:

1. `SWE-PolyBench_Verified` (retrieval-first, node-aware, manageable size)
2. `SWE-bench_Verified` subset (execution anchor)

If you need quick auxiliary stress tests:

1. `RepoBench v1.1` for long-context cross-file next-line diagnostics
2. `RepoExec` for executable function-context sensitivity

If you need to highlight amortization:

1. Always present both strict-commit and same-snapshot tracks.
2. Prefer repos/task sets with higher commit repeat ratio for strict-track reuse signal.

## 9. Immediate Actions For This Repo

1. Implement a benchmark adapter layer (`dataset adapters`) so one evaluator can run SWE-bench and SWE-PolyBench retrieval metrics consistently.
2. Add explicit amortization report fields:
   - `commit_repeat_ratio`
   - `cache_hit_rate`
   - `N_break_even` per method pair
3. Add one non-LLM graph baseline (deterministic graph walk/ranking) to isolate manager-policy value from graph value.
4. Freeze one fixed evaluation manifest (instance IDs + commits) for repeatability.

## 10. References (Primary Sources)

SWE-bench:

- Repo/docs: https://github.com/SWE-bench/SWE-bench
- Evaluation guide: https://github.com/SWE-bench/SWE-bench/blob/main/docs/assets/evaluation.md
- Harness reference: https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/harness.md
- Dataset: https://huggingface.co/datasets/SWE-bench/SWE-bench
- Verified dataset: https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified

SWE-PolyBench:

- Repo: https://github.com/amazon-science/SWE-PolyBench
- Paper: https://arxiv.org/abs/2504.08703
- Dataset: https://huggingface.co/datasets/AmazonScience/SWE-PolyBench
- Verified: https://huggingface.co/datasets/AmazonScience/SWE-PolyBench_Verified

RepoBench:

- Repo: https://github.com/Leolty/repobench
- Paper: https://arxiv.org/abs/2306.03091
- Python v1.1 dataset: https://huggingface.co/datasets/tianyang/repobench_python_v1.1

RepoExec:

- Repo: https://github.com/FSoft-AI4Code/RepoExec
- Paper: https://arxiv.org/abs/2406.11927
- Dataset: https://huggingface.co/datasets/Fsoft-AIC/RepoExec

Optional long-horizon future benchmark:

- SWE-EVO paper: https://arxiv.org/abs/2507.13272

## 11. Reproducibility Notes For Claims In This Spec

The dataset-size and commit-repeat claims in this document were measured in this environment on 2026-02-11 with `datasets` and the dataset IDs above.

Minimal probe commands (example):

```bash
./.venv/bin/python - <<'PY'
from datasets import load_dataset
from collections import defaultdict

# SWE-bench split sizes
for name, split in [
    ("SWE-bench/SWE-bench", "test"),
    ("SWE-bench/SWE-bench", "dev"),
    ("SWE-bench/SWE-bench", "train"),
    ("SWE-bench/SWE-bench_Verified", "test"),
    ("SWE-bench/SWE-bench_Lite", "test"),
]:
    print(name, split, len(load_dataset(name, split=split)))

# Commit-repeat stats
rows = []
for split in ["test", "dev", "train"]:
    rows.extend(load_dataset("SWE-bench/SWE-bench", split=split))
by_repo = defaultdict(list)
for r in rows:
    by_repo[r["repo"]].append(r)
for repo in ["pallets/flask", "psf/requests", "pytest-dev/pytest"]:
    n = len(by_repo[repo])
    u = len({x["base_commit"] for x in by_repo[repo]})
    print(repo, n, u, 1 - u / n)
PY
```
