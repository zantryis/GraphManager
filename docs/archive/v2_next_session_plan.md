# V2 Next Session Plan

*Written: 2026-02-22. For agent handoff — read this after CURRENT_STATE.md and RESEARCH_INTENT.md.*

---

## Context

The V1 pilot (N=100, paper written) is **archived as reference only**. The paper exposed
too many methodological gaps to be a credible submission as-is. V2 starts fresh with a
cleaner experimental design. The V1 pipeline, results, and paper remain intact as calibration
artifacts — do not delete them.

**The thesis direction stays the same:** graph-based world model for cost-efficient
multi-hop structural retrieval. The contribution is cost-efficiency, not quality-superiority.

---

## Phase 1 — Research (DO THIS FIRST, no code yet)

**Goal:** Answer three questions before touching the experiment design.

### Q1: How does Agentless localize files, and what does it cost?

Read the Agentless paper and codebase. Specifically:
- What is the exact localization pipeline? (BM25 → LLM re-rank → snippet selection?)
- What are the token costs per instance at each step?
- Does Agentless give the patch agent file-access tools, or fixed-context only?
- What are their published resolved rates on SWE-bench Verified, and with which models?

**Why it matters:** If Agentless BM25 localization costs 10K tokens and achieves F1 ≈ gm_deterministic
(0.52–0.68), then GM's cost advantage story requires re-framing. If BM25 is cheaper and equally good,
GM's graph needs to beat BM25 structurally to have a contribution.

### Q2: How does RepoMap work, and where does GM differ?

Read the RepoMap (aider) design. Specifically:
- Does RepoMap build a graph or a flat text summary?
- What information does it encode? (function signatures, call edges, imports?)
- What does it cost per repo? (tokens for generation)
- Is it static (generated once) or dynamic (re-generated per query)?

**Why it matters:** RepoMap is the closest architectural prior. If GM's graph is essentially
RepoMap + FAISS, the contribution is the agentic traversal policy, not the index structure.
Understanding this positions GM correctly relative to prior work.

### Q3: Does giving the patch agent file-access tools change the experiment?

This is an **open design decision** the researcher has not yet resolved. Frame the options:

**Option A — Fixed-context patch agent (current design):**
- Patch agent receives retrieved files, generates patch from those only
- Retrieval quality is the key variable; patch generation is held constant
- Architecturally: retrieval → fixed context → patch
- Comparable to: Agentless, most localization-first systems

**Option B — Agentic patch agent with file tools:**
- Patch agent receives retrieved files + can request more (ls/cat/grep)
- Agent can recover from bad retrieval by exploring on its own
- Architecturally: retrieval → agentic exploration → patch
- Comparable to: SWE-agent, Moatless Tools, top SWE-bench leaderboard entries

The tradeoff: Option A isolates retrieval quality cleanly; Option B is more realistic for
SWE-bench competitive performance but conflates retrieval quality with agent capability.

**Recommendation to discuss with professor:** For a thesis that claims retrieval contribution,
Option A is cleaner. For a thesis that claims end-to-end system contribution, Option B is
stronger but requires re-designing the cost accounting (patch phase now burns file-read tokens).

---

## Phase 2 — Engineering Diagnosis

Fix the pipeline before running new experiments. Do not run any V2 experiments until Phase 2 is complete.

### E1: Bump Modal harness timeout (15 min)

In [run_patch.py](../run_patch.py), find the `swebench_eval()` call and change `timeout=300` → `timeout=600`.
One instance timed out at 296.67s in the pilot. Slower repos (matplotlib, sympy) regularly exceed 300s.

```python
# Find this call in _run_evaluate_only() and in run_patch_pipeline()
swebench_eval(
    ...
    timeout=300,   # change to 600
    ...
)
```

Run `python -m unittest discover -s tests -v` to confirm no regressions.

### E2: Parallel Stage 1 — multiple repo clones (1–2 days engineering)

The patch generation bottleneck is sequential LLM calls (~230s avg/instance). `git checkout`
is not thread-safe on a single clone, so parallelism requires pre-cloned repo copies.

Design:
- Accept `--workers N` flag on Stage 1
- Pre-clone `N` copies: `requests_repo_0/`, `requests_repo_1/`, ..., `requests_repo_N-1/`
- Distribute instances across workers using `concurrent.futures.ThreadPoolExecutor`
- Each worker writes to its own partial `predictions_{worker_id}.jsonl`
- Merge all partial files into `predictions.json` before Stage 2

Expected speedup: 4 workers → ~4× faster Stage 1 (API rate limits may cap this in practice).

TDD requirement: write tests for the merge step and for worker failure isolation before implementing.

### E3: Checkpoint/resume for Stage 1 (4–6 hours)

The N=100 pilot lost two scikit-learn runs to Docker OOM mid-harness. With two-stage pipeline,
Stage 1 is now safe from harness failures, but Stage 1 itself can still die mid-run (OOM, network,
API quota exhaustion).

Design:
- After each instance completes Stage 1, flush its result to `predictions_partial.jsonl`
- On startup, check for an existing `predictions_partial.jsonl` — skip instances already in it
- `--resume` flag to explicitly trigger resume mode

This is lower priority than E1 and E2 but critical for overnight runs on 300+ instances.

### E4: Investigate `max_workers` behavior with Modal

From the pilot: Modal ran all 8 instances in parallel despite `max_workers=1`. The `max_workers`
parameter may not control Modal Sandbox parallelism. Investigate:
- Read `swebench/harness/run_evaluation_modal.py` to understand what `max_workers` controls
- Determine whether `max_workers=1 if modal else 4` is correct, harmless, or wrong
- Update `run_patch.py` accordingly

---

## Phase 3 — New Experiment Design

Do not implement until Phase 1 research is complete. These are the design targets based
on the V1 gap analysis. Final design may change after research findings.

### New baseline lineup

Replace the V1 baseline set with this cleaner structure:

| Tier | Method | LLM at query time? | Index? | Purpose |
|------|--------|-------------------|--------|---------|
| 0 | BM25 | No | None (lexical) | Lexical anchor — zero LLM cost |
| 0 | gm_deterministic | No | Graph | Structural anchor — zero LLM runtime cost |
| 0 | raw_rag | No | Dense embedding | Dense anchor — zero LLM runtime cost |
| 1 | gm_progressive | Yes | Graph | Graph + agentic traversal |
| 1 | rag_progressive | Yes (symmetric tools) | Dense embedding | RAG + symmetric tools |
| 1 | agentic_cold_start | Yes | None (file tools only) | True cold-start: agent navigates repo without index |
| — | Oracle | N/A | Gold files | Upper bound |

**Key changes from V1:**
- BM25 added as Tier 0 lexical baseline (highest priority — see gap analysis)
- `rag_progressive` gets a file-read tool to match GM's tool count (removes tool asymmetry confound)
- `none` (empty context patch) replaced by `agentic_cold_start` (agent with ls/cat/grep, no index)
- `agentic_cold_start` is the realistic "what would you pay without a pre-built index" baseline

### Aligned evaluation populations

V1 used Flask/Requests/Pytest for retrieval and a different 9-repo set for patching.
These do not compose. V2 must use the same repos for both.

**Proposed anchor set:** Flask, Requests, Pytest (keep existing retrieval data as calibration;
re-run patching on these same 3 repos)

Rationale: these 3 repos have ≥3 retrieval repeats, known commit pinning, and manageable
SWE-bench Verified instance counts. psf/requests (n=8) is small — consider supplementing
with full SWE-bench (requests=44) for statistical power.

### Statistical power

V1 n=100 → ~25% power to detect a 5pp gap. Options:
- n≥300 for a quality claim (meaningful but expensive)
- Reframe patching as cost-validation-only ("demonstrates end-to-end viability at lower cost")
  and report quality as directional without a significance test

**Decision to make in professor meeting:** which framing is more defensible for the thesis?

### Symmetric tool interface

Give `rag_progressive` a `get_file_contents(path)` tool to match GM's `get_file_summary`.
This removes the 3-vs-1 tool count confound. The test: if RAG-progressive F1 improves
significantly when given the extra tool, the V1 advantage was partly tool-count, not graph structure.

---

## Phase 4 — Scientific Audit (Before Full Runs)

Before kicking off any full experiment run, repeat the adversarial audit:

1. **Run a small pilot** (n=10, 2–3 methods, 1 repo) with the new baseline lineup
2. **Play Professor Mean again** — adversarial examination of the new design
3. **Check specific questions:**
   - Does BM25 match gm_deterministic? If yes, reframe; if no, headline it.
   - Does agentic_cold_start cost more than gm_progressive (as expected)?
   - Is rag_progressive F1 affected by the symmetric tool change?
4. **Only proceed to full runs after the pilot survives the audit**

---

## Open Questions (resolve in Phase 1 research)

1. **Worker tools for patch agent**: fixed-context (Option A) vs. agentic with file tools (Option B)?
   Carry to professor meeting.

2. **Comparison methodology**: published leaderboard numbers vs. running their code?
   Lean toward published numbers + internal BM25/agentic-cold-start, but confirm after
   understanding Agentless architecture.

3. **Full SWE-bench vs. Verified**: psf/requests Verified has only 8 instances — too few for
   statistical claims. Full SWE-bench has 44. Decide which dataset to anchor on for V2 patching.

4. **LangChain outlier (0.783 vs 0.366)**: Is this a structural advantage on dependency-heavy
   frameworks or a n=10 artifact? Worth 2 hours of analysis before V2 re-runs — could become
   the headline finding.

---

## What NOT to do in V2

- Do not re-run V1 frozen experiments (retrieval matrix is complete and frozen)
- Do not skip the research phase and go straight to coding
- Do not run full experiments before the Phase 4 audit
- Do not build MAS orchestration (Paper 2 — out of scope)
- Do not compare against Agentless/RepoMap by running their code without a clear plan
  for handling the architectural mismatch (different models, different tool access)

---

## Key Reference Files

| File | What it tells you |
|------|------------------|
| `CURRENT_STATE.md` | Workstream status, frozen run IDs, parking lot |
| `RESEARCH_INTENT.md` | Thesis scope — what is and isn't in scope |
| `CLAIMS_LOCK.md` | V1 permitted claim strength — use as calibration for V2 |
| `education/gap_analysis_v1.md` | Full gap analysis from adversarial defense session |
| `education/pilot_report_v1.md` | V1 results summary (professor-facing) |
| `research_report/main.tex` | V1 paper (archived reference) — do not edit |
| `dev_logs/2026-02-22-modal-two-stage-pipeline.md` | Modal pilot results + two-stage pipeline design |
