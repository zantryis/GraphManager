# V2 Phase 3 Handoff — Experiment Design & Execution

*Written: 2026-02-23. For the next agent. Read after CURRENT_STATE.md and RESEARCH_INTENT.md.*

---

## Status Coming In

- Phase 1 (research): DONE — see `dev_logs/2026-02-23-v2-phase1-research.md`
- Phase 2 (engineering fixes): DONE — see `dev_logs/2026-02-23-v2-phase2-engineering.md`
- 161 tests pass: `./.venv/bin/python -m unittest discover -s tests -v`
- V1 results, paper, manifests: all frozen; do not re-run

## Locked Decisions (do not re-open)

| Decision | Resolution |
|----------|-----------|
| Patching benchmark | **SWE-bench Verified, all 500 instances** |
| BM25 impl | **`rank_bm25` library** (not Princeton bm25_27K dataset) |
| Patch agent tool access | **Option A — fixed context** (retrieval → fixed files → patch) |
| Repair samples per instance | **1** (single-sample; label this explicitly in paper) |
| Agentless comparison | **Published leaderboard numbers only** (different repair pipeline, incompatible) |
| Patching vs retrieval populations | Retrieval: Flask/Requests/Pytest; Patching: full Verified |

## Phase 3 Execution Plan

Work strictly in the order below. TDD applies to all code changes.
Do not start Step N+1 until Step N is verified.

---

### Step 1: Implement BM25 Retrieval Baseline

**File to create:** `src/bm25_baseline.py`

BM25 is a zero-LLM-cost lexical retrieval method. It tokenizes the issue text and scores
repo files by BM25 relevance. It must conform to the same interface as `gm_deterministic`
and `rag_baseline` so it plugs into the existing retrieval pipeline.

**Interface contract (match this exactly):**

```python
class BM25Index:
    def __init__(self, repo_dir: str, include_prefixes: tuple[str, ...] | None = None):
        ...

    def build(self) -> None:
        """Index all Python files in repo_dir (filtered by include_prefixes if set)."""
        ...

    def query(self, query_text: str, top_k: int = 10) -> list[str]:
        """Return top-k file paths ranked by BM25 score against query_text."""
        ...

    @property
    def embedding_tokens_estimate(self) -> int:
        """Return 0 — BM25 has no embedding cost."""
        return 0
```

**Implementation notes:**
- Use `rank_bm25` library (`pip install rank_bm25`). Check if already installed first.
- Tokenize files at function granularity (match RAG chunk strategy) OR at file granularity.
  File granularity is simpler and adequate for Tier 0. Document which you chose.
- Index only `.py` files matching `include_prefixes` if set.
- `query()` concatenates issue title + body, tokenizes (whitespace-split is fine), scores.
- Return file paths (not line numbers). Deduplicate if multiple chunks from same file.

**Tests to write first (TDD):**
- `test_bm25_baseline.py` in `tests/`
- Test: build on a temp dir with 3 files → query returns most relevant file first
- Test: `embedding_tokens_estimate` is always 0
- Test: empty repo returns empty list, no crash
- Test: `include_prefixes` correctly filters files
- Test: duplicate-file deduplication in results

**Wire into retrieval pipeline:**
- `run_experiment.py`: add `"bm25"` to supported methods list
- `src/evaluation.py`: add BM25Index import + build path (similar to RAG build path)
- `run_patch.py`: add `"bm25"` to retrieval method handling in `_run_retrieval()`

---

### Step 2: Symmetric Tool for rag_progressive

**File to modify:** `src/rag_baseline.py`

V1 rag_progressive had 1 tool (`semantic_search`) vs gm_progressive's 3 tools. This is a
known confound. Fix: give rag_progressive a `get_file_contents(path)` tool that returns the
raw file content from the repo.

**Tool spec:**
```python
def get_file_contents(path: str) -> str:
    """Return the full contents of the file at `path` in the checked-out repo.
    Returns an error string if the file doesn't exist."""
```

**Implementation notes:**
- Add this as an optional second tool to the RAG agent, enabled via a manifest flag:
  `rag_symmetric_tools: true` (default `false` for backward compatibility with V1)
- The tool reads from `repo_dir / path`. Clip to `patch_max_file_chars` to match patch agent.
- Do NOT add this tool to rag_deterministic or raw_rag (they are zero-LLM-cost methods).

**Tests to write first:**
- Tool returns correct file contents when file exists
- Tool returns error string when file doesn't exist (no crash)
- Tool respects max_chars clip

---

### Step 3: V2 Patching Manifests (SWE-bench Verified, 500 instances)

**File to create:** `tools/generate_v2_verified_manifests.py`

Generate manifests for the V2 patching pilot and full run. Use the existing
`tools/generate_n100_verified_manifests.py` as a reference template.

**V2 manifest structure:**

```
patch_manifests/v2_verified/
  oracle_v1.yaml              # All 500 instances, oracle retrieval
  gm_progressive_v1.yaml     # All 500 instances, gm_progressive
  bm25_v1.yaml               # All 500 instances, BM25 retrieval
  agentic_cold_start_v1.yaml # All 500 instances, agentic cold-start retrieval
  pilot_oracle_v1.yaml       # 8 instances from psf/requests, oracle
  pilot_gm_progressive_v1.yaml # 8 instances from psf/requests, gm_progressive
  pilot_bm25_v1.yaml         # 8 instances from psf/requests, BM25
```

**Manifest settings for V2 (update from V1 defaults):**
```yaml
dataset_name: SWE-bench/SWE-bench_Verified
split: test
instance_wall_clock_cap_s: 600   # was 480; bump for harder instances
patch_max_output_tokens: 65536
patch_max_file_chars: 200000
patch_max_turns: 1
patch_apply_repair_retries: 1
rate_limit_max_retries: 3
instance_wall_clock_cap_s: 600
```

**Instance selection:**
- Use ALL 500 SWE-bench Verified test instances (no custom split needed; the full set IS the benchmark)
- For the pilot manifests, select the 8 psf/requests instances only (Verified contains 8)
- Deterministic ordering: sort by instance_id for reproducibility

---

### Step 4: Small Pilot Run (before full run)

Run ONLY the pilot manifests first. This is the Phase 4 audit gate.

```bash
# Oracle pilot (requires Modal or Docker)
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml \
  --evaluate [--modal]

# BM25 pilot
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_bm25_v1.yaml \
  --evaluate [--modal]

# GM pilot
./.venv/bin/python run_patch.py \
  --manifest patch_manifests/v2_verified/pilot_gm_progressive_v1.yaml \
  --evaluate [--modal]
```

**Pilot validation gates (check all before proceeding to full run):**
1. Oracle resolved rate ≥ 25% (V1 was 50% on 8 requests instances)
2. BM25 resolved rate ≥ 0% (i.e., it generates non-empty patches)
3. GM resolved rate ≥ 0% (i.e., it generates non-empty patches)
4. `predictions_partial.jsonl` checkpoint written for all instances (E3 validation)
5. No `apply_failed` rate > 80% (would indicate patch format regression)
6. Token costs in expected range: oracle ~30K-80K/instance, GM ~50K-150K, BM25 ~20K-60K

**If pilot fails any gate:** stop, diagnose, fix before full run. DO NOT expand.

---

### Step 5: Adversarial Audit (Professor Mean)

After pilot passes gates, audit the V2 design before full runs. Key questions:

1. **Does BM25 match gm_deterministic on retrieval F1?**
   - Run BM25 retrieval experiment on psf/requests (n=10, same snapshot as V1 retrieval runs)
   - Compare F1 to V1 gm_deterministic (0.520). If BM25 ≥ gm_det, the graph's structural
     value needs to be justified through multi-hop traversal, not raw retrieval quality.

2. **Is the cost story still clean with 1 repair sample vs. Agentless's 40?**
   - Confirm: paper explicitly states "single-sample; for cost-efficient deployment framing"
   - Confirm: Agentless comparison uses their published numbers, not their 40-sample pipeline

3. **Does rag_progressive benefit significantly from the symmetric file-read tool?**
   - If yes: V1 rag_progressive F1 was partly due to tool asymmetry, not embedding quality
   - If yes: may need to re-run a retrieval comparison with rag_progressive_v2

4. **Are token costs still the right primary metric?**
   - The paper's money table is cost-per-resolved-issue. Confirm the single-sample approach
     doesn't make GM look worse just because oracle/agentless use more samples.

---

## Key Files for Phase 3

| File | Purpose |
|------|---------|
| `src/bm25_baseline.py` | NEW — BM25 retrieval index |
| `tests/test_bm25_baseline.py` | NEW — BM25 unit tests |
| `src/rag_baseline.py` | MODIFY — add symmetric file-read tool |
| `tools/generate_v2_verified_manifests.py` | NEW — manifest generator |
| `patch_manifests/v2_verified/` | NEW — V2 manifest directory |
| `run_experiment.py` | MODIFY — add BM25 as supported method |
| `src/evaluation.py` | MODIFY — add BM25 build path |
| `run_patch.py` | MODIFY — add BM25 to retrieval dispatch |
| `v2_next_session_plan.md` | Reference — Phase 3 design rationale |
| `dev_logs/2026-02-23-v2-phase1-research.md` | Reference — Agentless/RepoMap findings |

## What NOT to Do in Phase 3

- Do NOT run full 500-instance experiments before the pilot passes gates
- Do NOT modify V1 frozen results or the archived paper
- Do NOT implement the parallel E2 worker engine yet — park it
- Do NOT compare against Agentless by running their code (incompatible pipeline)
- Do NOT add `agentic_cold_start` to retrieval experiments — it belongs only in patching
- Do NOT change `patch_max_turns` above 1 without explicit researcher approval
- Do NOT re-run V1 retrieval experiments (matrix is frozen)

## Commit Policy

Follow CLAUDE.md strictly:
1. TDD: write failing tests before implementing
2. Run full test suite (`161` tests) before every commit
3. Commit manifests and code; never commit results/
4. Update CURRENT_STATE.md and write a dev log at end of session
