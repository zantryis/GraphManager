# V2 Readiness Audit + T6: agentless_like LLM telemetry

Date: 2026-02-25
Session type: Research audit + code change

---

## What was done

### 1. V2 Full-Run Readiness Audit

Conducted a full Go/No-Go audit on the V2 experiment design. All 11 decisions resolved:

**Method-level:**
- A1 Tool asymmetry (2 vs 3 tools): **GO** — architectural comparison, not tool-count experiment. Disclose in paper.
- A2 baseline/progressive naming: **GO** — keep code names, add clear paper definitions (progressive = compact/focused, baseline = verbose/exploratory).
- A3 agentless_like LLM validation: **CONDITIONAL GO** — T6 telemetry implemented; live validation on first T0 run.
- A4 repomap_like naming: **GO** — rebrand to "graph-PageRank" in paper text only.
- A5 cold_start framing: **GO** — "no-index agent (lexical path tools only)."

**Ablation structure:** All four axes (index type, agent value-add, compactness/exploration, cost tiers) accepted. gm_deterministic B1/B2 confound acknowledged and disclosed.

**Population/stats:**
- C1 n=10 subset: GO
- C2 1 repeat on new repos: GO with clear anchor/expansion labeling
- C3 N=500 power: GO — ~80% power for 5pp gap; confirmatory framing acceptable for large effects

**Cost:**
- D1 Drop V2 dual-build disclosure: GO — V2 is method-scoped. Keep disclosure only for V1 numbers.
- D2 agentless_like cost: GO — separate row in cost table, labeled "hybrid: graph + embed."

**Execution:**
- E1 Retrieval parallelism: GO — `--max-parallel 2` with 3-pass method partitioning (zero-LLM → embedding-only → agentic).
- E2 Patching parallelism: GO — `--max-parallel-repos 3 --run-workers 2`. Oracle first.
- E3 Timeline: GO — 3.5 days acceptable. Pilot 3 repos × 10 methods before full campaign.

### 2. T6: agentless_like LLM telemetry (code change)

**Problem:** STATE.md I3 — `agentless_like_localization` could silently fall through to deterministic fallback if `client=None`. No existing telemetry to detect this.

**Solution:** Added `stage1_llm_fired`, `stage2_llm_fired`, `stage3_llm_fired` boolean flags to `agentless_like_meta` in `find_relevant_files`.

**Files changed:**
- `src/agentless_like_localization.py`: Added 3 local `*_llm_fired` variables, set them to `True` inside each LLM `if` branch, included in `usage["agentless_like_meta"]`.
- `tests/test_agentless_like_localization.py`: 3 new tests covering client=None (all False), client+stages enabled (all True), client+stages disabled (stage1 True, stages 2/3 False).

**Test count:** 258 → 261, all passing.

**Integration verification:** `evaluation.py:827` confirms real Gemini client is passed to `AgentlessLikeLocalizer`. The LLM conditions (`client is not None and file_branch_top_n > 0 and candidate_pool`) will all be True in real runs with non-trivial issues.

**Remaining gate:** First T0 run should include `agentless_like_localization` method and verify `stage1_llm_fired=true` in result JSON. This closes I3.

---

## Execution plan for researcher (STOP — requires human approval before launch)

The audit is complete. The following execution sequence is ready for human sign-off before launching expensive API work:

### Phase 1: T0 — Retrieval expansion
Command (3-pass method-partitioned):
```bash
# Pass 1: zero-LLM (no quota risk)
PYTHONUNBUFFERED=1 ./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml \
  --methods bm25,repomap_like --max-parallel 3

# Pass 2: embedding-only
PYTHONUNBUFFERED=1 ./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml \
  --methods gm_deterministic,raw_rag_function,raw_rag_fixed --max-parallel 2

# Pass 3: agentic (includes agentless_like — verify stage*_llm_fired on first result)
PYTHONUNBUFFERED=1 ./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml \
  --methods gm_progressive,gm_baseline,rag_progressive,rag_baseline,agentless_like_localization,agentic_cold_start --max-parallel 2
```
Estimate: ~8-10 hours total.

### Phase 2: T1 — Stage 1 patching (pilot 3 repos first)
```bash
# Pilot: anchor repos only (validate timing)
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list <(ls patch_manifests/v2_verified/*flask* patch_manifests/v2_verified/*requests* patch_manifests/v2_verified/*pytest*) \
  --results-dir results/v2_full_runs --max-parallel-repos 3 --run-workers 2 --resume-incomplete

# Full: all 123 manifests (after pilot validates)
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list <(ls patch_manifests/v2_verified/*.yaml) \
  --results-dir results/v2_full_runs --max-parallel-repos 3 --run-workers 2 --resume-incomplete
```
Estimate: ~70 hours. Run oracle manifests first (12 oracle yamls) to establish ceiling.

### Phase 3: T2 — Stage 2 harness eval
Run Docker harness on all completed Stage 1 predictions.json files.

### Phase 4: T3 → T5
Aggregate scorecard → paper rewrite.
