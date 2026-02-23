# Research Intent
<!-- Read this before making any scope or experiment design decisions. -->
<!-- This captures strategic intent agreed with the researcher. Do not modify
     without researcher sign-off — it is not a status doc, it is a contract. -->

Last updated: 2026-02-22

---

## V2 STATUS (2026-02-22)

**The V1 paper is archived as a reference artifact. Do not edit it. Do not treat V1
experiment design as the target — it had too many methodological gaps.**

V2 is in the research planning phase. The full V2 plan is in `education/v2_next_session_plan.md`.
Read that document before doing any V2 design or engineering work.

**Core thesis direction is unchanged:** graph-based world model for cost-efficient multi-hop
structural retrieval, with cost advantage widening under amortized deployment.

**What changes in V2:**
- BM25 added as lexical baseline (was missing in V1 — the most critical gap)
- `none` (empty-context patch) replaced with `agentic_cold_start` (agent with file tools, no index)
- `rag_progressive` gets symmetric tool interface (file-read tool to match GM's 3 tools)
- Retrieval and patching evaluations run on the **same repos** (V1 used different sets)
- Comparison framed against published Agentless/RepoMap leaderboard numbers, with
  BM25 and agentic_cold_start as honest internal baselines
- Open decision: fixed-context vs. agentic-tool patch agent — resolve in professor meeting

The V1 numbers, code, and results are frozen. Do not re-run V1 experiments.

---

---

## The Core Idea

**GraphManager is a centralized, reusable codebase world model for multi-agent systems.**

When many agents need to understand a codebase, the naive approach has each agent
cold-start its own exploration from scratch — expensive and slow. GraphManager
builds a typed AST graph (files, classes, functions, edges: imports/calls/inherits)
once and serves it to all agents cheaply. This amortizes codebase exploration across
tasks and agents.

The graph is also compact: embedding structural metadata (names, signatures,
docstrings) costs ~3× fewer tokens than embedding full code bodies (RAG).

---

## Paper 1 — Scope and Claim

**Title direction:** Graph-Augmented Retrieval for Cost-Efficient Issue Localization

**Central claim:** GraphManager reduces total token cost for issue resolution while
maintaining competitive retrieval quality. This is a **cost-efficiency paper**, not
a "graph beats RAG quality" paper.

**What the numbers show (already collected):**
- GM-progressive and RAG-progressive are near-tied on macro F1 (0.684 vs 0.680).
- GM-progressive total cost is 0.42× RAG-progressive — driven by 3.2× cheaper setup.
- Cost gap widens further under same-snapshot amortization (graph built once, many queries).

**Why retrieval alone is not sufficient (prof's feedback):**
Retrieval-only results, while clean, don't prove the mechanism is usable end-to-end.
Reviewers (and the advisor) will ask: "so what?" Paper 1 must include patching
results — not necessarily full SWE-bench pass@1, but enough to show the retrieval
feeds a real patch agent and that the system produces non-trivial resolved instances.

**Paper 1 target structure:**
1. Method: graph construction, retrieval modes, cost accounting
2. Retrieval results: 6 methods × 3 repos (Flask, Requests, Pytest) × n=10 × 3 repeats
   + gm_deterministic rows (currently pending)
3. Patching pilot: 3 methods (cold-start, rag_progressive, gm_progressive) ×
   ~30 instances (10/repo across 3 repos), labeled explicitly as a pilot
4. Key comparison table: cost-per-resolved-issue by method — this is the paper's
   money table, combining retrieval cost + patch cost into a single efficiency number

**What Paper 1 does NOT need:**
- Full MAS orchestration (Paper 2)
- SWE-bench pass@1 at scale (too expensive; pilot is sufficient)
- gm_deterministic patching runs (retrieval comparison only)
- Cross-language results (Python-only is fine with explicit scope limitation)

---

## Paper 2 — Intent (do not build yet)

**Central claim:** A shared GraphManager world model enables efficient multi-agent
issue resolution — multiple specialized worker agents (retrieval, patch, test, review)
share one graph index, preventing cold-start duplication across the pipeline.

**What Paper 2 adds over Paper 1:**
- MAS orchestration layer: manager dispatches worker agents
- Worker agents: patch agent, test-feedback agent, review agent
- Shared graph serves all workers → amortization across agent types, not just tasks
- Full SWE-bench Verified evaluation at scale

**Status:** Do not implement. Paper 1 must be submitted first.

---

## Experiment Design Principles

**Oracle run is mandatory before publishing patching numbers.**
Run gold files directly into the patch agent (bypassing retrieval) to establish
the model ceiling. If oracle gets N resolved, then GM-progressive getting M < N
means the gap is retrieval quality. If oracle also gets M ≈ N, the bottleneck is
the patch model, not retrieval. Without oracle, patching numbers are uninterpretable.

**Cold-start must be a real model call.**
cold-start = issue text only → patch agent, zero retrieval context. It must make
a genuine LLM call (not silently return no_patch). This is the baseline that
shows retrieval adds value. If cold-start resolves 3/30 and GM-progressive
resolves 8/30, that delta is the retrieval contribution.

**Ablation before committing to fixed parameter values.**
Any new limit (max_turns, max_output_tokens, max_file_chars) should be tested on
a small instance set before applying to a full 30-instance run. Lock values only
after confirming they don't cause truncation or cost blowups.

**Repeat sets for statistical validity.**
- Retrieval: 3 repeats per cell minimum; report bootstrap 95% CIs on paired deltas.
- Patching pilot: single run per method is acceptable for the pilot, but label it
  as a pilot (no CIs). State N explicitly. Aim for N≥10/repo.

---

## What Success Looks Like for Paper 1

A reviewer should be able to read the paper and conclude:
1. Graph retrieval is cheaper to set up than RAG (well-established in retrieval section).
2. Retrieval quality is competitive — not universally better, but not worse on average.
3. The system resolves real issues end-to-end, at lower total cost per resolution than RAG.
4. The amortization story holds: cost gap widens as more issues share one snapshot.

If the patching pilot shows even directional evidence for (3), the paper is submittable.
If patching results are negative (GM resolves fewer than RAG), the cost story in (1)/(4)
must be strong enough to carry the paper — and the negative result should be analyzed
honestly (retrieval miss rate? patch model bottleneck?).
