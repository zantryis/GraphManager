# V2 Phase 1 Research Summary

**Date:** 2026-02-23
**Task:** Phase 1 research — Q1 (Agentless), Q2 (RepoMap), Q3 (patch agent tool access)
**Status:** Complete — no code written
**Sources:** Agentless paper (arxiv:2407.01489), Agentless GitHub (OpenAutoCoder/Agentless), aider documentation (aider.chat/docs/repomap.html), aider blog (aider.chat/2023/10/22/repomap.html)

---

## Q1: How Does Agentless Localize Files, and What Does It Cost?

### Pipeline

Agentless is a three-phase system: **localization → repair → patch validation**. It explicitly
does **not** use an agent loop — the LLM does not decide future actions. All steps are
direct prompting with pre-defined structure.

**Localization is three-stage hierarchical (coarse → fine):**

**Stage 1 — File-level localization (two sub-methods, combined):**
- *LLM-based:* Prompts GPT-4o with the full directory tree (text) + issue description.
  Asks the model to identify the top 3 suspicious files by name. Output: list of filenames.
- *Embedding-based:* Filters irrelevant folders via LLM first, then chunks remaining files
  into 512-token segments with 0 overlap. Embeds chunks with `text-embedding-3-small`.
  Retrieves via cosine similarity to embedded issue text. Output: ranked file list.
- *Combined:* Merges both sub-method outputs. Recall (ground truth file in set):
  combined = 81.67%, prompting-only = 78.67%, embedding-only = 70.33%.

**Stage 2 — Element-level localization:**
- Generates a "skeleton format" of the suspicious files (class/function declarations,
  method signatures, comments — NOT full code bodies). Reduces context from ~3,000 to
  ~700 lines per file.
- Prompts the LLM to identify relevant classes and functions within those skeletons.
- Output: list of class/function names to examine in full.

**Stage 3 — Edit location localization:**
- Provides the full code of the identified elements to the LLM.
- Samples edit locations 4 times per issue (1 greedy + 3 stochastic).
- Output: specific line ranges, functions, or classes to edit.

### BM25 Usage

**Agentless does NOT use BM25.** The original Agentless localization uses:
- OpenAI `text-embedding-3-small` (dense embedding, not lexical)
- Direct LLM prompting with directory trees and skeleton formats

BM25 appears in two related but distinct contexts:
1. **SWE-bench's own retrieval dataset** (`princeton-nlp/SWE-bench_bm25_27K`): Princeton
   provides a pre-built BM25 retrieval context (27K-token limit) as a convenience resource
   for other systems. This is NOT Agentless's own pipeline.
2. **Agentless-Lite** (separate project, sorendunn/Agentless-Lite): A lightweight
   RAG-based reimplementation that uses embedding retrieval (not BM25). Costs ~$0.21/instance.
   32.33% resolved on SWE-bench Lite. Not the same codebase.

### Costs (Original Agentless, GPT-4o)

| Phase | Avg. Cost |
|-------|-----------|
| File localization (combined) | ~$0.06 |
| Element localization (skeleton) | ~$0.02 |
| Edit location (4 samples) | ~$0.07 |
| Repair (40 patches) | ~$0.29 |
| Reproduction test generation | ~$0.25 |
| **Total per issue** | **~$0.70** (~78,166 tokens) |

Note: The paper reports localization costs but not a clean per-stage token breakdown. The
GitHub provides `dev/util/cost.py` to compute per-step costs from output.jsonl files.
Token costs above are approximate from the HTML paper's table; the paper reports a clean
total of 78,166 tokens/instance.

**Localization alone is approximately (0.06+0.02+0.07)/$0.70 = 21% of total cost.**
Repair + test generation = 79% of total cost.

### Patch Agent Context Mechanism

**Option A (fixed context).** The patch agent receives:
- ±10-line context windows (`--context_window=10`) around each identified edit location
- No file-access tools (ls/cat/grep)
- Pre-determined locations from Stage 3

The LLM is not autonomous: "does not allow LLMs to autonomously decide future actions."
40 candidate patches are sampled (10 per location set × 4 location sets). Majority
voting + reproduction test execution selects the final patch.

### Resolved Rates

| Benchmark | Model | Resolved Rate |
|-----------|-------|---------------|
| SWE-bench Lite (300) | GPT-4o | 32.00% (96/300) |
| SWE-bench Lite (300) | Claude 3.5 Sonnet | 40.7% |
| SWE-bench Verified (500) | GPT-4o | 38.80% (194/500) |
| SWE-bench Verified (500) | Claude 3.5 Sonnet | 50.8% |

State-of-art on SWE-bench Verified (as of early 2026): ~75% with hybrid systems using
Claude 4 Sonnet + Claude 3.7 Sonnet. Top performers all use agentic tool-access (Option B).

### Implications for GM

**Cost framing:** If Agentless localization costs ~$0.15 total (stages 1–3) for GPT-4o,
that is roughly 0.15/0.70 = 21% of total spend. The GM localization setup cost ($0.04/task
from V1 cost accounting, method-accounted) is cheaper per task, but this comparison
requires careful alignment on what "tokens" count in each.

**BM25 baseline:** BM25 is NOT the Agentless approach — it is a separate SWE-bench
evaluation artifact. The correct comparison is GM-deterministic vs. Agentless embedding-only
stage 1 (sub-step), not vs. the full Agentless pipeline.

**V2 implication:** If we want to compare against Agentless, the cleanest approach is
comparing against their published leaderboard numbers (same model, different localization
method) rather than running their code, because:
(a) Agentless uses OpenAI embeddings + GPT-4o; GM uses Gemini — different cost structures
(b) Agentless generates 40 repair samples per issue (high cost); GM generates 1 patch per issue

---

## Q2: How Does RepoMap Work, and Where Does GM Differ?

### Structure

RepoMap is a **hybrid system**: it internally builds a file-level graph, but its output is
a **flat text string** of code signatures. The graph is not queryable at runtime — it is
only used to rank which signatures appear in the text output.

**Internal graph:**
- NetworkX `MultiDiGraph`
- Nodes: source files (one node per .py file)
- Edges: dependency/reference relationships (file A references symbol defined in file B →
  edge A→B). Edge weight = frequency of cross-file references.
- Algorithm: **Personalized PageRank** over this file graph, personalized toward files
  mentioned in the current conversation context.
- Purpose: rank files by relevance to the current coding task, select top-ranked files'
  signatures for inclusion in the text output.

**Output (what the LLM sees):**
- Flat text, organized by file
- Contents: function signatures ("the critical lines for each definition"), class definitions,
  symbol declarations
- NOT included: full function bodies, docstrings, import statements, call edge annotations
- Token budget: default 1,000 tokens, configurable via `--map-tokens`

### Static vs. Dynamic

**Dynamic per conversation turn.** RepoMap is regenerated each time the chat context
changes. The personalization vector in PageRank shifts based on which files the AI or user
has mentioned. It adjusts token budget dynamically ("usually stays within budget but can
expand significantly at times").

There is no one-time build phase. The graph is re-built from tree-sitter parse results on
each invocation.

### Cost

- Default: ~1,000 tokens per invocation
- No reported per-repo build cost (build is implicit in each invocation)
- For a long coding session with 50 turns, that is ~50,000 tokens of map context alone
- The `--map-tokens` setting can be tuned down for smaller codebases or cost control

### Technology

Uses **tree-sitter** for AST parsing — same parser library as GraphManager. Supports
multiple languages. Does not use FAISS or any vector embedding index.

### SWE-bench Results for Aider

No clean SWE-bench Verified number was found for aider specifically. Aider publishes its own
"polyglot benchmark" (225 Exercism exercises, multiple languages) but does not prominently
report SWE-bench Verified pass@1. The aider repo does not appear in the top SWE-bench
Verified leaderboard entries by name. (Note: some SWE-bench entries may use aider tooling
without attribution.)

### Where GM Differs from RepoMap

| Dimension | RepoMap | GraphManager |
|-----------|---------|--------------|
| Node granularity | Files | Files + Classes + Functions |
| Edge types | Generic "reference" (file→file) | Typed: imports, calls, inherits |
| Output format | Flat text (token-limited) | Queryable graph index |
| Usage pattern | Re-generated every turn | Built once, traversed many times |
| Query mechanism | PageRank personalization (passive) | Agent issues typed queries (active) |
| Amortization | None (cost per turn) | Yes (cost per repo, amortized over tasks) |
| Cross-file call edges | Implicit in file→file edges only | Explicit function→function call edges |
| Runtime LLM? | No (PageRank only) | gm_progressive: yes; gm_deterministic: no |

**Key architectural distinction:** RepoMap selects *which signatures to show* in a token-
limited window per turn. GM builds a persistent graph that an agent actively traverses
by asking typed questions ("what functions does this class call?", "what files import
module X?"). The GM agent collects a working set of relevant files/functions across multiple
turns, rather than passively receiving a ranked list.

**Contribution framing implication:** GM's contribution is NOT "better ranking than RepoMap."
It is (a) the persistent queryable index (amortized across tasks), and (b) the typed
multi-hop traversal that can follow call chains and inheritance paths not visible in a
flat signature list.

---

## Q3: Fixed-Context vs. Agentic Patch Agent — Framing the Design Decision

### Option A — Fixed-Context Patch Agent (Current GM Design)

**How it works:**
- Retrieval outputs a file set → patch agent receives those files verbatim → generates diff
- Agent cannot request additional files at patch time
- Comparable systems: Agentless, most localization-first systems

**Strengths:**
- Clean experimental isolation: resolved rate differences are attributable to retrieval quality
- Simpler cost accounting: patch cost is constant across retrieval methods
- Paper claims "retrieval quality → resolved rate" are directly testable
- Cheaper per instance (no extra file-read turns at patch time)

**Weaknesses:**
- If retrieval misses a key file, the patch agent has no recovery mechanism
- Underperforms vs. top leaderboard entries (all use Option B)
- "Real-world" deployment would not use fixed context — reviewers may object

### Option B — Agentic Patch Agent with File Tools

**How it works:**
- Patch agent receives retrieved files PLUS can call get_file, grep, ls during patch generation
- Agent can discover missed files and recover from retrieval errors
- Comparable systems: SWE-agent, Moatless Tools, Claude Code, top SWE-bench entries

**Strengths:**
- Higher realistic resolved rates (can recover from bad retrieval)
- More competitive with leaderboard top performers
- Demonstrates a complete agentic system end-to-end

**Weaknesses:**
- Conflates retrieval quality with agent capability — cannot isolate retrieval contribution
- Cost accounting is complex: patch phase now burns file-read tokens that vary by quality of retrieval
- If retrieval is bad, agent burns more tokens exploring — perversely rewards bad retrieval
  by adding recovery cost (which inflates as-run cost for bad methods)

### Recommendation for Thesis

For a thesis whose **central claim is cost-efficient retrieval contribution**, Option A is
the correct scientific choice:
- The paper's money table is cost-per-resolved-issue; isolating retrieval keeps that clean
- Option B makes the paper's comparison non-transferable: GM + agentic patch vs. Agentless
  + fixed patch is an apples-to-oranges comparison
- The retrieval-to-patch contribution claim requires holding patch generation constant

However, a second experiment row at Option B is potentially valuable for **motivating
the retrieval work** ("even with agentic recovery, better starting context costs less
and resolves more"). This could be a future direction or a limited pilot within the paper.

**For the professor meeting:** The question to resolve is whether the thesis positions GM as:
(a) "a cheaper retrieval component for localization-first systems" (Option A framing)
(b) "a cheaper end-to-end system that competes with agentic SWE-bench entries" (Option B framing)

These require different experimental designs and different comparison baselines.

---

## Summary: Key V2 Design Implications

1. **BM25 baseline is correctly identified as the critical V1 gap.** BM25 is NOT Agentless
   — it is a separate lexical baseline. V2 must implement BM25 or adopt the SWE-bench_bm25_27K
   Princeton dataset as the zero-LLM-cost localization anchor. Cost: near-zero (no LLM calls).

2. **Agentless comparison should use published leaderboard numbers, not their code.**
   Running Agentless requires OpenAI APIs, 40-sample repair, and test generation (all different
   from GM's pipeline). Compare at the system level (cost-per-resolved-issue) using published
   numbers, with BM25 and gm_deterministic as internal zero-LLM-cost anchors.

3. **RepoMap is not a direct competitor.** RepoMap produces a flat text summary per turn;
   GM builds a persistent graph. The correct positioning is: "GM provides the same structural
   metadata as RepoMap but builds it once and queries it actively, whereas RepoMap regenerates
   on every turn." This is the amortization story.

4. **Option A (fixed-context) is the correct thesis design.** Use it for the main experiments.
   Consider a small Option B pilot (n=10) to show the system generalizes, but do not anchor
   the comparison on Option B performance.

5. **Token cost comparison against Agentless is feasible but requires careful methodology.**
   Agentless localization: ~$0.15/instance (stages 1–3), total $0.70/instance (GPT-4o).
   GM retrieval: method-accounted ~$0.08/task for gm_progressive (from V1 data). But model
   prices differ (GPT-4o vs. Gemini), so dollar costs are not directly comparable.
   Use tokens as the unit, not dollars.
