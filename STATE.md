# STATE.md -- Current project status

Last updated: 2026-02-25
Last agent: Claude (V2 campaign launch prep session)

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
- V2 manifests: `patch_manifests/v2_verified/` (12 repos x 10 methods + oracle + 3 pilots = 123 manifests)
- Retrieval expansion config: `experiments_retrieval_expansion_v2.yaml` (9 repos, 11 methods)
- Checkpoint/resume: `--resume` flag, `predictions_partial.jsonl`
- Parallel stage 1: `--workers N`, isolated repo clones per worker
- Parallel retrieval suite: `run_suite.py --max-parallel N` (repo-level concurrency)
- Docker harness available locally (v28.4.0)
- Dashboard: `tools/patch_dashboard.py` on port 5051
- Run provenance: `run_meta.json` captures git SHA, manifest hash, dep versions
- Makefile: `make verify` / `make test` / `make smoke` / `make lint`
- 263 unit tests passing
- Scientific rigor audit: PASSED (2026-02-25)
- API retry logic: `src/api_retry.py` (embed_with_retry for 503/429 transients)
- `run_suite.py --methods` CLI filter for method selection
- agentless_like LLM telemetry: `stage1/2/3_llm_fired` flags in `agentless_like_meta` (2026-02-25)
- patch_agent retry: `generate_content` wrapped with `_call_with_retry` (retries=3, initial_delay_s=6.0) — prevents silent instance failures on 429 (2026-02-25)
- Parallelism defaults raised: retrieval `--max-parallel 4` (was 1), patching `--max-parallel-repos 6 --run-workers 2` (was 3/1) (2026-02-25)
- **Dashboard redesign** (2026-02-25): 3-tab dark-theme dashboard (Retrieval | Patching | Campaign); `src/patch_dashboard.py` adds `build_retrieval_status()` + `load_campaign_state()`; `tools/patch_dashboard.py` fully rewritten; ETA on retrieval grid
- **run_suite.py skip-completed** (2026-02-25): `--skip-completed` flag + `_find_completed_methods()` — re-runs skip already-finished (repo, method) cells
- **Campaign runner** (2026-02-25): `tools/run_campaign.py` + `campaigns/v2_full.yaml` — 5-step T0/T1/T2 campaign, resumable via `--resume`
- **T3 aggregation script** (2026-02-25): `tools/aggregate_v2_results.py` — outputs retrieval.csv, patching.csv, retrieval_table.tex, patching_table.tex, mcnemar.txt from all V2 runs
- **Paper archival** (2026-02-25): V1 content moved to `research_report/archive/v1/`; V2 `main.tex` + section stubs created; `sections/03_method.tex` written in full (all 11 retrieval methods, §3.1–3.4)
- 274 unit tests passing (was 263 before this session)

### V2 method matrix alignment (done 2026-02-25)

- `agentic_cold_start` added to retrieval eval `ALL_METHODS` (was patching-only)
- `repomap_like` + `agentless_like_localization` added to patching manifests (were retrieval-only)
- Retrieval expansion YAML updated: explicit 11-method `methods` list
- Manifest generator updated: FULL_METHODS now 10 (+ oracle), was 8
- RESEARCH_INTENT.md rewritten for V2 method matrix
- All code + tests aligned across retrieval and patching

**Retrieval eval methods (11):**
gm_deterministic, gm_progressive, gm_baseline, rag_progressive, rag_baseline,
raw_rag_function, raw_rag_fixed, bm25, repomap_like, agentless_like_localization,
agentic_cold_start

**Patching methods (10 + oracle):**
oracle, gm_progressive, gm_deterministic, rag_progressive, raw_rag_function,
raw_rag_fixed, bm25, agentic_cold_start, repomap_like, agentless_like_localization

(gm_baseline and rag_baseline excluded from patching — single-turn ablation variants)

### V2 experiment runs (partial)

- Pilot (psf/requests, n=8): oracle 50%, bm25 50%, gm_progressive 62.5%. All gates passed.
- Full 8-method campaign partially completed (~1500/4000 Stage 1 instances).
  Stopped mid-run to align method matrix (now 10-method).
- Data on disk in `results/v2_full_runs/` is resumable.
- Retrieval expansion partial results:
  - seaborn (10 methods): GM(p)=0.667, RAG(p)=0.400, BM25=0.258
  - pylint (10 methods): GM(p)=0.517, RAG(p)=0.477, BM25=0.181
  - sphinx (3 methods only, incomplete): GM(p)=0.663, RAG(p)=0.695, BM25=0.140
- Stage 2 (harness eval) NOT yet run on full campaign data.

---

## What is next

See TASKS.md for the active task. High-level sequence:

1. **Launch campaign**: `PYTHONUNBUFFERED=1 ./.venv/bin/python tools/run_campaign.py campaigns/v2_full.yaml --resume`
   - T0 pass 1 (embed-only, max-parallel 8) → T0 pass 2 (single-turn, 4) → T0 pass 3 (multi-turn, 3) → T1 → T2
   - Dashboard at `tools/patch_dashboard.py --port 5051` shows live Retrieval grid + Campaign steps
2. **Monitor** via dashboard. Wake Claude when campaign tab shows T2 done.
3. **T3**: `python tools/aggregate_v2_results.py --results-root results --output-dir results/v2_scorecard`
4. **T4**: Priority ablations (if needed)
5. **T5**: Fill V2 paper sections with data (research_report/sections/)

---

## Known issues

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| I1 | HIGH | Retrieval population != patching population | **Fixed** 2026-02-25: experiments_retrieval_expansion_v2.yaml now covers all 12 patching repos (flask n=1, requests n=8, seaborn n=2 — SWE-bench Verified limits) |
| I2 | MEDIUM | Single repair sample vs Agentless 40-sample -- document explicitly | Open -- paper framing |
| I3 | LOW | `agentless_like_localization` may fall through to deterministic fallback | Telemetry added (2026-02-25): `stage1/2/3_llm_fired` flags in `agentless_like_meta`. Integration wiring confirmed: `evaluation.py:827` passes real client. Validate flags on first T0 agentless_like run. |
| I4 | LOW | Dataset adapter silently swallows split-load failures | Open -- T7 adds fail-fast |
| I5 | LOW | Seaborn manifests have `source_prefixes: []` (indexes entire repo) | **Fixed** 2026-02-25 |

---

## Parking Lot

<!-- Agents: append ideas here. Do NOT self-promote to active tasks. -->

- Consider `bm25_function` ablation (function-chunk BM25 vs file-level)
- Consider k=3 repair sample ablation on 50-instance pilot subset
- Add integration tests for harness interface
- Consider dropping seaborn from analysis (n=2 too small for meaningful comparison)
- s_hint ablation (w_hint=0) to test lexical vs structural contribution (gap_analysis_v1 Tier 2 item)
- CALLS-only vs IMPORTS-only graph ablation (gap_analysis_v1 Tier 2 item)
