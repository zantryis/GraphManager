# STATE.md -- Current project status

Last updated: 2026-03-12 UTC
Last agent: Claude (V2 campaign COMPLETE — T1/T2/T3 all finished)

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
- V2 manifests: `patch_manifests/v2_verified/` (12 repos × 11 methods + oracle + 3 pilots = 135 manifests)
- Retrieval expansion config: `experiments_retrieval_expansion_v2.yaml` (12 repos, 12 methods including rag_metadata)
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
- **rag_metadata baseline** (2026-02-25): `RAGMetadataIndex` added to `src/rag_baseline.py`; wired into `src/evaluation.py` and `run_patch.py`; 12 new patching manifests generated; `rag_metadata` added to `ALL_METHODS` and retrieval expansion YAML. Isolates graph structure contribution from embedding-content choice.
- **Campaign reordered T1 → T2 → T0** (2026-02-25): T1 (patch Stage 1) runs first to capture retrieval F1 for all 11 patching methods × 500 instances for free. T0 now covers only 3 retrieval-only ablations (gm_baseline, rag_baseline, rag_metadata). T2 uses Modal.
- 288 unit tests passing (304 after T1 hotfix + T2 gap fix + git hang fix 2026-02-27)
- **P0 retrieval eval bug fixes** (2026-02-25, external rigor audit):
  - `evaluation.py`: extracted `_build_agentic_methods()`; ManagerAgent + RAGAgent now receive `model=model_name` (were silently falling back to `gemini-2.0-flash` while agentless/cold-start got `gemini-3-flash-preview`)
  - `evaluation.py`: `rag_progressive` + `rag_baseline` now receive `symmetric_tools=True` + `repo_dir` (were getting 1 tool vs GM's 3 — biased retrieval comparison)
  - `agentless_like_localization.py`: all 3 stage LLM calls now set `temperature=0.0` (were using API default ~1.0 — non-deterministic vs all other methods)
  - 3 new tests covering all three fixes; 291 tests total
  - No data corruption: agentless_like T1 manifests had not yet started; T0 retrieval eval has not started
- **Dashboard deduplication fix** (2026-02-27): `collect_dashboard_status()` was keeping the newest run by timestamp, causing stalled partial dirs to hide completed runs in `count_unique_manifests_complete`. Fix: when one run is `complete` and another is not, keep both records so the counter sees the complete one while active-only views still surface the live attempt. 1 new test (`test_collect_dashboard_status_prefers_complete_over_stalled_same_manifest`); **298 tests total, all pass**. Dashboard now shows 115/135 (was 108/135).
- **T1 campaign hotfix** (2026-02-27): `repo_name=null` in all 140 `patch_summary.json` files caused `aggregate_v2_results.py` to silently discard every patching run (0 rows). Root cause: `run_patch_stage1()` omitted `repo_name` from the Stage-1 summary dict. Three-part fix:
  - `tools/aggregate_v2_results.py`: fallback reads `repo_name` from adjacent `run_meta.json` when `patch_summary.json` has null — recovers all 140 completed runs on disk
  - `run_patch.py` Stage-1 summary dict: added `"repo_name": repo_name` — future runs write correctly
  - `run_patch.py` `_run_evaluate_only()`: added `repo_name` recovery from manifest alongside existing `split` recovery
  - 2 new tests (`test_collect_patching_falls_back_to_run_meta_for_repo_name`, source-structure `test_stage1_summary_dict_includes_repo_name`); **297 tests total, all pass**
  - Aggregate script now outputs `114 cells across 12 repos` (was `0 cells across 0 repos`)
  - Campaign status: **112/132 unique (repo, method) pairs complete** at time of fix; pool coordinators still running for remaining 20 pairs (django 9 methods, sympy 7 methods + repomap_like for both)

### V2 method matrix alignment (done 2026-02-25)

- `agentic_cold_start` added to retrieval eval `ALL_METHODS` (was patching-only)
- `repomap_like` + `agentless_like_localization` added to patching manifests (were retrieval-only)
- Retrieval expansion YAML updated: explicit 11-method `methods` list
- Manifest generator updated: FULL_METHODS now 10 (+ oracle), was 8
- RESEARCH_INTENT.md rewritten for V2 method matrix
- All code + tests aligned across retrieval and patching

**Retrieval eval methods (12):**
gm_deterministic, gm_progressive, gm_baseline, rag_progressive, rag_baseline,
raw_rag_function, raw_rag_fixed, rag_metadata, bm25, repomap_like,
agentless_like_localization, agentic_cold_start

**Patching methods (11 + oracle):**
oracle, gm_progressive, gm_deterministic, rag_progressive, raw_rag_function,
raw_rag_fixed, rag_metadata, bm25, agentic_cold_start, repomap_like, agentless_like_localization

(gm_baseline and rag_baseline excluded from patching — single-turn ablation variants)

### V2 experiment runs (COMPLETE 2026-03-04)

- **T1 (Stage 1 — patch generation)**: 135/135 manifests complete (12 repos × 11 methods)
- **T2 (Stage 2 — SWE-bench harness eval)**: 135/135 valid harness results (3 passes of t2_rerun.py)
- **T3 (aggregation)**: Final scorecard at `results/v2_scorecard/patching_table.tex`
- **Results archive**: `gm_v2_results.tar.gz` (results data + README guide)
- 159 valid runs, 44 stale/incomplete runs (from retries), 203 total run directories
- Pilot (psf/requests, n=8): oracle 50%, bm25 50%, gm_progressive 62.5%. All gates passed.
- Key results (resolve rate):
  - GM-P best: astropy 55%, pytest 63%, scikit-learn 59%, xarray 55%
  - django: RRX 57% (GM-P 56%), sympy: RRX 33% (GM-P 35%)
  - All-zero: seaborn (n=2), pylint (n=10); flask (n=1) noisy 100%

---

## What is next

See TASKS.md for the active task. T1/T2/T3 are all COMPLETE. Remaining:

1. ~~**T1 campaign**~~: **COMPLETE** (135/135 manifests, 2026-03-04)
2. ~~**T2 (harness eval)**~~: **COMPLETE** (135/135 valid results, 2026-03-04)
3. ~~**T3 (aggregation)**~~: **COMPLETE** (scorecard at results/v2_scorecard/, 2026-03-04)
4. **T4**: Priority ablations (if needed)
5. **T5**: Fill V2 paper sections with data (research_report/sections/)
6. **Statistical tests**: McNemar + Holm-Bonferroni (T14), bootstrap CIs (T13), binomial CIs (T15)
7. **Paper writing**: Threats to validity (T16), missing bib entries (T12)

---

## Known issues

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| I1 | HIGH | Retrieval population != patching population | **Fixed** 2026-02-25: experiments_retrieval_expansion_v2.yaml now covers all 12 patching repos (flask n=1, requests n=8, seaborn n=2 — SWE-bench Verified limits) |
| I2 | MEDIUM | Single repair sample vs Agentless 40-sample -- document explicitly | Open -- paper framing |
| I6 | MEDIUM | `repomap_like` and `agentless_like_localization` are adapted to file-list interface, not faithful reproductions | Open -- paper framing. Both methods return `list[str]` file paths (same as all methods); full files passed to patch agent. Original Aider uses an in-context repo map; original Agentless passes spans not full files. Comparison is valid within this framework but §3.2/§3.3 must state: "adapted to unified file-retrieval interface." |
| I3 | LOW | `agentless_like_localization` may fall through to deterministic fallback | Telemetry added (2026-02-25): `stage1/2/3_llm_fired` flags in `agentless_like_meta`. Integration wiring confirmed. Validate flags on first T0 agentless_like run. |
| I7 | HIGH | Bootstrap CI implementation wrong: resamples 3 run-level means, not per-issue deltas. Paper states 10K resamples; code uses 2K. CIs in V1 paper are artificially narrow. | Open — fix before paper submission. Correct impl: resample per-issue paired deltas (n=10 per repo). V2 has no CI code at all. |
| I8 | HIGH | McNemar test is non-functional stub: always outputs p=null. Instance-level resolved vectors needed from T2. | Open — implement after T2 completes. |
| I9 | MEDIUM | No Holm-Bonferroni correction on pairwise McNemar tests. With 5+ comparisons, familywise error ~23%. | Open — add correction when McNemar is implemented. |
| I10 | MEDIUM | No binomial CIs on patching resolve rates. Single-run data supports Wilson/Clopper-Pearson CIs. | Open — add to aggregate_v2_results.py before paper. |
| I11 | MEDIUM | Missing bib entries: `aider2023` and `lv2011lower` cited in sections/03_method.tex but absent from references.bib — LaTeX will not compile. | Open — add before paper compile. |
| I12 | MEDIUM | `agentless_like_localization` is graph-augmented (uses GM graph in Stage 2), not a faithful Agentless reproduction. Mentioned in §3 but must be prominently disclosed in §4 Experimental Setup and §7 Threats to Validity. | Open — paper writing. |
| I13 | MEDIUM | `repomap_like` uses PageRank on import graph, not Aider's actual compressed text map. Should be disclosed as "graph-PageRank baseline" not an Aider reimplementation. | Open — paper writing. |
| I14 | LOW | `aggregate_v2_results.py` "latest wins" silently replaces earlier results with no warning when multiple runs exist for same (repo, method). A bad re-run could corrupt tables. | Open — low urgency; add warning log. |
| I15 | LOW | No effect size reporting (Cohen's h, odds ratios) alongside McNemar p-values. | Open — paper writing. |
| I16 | LOW | No data availability statement (increasingly required by SE venues). | Open — paper writing. |
| I17 | LOW | `ALL_METHODS` in `run_experiment.py` missing `agentic_cold_start`. Repeat aggregation and pairwise CI code silently omits cold-start. V2 uses repeats=1 so no immediate bite, but latent bug. | Open — fix opportunistically. |
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
- Fix `ALL_METHODS` in `run_experiment.py` to include `agentic_cold_start` (see I17)
- Add warning log in `aggregate_v2_results.py` when multiple runs exist for same (repo, method) (see I14)
- Add data availability statement to paper (see I16)
- Recalibrate CLAIMS_LOCK.md after V2 data lands (N=500 changes power substantially vs V1 N=100)
- ~~T2 design gap~~: **FIXED** 2026-02-27 (commit 9d9c274). `_is_manifest_completed()` and `_find_latest_incomplete_run_dir()` now accept `evaluate_mode`; stage12 mode checks `harness_run_id`. 5 new tests.
- ~~Agentless git hang~~: **FIXED** 2026-02-27 (commit 9d9c274). `repo_git.close()` in finally block of `_run_repo_issue_batch()`. 1 structural test.
- Add `--manifest-timeout-s 7200` to agentless rerun pool as belt-and-suspenders (even after git close() fix).
