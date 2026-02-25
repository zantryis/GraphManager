# Research Intent
<!-- Read this before making any scope or experiment design decisions. -->
<!-- This captures strategic intent agreed with the researcher. Do not modify
     without researcher sign-off — it is not a status doc, it is a contract. -->

Last updated: 2026-02-25

---

## V2 STATUS (2026-02-25)

**The V1 paper is archived as a reference artifact. Do not edit it. Do not treat V1
experiment design as the target — it had too many methodological gaps.**

V2 is in the execution phase. Infrastructure is complete (all methods implemented,
manifests generated, retrieval eval wired up). The V1 pipeline, results, and paper
remain intact as calibration artifacts.

**Core thesis direction is unchanged:** graph-based world model for cost-efficient
multi-hop structural retrieval, with cost advantage widening under amortized deployment.

**What changed in V2 (engineering complete):**
- BM25 added as lexical baseline (was missing in V1 — the most critical gap)
- `none` (empty-context patch) replaced with `agentic_cold_start` (agent with file tools, no index)
- `rag_progressive` gets symmetric tool interface (file-read tool to match GM's 3 tools)
- Retrieval and patching evaluations run on the **same 12 repos** (V1 used different sets)
- `repomap_like` and `agentless_like_localization` added to patching manifests (were retrieval-only in V1)
- `agentic_cold_start` added to retrieval eval (was patching-only)
- Full 11-method retrieval matrix aligned with 10-method + oracle patching matrix

The V1 numbers, code, and results are frozen. Do not re-run V1 experiments.

---

## The Core Idea

**GraphManager is a centralized, reusable codebase world model for multi-agent systems.**

When many agents need to understand a codebase, the naive approach has each agent
cold-start its own exploration from scratch — expensive and slow. GraphManager
builds a typed AST graph (files, classes, functions, edges: imports/calls/inherits)
once and serves it to all agents cheaply. This amortizes codebase exploration across
tasks and agents.

The graph is also compact: embedding structural metadata (names, signatures,
docstrings) costs ~3x fewer tokens than embedding full code bodies (RAG).

---

## Paper 1 — V2 Scope and Claim

**Title direction:** Graph-Augmented Retrieval for Cost-Efficient Issue Localization

**Central claim:** GraphManager reduces total token cost for issue resolution while
maintaining competitive retrieval quality. This is a **cost-efficiency paper**, not
a "graph beats RAG quality" paper.

### Method Matrix (aligned for V2)

**Retrieval evaluation (11 methods):**

| Tier | Methods | LLM calls | Index type |
|------|---------|-----------|------------|
| Tier 0 (zero-LLM) | `gm_deterministic`, `raw_rag_function`, `raw_rag_fixed`, `bm25`, `repomap_like` | None | Graph/RAG/BM25/PageRank |
| Tier 1 (agentic) | `gm_progressive`, `gm_baseline`, `rag_progressive`, `rag_baseline`, `agentless_like_localization`, `agentic_cold_start` | Yes | Graph/RAG/none |

**Patching evaluation (10 methods + oracle):**
`oracle`, `gm_progressive`, `gm_deterministic`, `rag_progressive`, `raw_rag_function`,
`raw_rag_fixed`, `bm25`, `agentic_cold_start`, `repomap_like`, `agentless_like_localization`

`gm_baseline` and `rag_baseline` excluded from patching (single-turn ablation variants;
retrieval eval captures their quality difference vs progressive).

### Tiered Narrative (per gap_analysis_v1)

```
Tier 0:  BM25 (lexical, 0 LLM, 0 embedding cost)
         GM-det (structural, 0 LLM, low embedding cost)
         raw_rag (dense, 0 LLM, high embedding cost)
         repomap_like (graph PageRank, 0 LLM, 0 embedding cost)
         -> Question: what does structure add over lexical matching, at what cost?

Tier 1:  GM-prog (structural + LLM)
         RAG-prog (dense + LLM, symmetric tools)
         agentless_like (hierarchical LLM localization)
         agentic_cold_start (LLM + filesystem tools, no index)
         -> Question: does adding LLM budget help more for one approach?

Tier 2:  Patching pilot (all 10 methods + oracle)
         -> Question: does the retrieval advantage translate end-to-end?
```

### Evaluation Population (12 repos, same for retrieval + patching)

SWE-bench Verified (500 instances across 12 repos):
astropy, django, matplotlib, seaborn, flask, requests, xarray, pylint,
pytest, scikit-learn, sphinx, sympy

Retrieval: n=10 per repo (except seaborn n=2), strict_commit_fidelity track.
Patching: all Verified instances per repo, single run per method.

**Why retrieval alone is not sufficient (prof's feedback):**
Retrieval-only results don't prove end-to-end viability. Paper 1 must include
patching results to show the retrieval feeds a real patch agent.

**What Paper 1 does NOT need:**
- Full MAS orchestration (Paper 2)
- Cross-language results (Python-only is fine with explicit scope limitation)

---

## Paper 2 — Intent (do not build yet)

**Central claim:** A shared GraphManager world model enables efficient multi-agent
issue resolution — multiple specialized worker agents share one graph index.

**Status:** Do not implement. Paper 1 must be submitted first.

---

## Experiment Design Principles

**Oracle run is mandatory before publishing patching numbers.**
Run gold files directly into the patch agent to establish the model ceiling.

**Cold-start must be a real agent call.**
`agentic_cold_start` uses filesystem tools (ls/search_paths/get_file_contents)
with no pre-built index. This is the baseline that shows retrieval adds value.

**Ablation before committing to fixed parameter values.**
Any new limit should be tested on a small instance set before applying to a full run.

**Repeat sets for statistical validity.**
- Retrieval: 3 repeats per cell minimum on anchor repos; 1 repeat on expansion repos.
  Report bootstrap 95% CIs on paired deltas.
- Patching: single run per method. Label as pilot (no CIs). State N explicitly.

---

## What Success Looks Like for Paper 1

A reviewer should be able to read the paper and conclude:
1. Graph retrieval is cheaper to set up than RAG (well-established in retrieval section).
2. Retrieval quality is competitive — not universally better, but not worse on average.
3. The system resolves real issues end-to-end, at lower total cost per resolution than RAG.
4. The amortization story holds: cost gap widens as more issues share one snapshot.
5. BM25 and prior-work baselines (RepoMap, Agentless) are honestly compared.

If the patching pilot shows even directional evidence for (3), the paper is submittable.
If patching results are negative, the cost story in (1)/(4) must be strong enough to
carry the paper — and the negative result should be analyzed honestly.
