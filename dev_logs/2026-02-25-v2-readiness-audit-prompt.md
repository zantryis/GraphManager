# V2 Full-Run Readiness Audit — Senior Researcher Review

*Prepared: 2026-02-25. Request: audit method alignment, methodology rigor, and ablation structure before launching the full V2 experiment campaign.*

---

## 1. Context

We are about to launch the V2 experiment campaign for GraphManager — a cost-efficiency study comparing graph-augmented retrieval against embedding-based (RAG), lexical (BM25), and prior-work (Agentless, RepoMap) baselines for SWE-bench issue localization and patching.

**Core thesis:** GraphManager reduces total token cost for issue resolution while maintaining competitive retrieval quality. Cost advantage widens under amortized (multi-issue) deployment.

**V1 gaps that motivated V2** (from `gap_analysis_v1.md`):
- No lexical baseline (BM25) — the cost story had no floor
- Tool asymmetry: GM had 3 tools, RAG had 1
- Retrieval and patching used different repo populations
- No comparison to prior-work methods (Agentless, RepoMap)
- `agentic_cold_start` existed in patching but not in retrieval eval

All of these have been addressed in V2 engineering. This audit asks: **is the experimental design now rigorous enough to run?**

---

## 2. Method Matrix

### Retrieval Evaluation (11 methods, 9 repos, n=10 per repo, strict_commit_fidelity)

| # | Method | Index | LLM at query | Embed at query | Agent tools | Setup cost |
|---|--------|-------|:---:|:---:|---|---|
| 1 | `gm_deterministic` | FAISS (graph nodes: names+docstrings) | No | Yes (seed only) | None | Graph build + embed |
| 2 | `gm_progressive` | FAISS (graph nodes) | Yes (multi-turn) | Yes (per turn) | `search_nodes`, `get_neighbors`, `get_file_summary` | Graph build + embed |
| 3 | `gm_baseline` | FAISS (graph nodes) | Yes (single-turn-like) | Yes (per turn) | Same 3 tools (relaxed limits) | Graph build + embed |
| 4 | `rag_progressive` | FAISS (function chunks) | Yes (multi-turn) | Yes (per turn) | `search_codebase`, `get_file_contents` (V2 symmetric) | Chunk + embed |
| 5 | `rag_baseline` | FAISS (function chunks) | Yes (single-turn-like) | Yes (per turn) | Same 1-2 tools (relaxed limits) | Chunk + embed |
| 6 | `raw_rag_function` | FAISS (function chunks) | No | Yes (1 query embed) | None | Chunk + embed |
| 7 | `raw_rag_fixed` | FAISS (fixed ~512-token chunks) | No | Yes (1 query embed) | None | Chunk + embed |
| 8 | `bm25` | BM25Plus (file-level) | No | No | None | Tokenize files (zero API cost) |
| 9 | `repomap_like` | NetworkX file graph + PageRank | No | No | None | Graph build only (zero API cost) |
| 10 | `agentless_like_localization` | FAISS (chunks) + graph | Yes (3-stage) | Yes (stage 1) | None (pipeline, not tool-calling) | Graph + chunk + embed |
| 11 | `agentic_cold_start` | None | Yes (multi-turn) | No | `list_files`, `search_paths`, `get_file_contents` | Zero (filesystem scan only) |

### Patching Evaluation (10 methods + oracle, 12 repos, all Verified instances, single run)

Same as above minus `gm_baseline` and `rag_baseline` (single-turn ablation variants excluded from patching to save budget).

**Rationale for excluding baselines from patching:** The progressive→baseline difference is a retrieval-quality ablation (does multi-turn help?). The retrieval eval captures this directly. Running baselines through the full patching pipeline adds 24 manifests (~960 instances) with low analytical payoff — the quality difference is already measured in retrieval F1.

---

## 3. Questions for Audit

### A. Method-Level Rigor

**A1. Tool symmetry (GM-prog vs RAG-prog)**

V2 added `get_file_contents` to RAG-progressive, making the tool count 2 vs 3:
- GM-progressive: `search_nodes`, `get_neighbors`, `get_file_summary`
- RAG-progressive: `search_codebase`, `get_file_contents`

The capability set is now closer (both can search + inspect files), but not identical. GM still has `get_neighbors` (graph traversal) and `get_file_summary` (structural overview), while RAG has `get_file_contents` (full source). These are architecturally different capabilities.

**Q: Is this sufficiently symmetric for a fair comparison, or do we need an explicit ablation isolating tool interface from index type?**

**A2. baseline vs progressive naming**

`gm_baseline` and `rag_baseline` are not single-turn agents — they're multi-turn agents with relaxed parameters (larger search windows, no compact results, higher per-turn tool budgets). The naming suggests "minimal" but the behavior is "verbose." Specifically:
- gm_baseline: `max_neighbors_return=20` vs progressive's 10; `max_definitions_return=12` vs 8
- rag_baseline: `search_top_k=20` vs progressive's 5; `max_snippet_chars=300` vs 120; `max_return_files=20` vs 6

**Q: Does the baseline/progressive split form a clean ablation? What hypothesis does it test — "compactness helps" or "progressive refinement helps"? Should the naming be changed to avoid confusion?**

**A3. agentless_like_localization fidelity**

Our Agentless-like implementation uses 3 stages (file ranking, symbol ranking, edit span selection) and has deterministic fallbacks at each stage. Known concern: the LLM path may silently fall through to the deterministic fallback if LLM calls fail or return unparseable output (STATE.md issue I3).

**Q: Before publishing comparisons to "Agentless," should we validate that the LLM stages actually fire on our eval set? If the method silently degrades to deterministic, we're comparing our graph against a strawman.**

**A4. repomap_like fidelity**

Our RepoMap-like implementation uses PageRank on a file-level dependency graph with query-term personalization. The real RepoMap (aider) generates a compressed text map of repository structure, not a PageRank ranking. Our implementation captures the *structural ranking* idea but not the *text generation* interface.

**Q: Is calling this "RepoMap-like" defensible, or should we rebrand to "graph-PageRank" to avoid direct comparison claims?**

**A5. agentic_cold_start scope**

`agentic_cold_start` has no retrieval index — it uses `list_files`, `search_paths` (lexical path matching), and `get_file_contents` (read source). This is an honest "no-index agent" baseline, but its `search_paths` tool does lexical matching on file paths (token overlap + substring), which is arguably a weak form of retrieval.

**Q: Is this a fair "no retrieval" baseline, or should we frame it as "agent with minimal lexical tools"?**

### B. Ablation Structure

The methods form these natural ablation axes:

**B1. Index type (holding agent fixed at "none")**
- `bm25` (lexical, file-level) vs `raw_rag_function` (dense, function-level) vs `raw_rag_fixed` (dense, fixed-chunk) vs `repomap_like` (graph PageRank) vs `gm_deterministic` (graph + embedding)
- **Tests:** Does structural information (graph) add value over lexical (BM25) or dense (RAG) matching?

**B2. Agent value-add (holding index fixed)**
- `raw_rag_function` → `rag_progressive` (same index, add agent)
- `gm_deterministic` → `gm_progressive` (same index, add agent)
- No agent → `agentic_cold_start` (no index, add agent)
- **Tests:** Does an LLM agent improve file localization over the index alone?

**B3. Compactness / exploration (baseline vs progressive)**
- `gm_baseline` vs `gm_progressive` (same index, same tools, different parameter regimes)
- `rag_baseline` vs `rag_progressive` (same pattern)
- **Tests:** Does compact, focused exploration beat verbose exploration?

**B4. Cost tiers**
- Zero-cost: `bm25`, `repomap_like`
- Embedding-only: `raw_rag_function`, `raw_rag_fixed`, `gm_deterministic`
- LLM + embedding: `gm_progressive`, `rag_progressive`, `agentless_like_localization`
- LLM only (no index): `agentic_cold_start`
- **Tests:** Cost-quality frontier — where does each method sit?

**Q for all:** Do these ablation axes form a convincing analytical structure for the paper? Are there confounds between axes (e.g., B1 and B2 are conflated for `gm_deterministic` which uses both graph structure *and* embedding)?

### C. Population & Statistical Design

**C1.** Retrieval eval uses 9 repos × 10 issues = 90 instances (plus seaborn n=2). Patching uses all Verified instances per repo (~500 total). The retrieval and patching populations overlap but are not identical (retrieval uses a 10-issue subset of the patching population).

**Q: Is the subset relationship acceptable, or should retrieval run on all Verified instances too?**

**C2.** Retrieval expansion runs 1 repeat (no CIs). The 3 anchor repos (Flask/Requests/Pytest) have 3 repeats from V1. New repos do not.

**Q: Is 1 repeat on 9 new repos acceptable given the 3-repeat anchor data? The paper will need to clearly distinguish high-confidence (anchor) from directional (expansion) results.**

**C3.** Patching is single-run, no CIs. V1 showed McNemar p=0.38 on N=100, which was underpowered (~25% power for 5pp gap). V2 expands to ~500 instances × 10 methods.

**Q: With N=500, do we have sufficient power to detect meaningful differences? Or should the framing remain "directional"?**

### D. Cost Accounting

**D1.** V2 patching runs use method-scoped index building (only the required index is built per method). V1 had a dual-build confound (both graph and RAG indices built for every run). The `CLAIMS_LOCK.md` requires dual-build disclosure for V1 numbers.

**Q: With V2's method-scoped builds, can we drop the dual-build disclosure for V2 numbers? Or should we maintain it for continuity?**

**D2.** `agentless_like_localization` uses *both* graph structure and RAG embedding index. Its setup cost is: graph_build_time + rag_embed_time. This is the highest setup cost of any method.

**Q: How should this be accounted in the cost narrative? It's a legitimate prior-work comparison, but its cost profile muddies the "graph is cheaper than RAG" story (since it uses both).**

### E. Execution Speed & Parallelism

The full V2 campaign is large. Here is the wall-clock budget and existing parallelism infrastructure.

**E1. Retrieval expansion (T0): 9 repos × 11 methods × n=10 issues**

Current infrastructure: `run_suite.py --max-parallel N` runs repos concurrently (same-repo experiments are sequential to avoid git contention). Available: `--methods` filter to subset methods per invocation.

Observed timings from partial runs:
- pylint (10 methods, n=10): ~2455s sequential → ~392s with `--methods` filter (3 methods per invocation, 6.3× speedup via method-level partitioning)
- seaborn (10 methods, n=2): relatively fast (small repo, few issues)

Method cost tiers per issue:
- **Zero-LLM** (bm25, repomap_like): seconds per issue. Bottleneck is graph build / file tokenization.
- **Embedding-only** (gm_deterministic, raw_rag_function, raw_rag_fixed): ~10-30s per issue. Bottleneck is Gemini embedding API (20K requests/min quota).
- **Agentic** (gm_progressive, gm_baseline, rag_progressive, rag_baseline, agentic_cold_start, agentless_like_localization): ~30-120s per issue. Bottleneck is multi-turn LLM calls (Gemini Flash, 4-8 turns).

The `strict_commit_fidelity` track requires a fresh git checkout and full index rebuild per issue (no index caching across issues). This is the dominant fixed cost — every issue at a different commit means the graph/embedding index is rebuilt from scratch.

**Naive sequential estimate:** 9 repos × 11 methods × 10 issues × ~60s average = ~16.5 hours.
With `--max-parallel 2` (safe for embedding quota): ~8-9 hours.
With `--max-parallel 3` + retry logic: ~6 hours (but higher risk of 429/503 bursts).

**Q: Is sequential-per-repo acceptable for a one-time research run, or should we invest in:**
1. **Method-level parallelism** — run zero-LLM methods in a separate parallel process (they don't use API at all), freeing the main pipeline for agentic methods only?
2. **Evaluation-track relaxation** — `snapshot_commit` mode caches the index across issues at the cost of commit fidelity. For methods where the index is commit-insensitive (BM25, repomap_like), this is a valid speedup. Should we use mixed tracks?
3. **Priority ordering** — run the 5 zero-LLM + embedding-only methods first (fast, no agent variance), then the 6 agentic methods? This gives early directional data.

**E2. Patching campaign (T1): 123 manifests, ~500 total instances × 10 methods**

Current infrastructure: `tools/run_manifest_pool.py --max-parallel-repos N --run-workers N`
- `--max-parallel-repos`: number of repos running concurrently (same-repo manifests are sequential)
- `--run-workers`: issue-level parallelism within a single manifest (concurrent.futures thread pool)
- `--resume-incomplete`: skip completed manifests, resume partial runs

Observed timings from V1 pilot:
- N=100 instances (3 methods): ~6-8 hours per method, sequential
- V2 instance_wall_clock_cap: 600s per instance (10 min timeout)

**Naive sequential estimate (stage 1 only):** 500 instances × 10 methods × ~300s average = ~416 hours (~17 days).
With `--max-parallel-repos 3` + `--run-workers 2`: ~70 hours (~3 days).
With `--max-parallel-repos 8` + `--run-workers 4`: ~26 hours, but requires Gemini Flash burst capacity.

Stage 2 (Docker harness): ~2-5 min per instance, highly parallelizable (no API calls, only Docker containers). Available locally via Docker v28.4.0.

**Q: What is the acceptable wall-clock budget for the full patching campaign?**
1. Should we run stage 1 only (patches) for all manifests first, then stage 2 (harness eval) as a batch? This decouples API-bound work from compute-bound work.
2. What `--max-parallel-repos` / `--run-workers` combination balances speed vs API stability? The Gemini Flash rate limit is generous but untested at 8× concurrency.
3. Should we prioritize certain repos (e.g., django with 232 instances) or methods (e.g., oracle first to establish the ceiling)?

**E3. Total campaign wall-clock**

| Phase | Scope | Sequential estimate | With parallelism (conservative) | With parallelism (aggressive) |
|-------|-------|--------------------|---------------------------------|-------------------------------|
| T0: Retrieval | 9 repos × 11 methods × 10 issues | ~16.5 hours | ~8 hours (`--max-parallel 2`) | ~5 hours (`--max-parallel 3` + method partitioning) |
| T1: Patching Stage 1 | 123 manifests, ~5000 total runs | ~416 hours | ~70 hours (3 repos × 2 workers) | ~26 hours (8 repos × 4 workers) |
| T2: Patching Stage 2 | All completed Stage 1 data | ~25 hours | ~5 hours (Docker, 5-way parallel) | ~3 hours |
| **Total** | | **~457 hours (~19 days)** | **~83 hours (~3.5 days)** | **~34 hours (~1.5 days)** |

**Q: Given these estimates:**
1. Is the "conservative parallelism" timeline (~3.5 days) acceptable?
2. Should we run a smaller pilot first (e.g., 3 repos × 10 methods) to validate timing estimates before committing to the full campaign?
3. Are there methods we can deprioritize or drop entirely to reduce scope without losing analytical value? (e.g., `raw_rag_fixed` overlaps heavily with `raw_rag_function` — do we need both?)

---

## 4. Summary of Go/No-Go Decisions Requested

| # | Decision | Recommendation | Risk if wrong |
|---|----------|----------------|---------------|
| 1 | Tool asymmetry (2 vs 3 tools) | Acceptable with disclosure | Reviewer questions fairness |
| 2 | baseline/progressive naming | Rename to "compact/verbose" or keep with clear definition | Confusion in paper |
| 3 | agentless_like LLM validation | Run telemetry check (T6) before full campaign | Silent strawman comparison |
| 4 | repomap_like naming | Rebrand to "graph-PageRank" | Overclaiming vs prior work |
| 5 | cold_start "no retrieval" framing | Frame as "minimal agent tools, no index" | Reviewer challenges baseline integrity |
| 6 | 1 repeat on new repos | Acceptable if clearly labeled | Reviewer demands CIs on all cells |
| 7 | Baseline exclusion from patching | Acceptable — retrieval eval covers the ablation | Missing data point |
| 8 | agentless cost accounting | Report separately, note hybrid setup cost | Cost story confusion |
| 9 | Retrieval parallelism level | `--max-parallel 2` conservative, 3 with retry | Campaign takes too long or API instability |
| 10 | Patching parallelism level | 3 repos × 2 workers conservative | 3.5-day timeline may be unacceptable |
| 11 | Method pruning (drop `raw_rag_fixed`?) | Keep for now, drop if timeline demands | Missing granularity data point |

**Overall recommendation:** The method matrix is comprehensive and the ablation structure is sound. The two highest-risk items are (3) agentless LLM validation and (4) RepoMap naming. Both can be addressed with minimal effort before launch. The execution timeline is 3.5 days with conservative parallelism, which is manageable for a one-time research campaign. The most impactful speedup is method-level partitioning (run zero-LLM methods separately), which requires no new infrastructure.

---

*Files modified in this alignment session: `src/evaluation.py`, `tests/test_evaluation_logic.py`, `tools/generate_v2_verified_manifests.py`, `tests/test_generate_v2_verified_manifests.py`, `experiments_retrieval_expansion_v2.yaml`, `RESEARCH_INTENT.md`, `STATE.md`, `TASKS.md`. 258 tests passing.*
