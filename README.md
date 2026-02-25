# GraphManager

**Graph-based retrieval for cost-efficient automated issue resolution.**

GraphManager builds a typed AST graph from a Python repository and uses it to locate relevant files for a given issue — matching or exceeding dense RAG quality at substantially lower token cost.

## Quick Start

```bash
git clone <repo-url> && cd GraphManager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then set GEMINI_API_KEY
```

Health check:

```bash
make verify   # runs 242 tests + import lint
make smoke    # quick pipeline plumbing test (no API key needed)
```

## How to Run

### Retrieval evaluation (single repo)

```bash
./.venv/bin/python run_experiment.py \
  --repo-name pallets/flask \
  --source-prefix src/flask \
  --n-issues 10 \
  --manager-max-turns 6 \
  --rag-max-turns 6
```

### Patching pipeline

**Stage 1 -- generate patches** (no Docker/Modal required):

```bash
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml
```

**Stage 2 -- evaluate** existing predictions:

```bash
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml \
  --evaluate-only \
  --run-dir results/patch_runs/<run_id> \
  --modal
```

**Combined Stage 1+2:**

```bash
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml \
  --evaluate --modal
```

### Batch orchestration (multiple manifests)

```bash
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list logs/v2_full_manifests_8method_20260224_100240.txt \
  --results-dir results/v2_full_runs \
  --max-parallel-repos 8 \
  --resume-incomplete \
  --execution-mode local \
  --evaluate-mode stage1_only
```

## Architecture

```
Issue text ──> Retrieval (graph/RAG/BM25/agentic) ──> File list ──> Patch Agent ──> Patch
                         |                                              |
                   Knowledge Graph                               SWE-bench harness
                   or RAG Index                                  (Docker / Modal)
                   or BM25 Index
```

## Retrieval Methods (V2)

| Method | Index | LLM at query? | Purpose |
|---|---|---|---|
| `oracle` | None | No | Upper bound (gold files) |
| `bm25` | Lexical | No | Zero-cost lexical baseline |
| `gm_deterministic` | Graph+FAISS | No | Structural baseline (no LLM runtime cost) |
| `gm_progressive` | Graph+FAISS | Yes | **Core method**: graph-guided agentic retrieval |
| `rag_progressive` | Dense embed | Yes | Primary comparison: RAG with symmetric tools |
| `agentic_cold_start` | None | Yes | No-index agent (filesystem tools only) |
| `raw_rag_function` | Dense embed | No | Dense retrieval without agentic search |
| `repomap_like` | Graph (PageRank) | Optional | RepoMap-inspired file ranking |
| `agentless_like_localization` | Graph+Dense | Yes | Agentless-inspired hierarchical localization |

## Project Structure

```
run_experiment.py          Retrieval evaluation runner
run_patch.py               Patching pipeline (retrieval -> patch -> eval)
run_suite.py               Multi-repo suite runner
Makefile                   Health checks: make verify / make smoke / make test

src/
  graph_builder.py         AST -> typed graph + FAISS index
  manager_agent.py         Graph navigation agent (gm_progressive)
  rag_baseline.py          RAG agents + raw RAG + symmetric file tool
  bm25_baseline.py         BM25Plus file-level retrieval
  agentic_cold_start.py    No-index agentic retrieval
  repomap_like.py          PageRank file ranking
  agentless_like_localization.py  3-stage hierarchical localization
  evaluation.py            Dataset loading, orchestration, metrics
  patch_agent.py           Fixed-context patch generation
  deterministic_retrieval.py  Zero-LLM structural scorer
  patch_dashboard.py       Run status collector
  path_resolution.py       File path canonicalization

tools/
  run_manifest_pool.py     Repo-safe parallel manifest runner
  patch_dashboard.py       Web dashboard server
  generate_v2_verified_manifests.py  V2 manifest generator
  generate_v2_baseline_ablation_manifests.py  Ablation manifest generator
  analyze_v4_handoff.py    V1 N=100 analysis script

patch_manifests/
  v2_verified/             V2 manifests (12 repos x 8 methods + pilots)
  v2_ablation_smoke/       Ablation smoke manifests
  n100_verified/           Frozen V1 N=100 split

tests/                     242 unit tests (make test)
configs/                   Frozen experiment configs
docs/                      Design docs and analysis artifacts
dev_logs/                  Decision logs (one per session)
research_report/           LaTeX paper (archived V1)
results/                   gitignored -- experiment outputs
logs/                      gitignored -- runtime logs
```

## Key Documents

| File | Purpose |
|---|---|
| `STATE.md` | Current status, what's done, what's next |
| `TASKS.md` | Atomic task backlog with IDs and acceptance criteria |
| `AGENTS.md` | How agents should operate in this repo |
| `SESSION_PLAYBOOK.md` | Canonical loop for continuing work |
| `RESEARCH_INTENT.md` | Paper scope and claims (contract) |
| `CLAIMS_LOCK.md` | Permitted claim strength |
| `CLAUDE.md` | Dev policy (TDD, commits, scope) |

## Outputs

- `results/runs/<run_id>/summary.json` -- retrieval experiment results
- `results/patch_runs/<run_id>/patch_summary.json` -- patching results
- `results/patch_runs/<run_id>/predictions.json` -- SWE-bench format predictions
- `results/patch_runs/<run_id>/run_meta.json` -- provenance (git SHA, manifest hash, versions)

## Dependencies

Core: `tree-sitter`, `networkx`, `google-genai`, `faiss-cpu`, `datasets`, `gitpython`, `pyyaml`, `rank_bm25`, `swebench`

Optional: `modal` (cloud harness evaluation)
