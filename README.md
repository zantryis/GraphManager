# GraphManager

**Graph-based retrieval for cost-efficient automated issue resolution.**

GraphManager builds a typed AST graph from a Python repository and uses it to locate relevant files for a given issue — matching or exceeding dense RAG quality at substantially lower token cost.

## Architecture

```
GitHub Issue ──▶ Retrieval Agent ──▶ Relevant Files ──▶ Patch Agent ──▶ Patch
                 (Gemini + tools)
                       │
            Knowledge Graph or RAG Index
```

## Retrieval Methods

Seven methods evaluated on the same issue sets:

| Method | Strategy | LLM at query time? |
|---|---|---|
| `gm_progressive` | Graph Manager, constrained/progressive tool use | Yes |
| `gm_baseline` | Graph Manager, exploratory baseline | Yes |
| `gm_deterministic` | Structural scoring (no LLM at query time) | No |
| `rag_progressive` | RAG Agent, constrained/progressive search | Yes |
| `rag_baseline` | RAG Agent, exploratory baseline | Yes |
| `raw_rag_function` | Pure vector similarity over function chunks | No |
| `raw_rag_fixed` | Pure vector similarity over fixed-size chunks | No |

Current models: retrieval manager = `gemini-3-flash-preview`, patch agent = `gemini-3-flash-preview`.

## Knowledge Graph

Built from static AST analysis (`tree-sitter`):

- **Nodes:** files, classes, functions
- **Edges:** `DEFINES`, `IMPORTS`, `CALLS`, `CONTAINS`, `INHERITS`
- **Semantic entry:** FAISS over node metadata (names/docstrings/signatures — not code bodies)

Indexing metadata instead of code bodies is why graph setup costs ~3× fewer tokens than dense RAG embedding.

## Evaluation Protocol

- **Datasets:** `SWE-bench/SWE-bench_Verified` and `AmazonScience/SWE-PolyBench_*`
- **Metric:** file-level precision/recall/F1
- **Cost accounting:** `setup_embedding_tokens + retrieval_runtime_tokens + patch_runtime_tokens`
- **Dual track:**
  - **Strict** — per-issue index rebuild at each commit (conservative cost)
  - **Same-snapshot amortized** — one index serves all issues on a snapshot (realistic deployment)

## Key Results (2026-02-22, final)

### Retrieval Quality — Strict Track, File-level F1

| Method | Flask | Requests | Pytest | FastAPI | LangChain | Keras | yt-dlp |
|--------|-------|----------|--------|---------|-----------|-------|--------|
| gm\_deterministic | 0.679 | 0.520 | 0.473 | 0.407 | 0.452 | 0.274 | 0.297 |
| gm\_progressive | 0.803 | 0.700 | 0.550 | 0.417 | **0.783** | 0.267 | 0.347 |
| rag\_progressive | 0.704 | 0.733 | 0.602 | 0.421 | 0.366 | 0.162 | 0.114 |

Flask/Requests/Pytest: means over ≥3 repeats. Others: single run, directional.
Macro-F1 across Flask/Requests/Pytest: GM-progressive 0.684, RAG-progressive 0.680 — near-tied.

### Token Cost Comparison (3 SWE-bench repos, 30 issues)

| Method | Setup tokens | Total tokens | vs RAG-progressive |
|--------|-------------|--------------|-------------------|
| GM-progressive | 701K | 999K | 0.42× |
| GM-deterministic | 701K | 706K | 0.30× |
| RAG-progressive | 2,268K | 2,391K | 1.0× (reference) |

Graph setup embeds metadata (~40–80 tokens/function) vs RAG embedding code bodies (~200–500 tokens/function).

### End-to-End Patching Pilot (N=100, SWE-bench Verified, 9 repositories)

| Method | Resolved | Cost-per-resolved (method-accounted) | Cost-per-resolved (as-run) |
|--------|----------|--------------------------------------|---------------------------|
| Oracle (gold files) | 45% | 33,594 tokens | 33,594 tokens |
| GM-progressive | **43%** | **479,354 tokens** | 1,250,676 tokens |
| RAG-progressive | 38% | 2,115,746 tokens | 2,319,677 tokens |
| None (no retrieval) | 3% | 24,291 tokens | 24,291 tokens |

McNemar p=0.38 — quality gap not statistically significant. Single run, exploratory.
GM resolves 43% at **4.4× lower cost-per-resolved** than RAG (method-accounted).

## Quick Start

```bash
git clone <repo-url> && cd GraphManager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set GEMINI_API_KEY in .env (required)
# Optional: HF_TOKEN (for HuggingFace dataset access), MODAL_TOKEN_ID/SECRET (for Modal cloud)
```

## Run Experiments

### Retrieval evaluation

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
./.venv/bin/python run_suite.py experiments_matrix_v2.yaml
```

### Patching pipeline (two-stage)

**Stage 1 — generate patches** (no Docker or Modal required):

```bash
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/swebench_verified_requests_v1.yaml
# → writes results/patch_runs/<run_id>/predictions.json
```

**Stage 2 — evaluate** an existing predictions.json:

```bash
# Local Docker
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate-only \
  --run-dir results/patch_runs/<run_id>

# Modal cloud (no local Docker needed; requires modal setup)
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate-only \
  --run-dir results/patch_runs/<run_id> \
  --modal
```

**Combined Stage 1+2** (generate + evaluate in one pass):

```bash
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate [--modal]
```

### Visualize

```bash
./.venv/bin/python visualize_results.py
# writes results/compare.html

# Include stale/historical runs
./.venv/bin/python visualize_results.py --include-stale --output results/compare_with_stale.html
```

## Project Structure

```
run_experiment.py          Single retrieval experiment runner
run_suite.py               Multi-repo suite runner from YAML config
run_patch.py               Patching pipeline (retrieval → patch generation → evaluation)
visualize_results.py       HTML dashboard generator
src/
  graph_builder.py         AST → typed graph + FAISS index
  manager_agent.py         Graph navigation agent and tools
  rag_baseline.py          RAG agents and raw RAG baselines
  evaluation.py            Dataset loading, orchestration, metrics
  patch_agent.py           Patch generation agent
  deterministic_retrieval.py  Zero-LLM-runtime structural scorer
  deterministic_config.py  Machine-loadable deterministic config contract
patch_manifests/           YAML manifests for patch runs
  n100_verified/           Frozen N=100 SWE-bench Verified split (9 repos × 4 methods)
experiments_matrix_v2.yaml Retrieval experiment matrix
configs/                   Frozen experiment configs (gm_deterministic tuning)
tools/                     Analysis scripts (profiling, v4 handoff analysis)
education/                 Professor-facing pilot report, gap analysis, email drafts
tests/                     Unit tests (run before every commit)
research_report/           LaTeX paper (two-column arXiv format, 15 pages)
  figures/                 Matplotlib PDF figures
dev_logs/                  Decision logs (one file per session/decision)
results/                   gitignored — experiment outputs
```

## Planning and Reporting

- Current execution state and workstreams: `CURRENT_STATE.md`
- Paper scope and claims boundaries: `RESEARCH_INTENT.md`
- Permitted claim framing: `CLAIMS_LOCK.md`
- Full dev policy (TDD, commits, scope rules): `CLAUDE.md`
- Evaluation protocol and formulas: `EVALUATION_SPEC.md`
- Decision logs: `dev_logs/`

## Limitations

1. **No BM25 baseline.** The primary cost comparison is GM vs. our dense-RAG implementation. BM25 file-level retrieval (used by Agentless, SWE-bench SOTA) was not evaluated. The 4.4× CPR advantage is relative to dense-embedding RAG, not lexical retrieval.
2. **Underpowered quality comparison.** n=100 patching gives ~25% power to detect a 5pp gap; McNemar p=0.38 — cannot conclude equivalence, only non-significance at this sample size.
3. **Tool interface asymmetry.** GM-progressive has 3 retrieval tools; RAG-progressive has 1. Whether F1 differences reflect graph structure or tool count is unablated.
4. **Asymmetric optimization.** gm_deterministic was tuned via 60-candidate random search on Flask; RAG uses default parameters.
5. **Non-overlapping evaluation populations.** Retrieval F1 measured on Flask/Requests/Pytest; patching on a different 9-repo set. Per-instance retrieval-to-patch correlation is unavailable.
6. **Python-only.** Tree-sitter Python grammar; cross-language claims are out of scope.

## Dependencies

- `tree-sitter` + `tree-sitter-python`
- `networkx`
- `google-genai`
- `faiss-cpu`
- `datasets`
- `gitpython`
- `pyyaml`
- `modal` (optional, for cloud harness evaluation)
