# STATE.md -- Current project status

Last updated: 2026-02-25
Last agent: Claude (repo cleanup + retrieval expansion planning session)

---

## Project Goal

Graph-based retrieval reduces total token cost for software issue resolution while
maintaining competitive pass@1. This is a **cost-efficiency paper**, not a quality-superiority paper.

Full scope: `RESEARCH_INTENT.md`. Permitted claims: `CLAIMS_LOCK.md`.

---

## What is done

### V1 (archived -- do not re-run)

- Retrieval matrix: 7 repos x 3 methods, 3 repeats on anchor repos. Table 3 complete.
- N=100 patching pilot: GM 43%, RAG 38%, Oracle 45%, None 3%. McNemar p=0.38.
- Paper: 15-page two-column draft (archived in research_report/).
- All V1 data frozen. Do not modify.

### V2 infrastructure (done)

- BM25 baseline: `src/bm25_baseline.py` (BM25Plus, file-level, regex tokenizer)
- Symmetric RAG tools: `rag_progressive` has `get_file_contents` via `rag_symmetric_tools: true`
- Agentic cold-start: `src/agentic_cold_start.py` (real agent with 3 filesystem tools)
- RepoMap-like: `src/repomap_like.py` (PageRank on file-level graph)
- Agentless-like: `src/agentless_like_localization.py` (3-stage hierarchical)
- V2 manifests: `patch_manifests/v2_verified/` (12 repos x 8 methods + 3 pilots)
- Retrieval expansion config: `experiments_retrieval_expansion_v2.yaml` (9 new repos from Verified)
- Checkpoint/resume: `--resume` flag, `predictions_partial.jsonl`
- Parallel stage 1: `--workers N`, isolated repo clones per worker
- Docker harness available locally (v28.4.0)
- Dashboard: `tools/patch_dashboard.py` on port 5051
- Run provenance: `run_meta.json` captures git SHA, manifest hash, dep versions
- Makefile: `make verify` / `make test` / `make smoke` / `make lint`
- 242 unit tests passing
- Scientific rigor audit: PASSED (2026-02-25) — no confounds, fair baselines, standard SWE-bench harness

### V2 experiment runs (partial)

- Pilot (psf/requests, n=8): oracle 50%, bm25 50%, gm_progressive 62.5%. All gates passed.
- Full 8-method campaign launched (96 manifests, 4000 instances). ~1500/4000 Stage 1 complete.
- Stage 2 (harness eval) NOT yet run on full campaign data.
- Pool was stopped due to method-matrix mismatch mid-run (4-method -> 8-method correction).
- Data on disk in `results/v2_full_runs/` is resumable.

---

## What is next

See TASKS.md for the active task. High-level sequence:

1. **T0: Retrieval expansion** — run retrieval eval on 9 new repos (align populations)
2. **T1: Complete Stage 1** for remaining patching manifests (resume pool)
3. **T2: Run Stage 2** (Docker harness eval) on all completed Stage 1 data
4. **T3: Aggregate scorecard** — retrieval F1 + patching resolve rate + CPR per repo
5. T4: Priority ablations
6. T5: Rewrite paper with V2 data

---

## Known issues

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| I1 | HIGH | Retrieval population != patching population | **Fix planned**: T0 expands retrieval to all 12 patching repos |
| I2 | MEDIUM | Single repair sample vs Agentless 40-sample -- document explicitly | Open -- paper framing |
| I3 | LOW | `agentless_like_localization` may fall through to deterministic fallback | Open -- T6 adds telemetry |
| I4 | LOW | Dataset adapter silently swallows split-load failures | Open -- T7 adds fail-fast |
| I5 | LOW | Seaborn manifests have `source_prefixes: []` (indexes entire repo) | Open -- T8 fixes |

---

## Parking Lot

<!-- Agents: append ideas here. Do NOT self-promote to active tasks. -->

- Consider `bm25_function` ablation (function-chunk BM25 vs file-level)
- Consider k=3 repair sample ablation on 50-instance pilot subset
- Add integration tests for harness interface
- Consider dropping seaborn from analysis (n=2 too small for meaningful comparison)
