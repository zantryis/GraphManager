# TASKS.md -- Atomic task backlog

<!-- Rules:
  - Exactly ONE task may be [ACTIVE] at a time.
  - Only the researcher promotes tasks to [ACTIVE].
  - Agents mark tasks [DONE] when acceptance criteria are met.
  - Agents may add tasks as [BACKLOG] but may NOT self-promote them.
  - When a task is done, record the evidence (run ID, test output, commit SHA).
-->

---

## Active

*No active task. Researcher: assign one from Backlog below.*

---

## Backlog (prioritized)

### T0: Run retrieval expansion on 9 new repos (11 methods)
**Priority:** P0 (fixes population mismatch — STATE.md issue I1)
**Acceptance criteria:**
- `experiments_retrieval_expansion_v2.yaml` run to completion (9 repos x 11 methods x 10 issues)
- Results in `results/runs/` with summary.json per experiment
- Retrieval F1 values recorded in STATE.md
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** Config updated with explicit 11-method list. Partial results exist for seaborn (10 methods), pylint (10 methods), sphinx (3 methods). Run with `run_suite.py --max-parallel 2`. Agentic methods (cold_start, agentless_like) need LLM calls, so budget will be higher than the original 3-method plan.
**Command:** `./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml --max-parallel 2`

### T1: Complete Stage 1 for all V2 patching manifests (10 methods + oracle)
**Priority:** P0 (blocking everything downstream)
**Acceptance criteria:**
- All 123 manifests in `patch_manifests/v2_verified/` (12 repos x 10 methods + oracle + 3 pilots) have `predictions_partial.jsonl` or `predictions.json`
- Dashboard shows 0 pending/stalled rows for Stage 1
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** 123 manifests = 12 oracles + 3 pilots + 108 full (12 repos x 9 non-oracle methods). ~1500/4000 instances done from prior 8-method run. Pool is resumable: `tools/run_manifest_pool.py --resume-incomplete`

### T2: Run Stage 2 (SWE-bench harness) on all completed Stage 1 data
**Priority:** P0 (blocking results)
**Acceptance criteria:**
- Every run directory with a `predictions.json` also has `harness_output/` with `report.json`
- `patch_summary.json` contains `n_resolved` for each manifest
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T1
**Notes:** Docker is available locally (v28.4.0). No Modal needed.

### T3: Aggregate V2 results into scorecard
**Priority:** P1
**Acceptance criteria:**
- CSV/JSON artifact with columns: repo, method, n_instances, n_resolved, resolve_rate, CPR_method_accounted, CPR_as_run
- Covers all 12 repos x 10 methods (+ oracle)
- Retrieval F1 column included (from T0 + existing matrix data)
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T0, T2

### T4: Run priority ablations (max_turns, BM25 granularity)
**Priority:** P2
**Acceptance criteria:**
- At least 2 ablation variants run on pilot subset (8 instances)
- Results documented in dev log
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T3

### T5: Rewrite paper with V2 data
**Priority:** P2
**Acceptance criteria:**
- `research_report/main.tex` updated with V2 tables and figures
- Compiles clean (`pdflatex` + `bibtex`, 0 errors)
- All claims satisfy `CLAIMS_LOCK.md`
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T3

### T6: Validate agentless_like LLM path fires (not fallback)
**Priority:** P3 (quality)
**Acceptance criteria:**
- Telemetry added to `src/agentless_like_localization.py` showing LLM call count per run ✓
- At least 1 pilot run confirms LLM path executes (not silent deterministic fallback) — pending first T0 run
**Owner:** unassigned
**Status:** `[BACKLOG]` (code complete; live validation pending T0)
**Notes:** Added `stage1_llm_fired`, `stage2_llm_fired`, `stage3_llm_fired` booleans to `agentless_like_meta`. Unit tests (261 passing) verify flags work for client=None and client-present cases. `evaluation.py:827` confirms real client is passed in eval runs. Check flags in first T0 agentless_like run output.

### T7: Add fail-fast mode to dataset adapter
**Priority:** P3 (quality)
**Acceptance criteria:**
- `src/evaluation.py` dataset loading raises on split-load failure instead of silent skip
- Test covering the fail-fast behavior
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** See STATE.md known issue I4

### ~~T8: Fix seaborn source_prefixes in patching manifests~~
**Status:** `[DONE]` — Fixed 2026-02-25. Added `mwaskom/seaborn: ["seaborn"]` to `SOURCE_PREFIXES` in generator, regenerated all seaborn manifests.

### ~~T9: Dashboard UI rewrite~~
**Status:** `[DONE]` — 2026-02-25. Full redesign: slate dark theme, 3 tabs (Retrieval 12×11 grid + ETA / Patching / Campaign), new routes `/api/retrieval_status` + `/api/campaign_status`, `--campaigns-dir` arg. Data layer extended with `build_retrieval_status()` + `load_campaign_state()`. 11 new tests (274 total).

### T10: V2 campaign execution (async)
**Priority:** P0
**Acceptance criteria:**
- Dashboard shows 99/99 retrieval cells green (T0 done)
- All 123 patching manifests have Stage 1 predictions (T1 done)
- All Stage 1 runs have harness results (T2 done)
**Owner:** unassigned
**Status:** `[BACKLOG]` — ready to launch
**Command:** `PYTHONUNBUFFERED=1 ./.venv/bin/python tools/run_campaign.py campaigns/v2_full.yaml --resume`
**Notes:** Campaign runner handles sequencing (T0 pass1→pass2→pass3→T1→T2). Dashboard on port 5051. Run `--skip-completed` prevents re-runs on resume.

### T12: Fix missing bib entries
**Priority:** P1 (blocks LaTeX compilation)
**Acceptance criteria:**
- `references.bib` has valid entries for `aider2023` and `lv2011lower`
- `make -C research_report` compiles without bib errors
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** Both are cited in `sections/03_method.tex`. Missing entries will cause `bibtex` failure.

### T13: Implement correct bootstrap CIs for retrieval F1
**Priority:** P1 (paper statistical claims)
**Acceptance criteria:**
- Resample per-issue paired F1 deltas (not 3 run-level means as in V1 buggy impl)
- 10,000 resamples, 95% CI reported for each GM-vs-baseline pair
- Implemented in `tools/aggregate_v2_results.py`, outputs to `retrieval_ci.csv`
- Unit test with mock issue-level data
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T10 (needs T0 retrieval data)
**Notes:** V1 CI implementation (run_experiment.py:58-83) bootstraps 3 run means — critically wrong. V2 aggregation has no CI code at all.

### T14: Implement McNemar with instance-level vectors + Holm-Bonferroni
**Priority:** P1 (paper significance claims)
**Acceptance criteria:**
- `compute_mcnemar()` in `aggregate_v2_results.py` reads per-instance resolved/not-resolved from `predictions.json` files
- Pairwise tests: gm_progressive vs each of (rag_progressive, bm25, repomap_like, agentless_like, agentic_cold_start)
- Holm-Bonferroni correction applied across all tests
- Outputs p-values + corrected p-values to `mcnemar.txt`
- Unit test with mock binary vectors
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T10 (needs T2 Stage 2 resolved vectors)

### T15: Add binomial CIs to patching resolve rates
**Priority:** P1 (paper tables)
**Acceptance criteria:**
- Wilson 95% CIs added to `patching.csv` columns `ci_lower`, `ci_upper`
- LaTeX table shows `43% [38, 48]` format
- Implemented in `aggregate_v2_results.py`
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T10

### T16: Write Threats to Validity section
**Priority:** P2
**Acceptance criteria:**
- `sections/07_threats_to_validity.tex` covers at minimum:
  1. Single LLM provider (Gemini only — generalizability)
  2. Python-only evaluation
  3. SWE-bench population bias (popular, well-tested repos)
  4. LLM non-determinism despite temperature=0
  5. Agentless-like is graph-augmented (not faithful reproduction)
  6. repomap_like uses PageRank (not Aider's actual repo map)
  7. Single repair sample vs Agentless 40-sample
  8. Seaborn (n=2) and Flask (n=1) too small for per-repo analysis
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T11

### T11: T3 aggregation and paper filling
**Priority:** P1 (after T10 complete)
**Acceptance criteria:**
- `results/v2_scorecard/retrieval.csv` and `patching.csv` populated
- V2 paper sections 00, 01, 04, 05, 06, 07, 08 filled with data
- `research_report/main.tex` compiles clean
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T10
**Notes:** `tools/aggregate_v2_results.py` is ready. Section 03_method.tex already complete. References.bib preserved from V1.

---

## Done

| ID | Description | Evidence | Date |
|----|-------------|----------|------|
| -- | V2 infrastructure (BM25, symmetric tools, manifests, checkpoint, parallel, Modal, dashboard) | 242 tests pass, pilot gates passed | 2026-02-24 |
| -- | Provenance capture in run_patch.py | `_capture_provenance()` + Makefile smoke test | 2026-02-25 |
| -- | Model tracking in evaluation.py | `model_name` parameter added | 2026-02-25 |
| -- | Repo cleanup + all V2 work committed | PR #1 merged, 186 files, 242 tests pass | 2026-02-25 |
| -- | Retrieval expansion config generated | `experiments_retrieval_expansion_v2.yaml` (9 repos, SWE-bench Verified) | 2026-02-25 |
| -- | Parallel retrieval suite (`--max-parallel`) | `run_suite.py` + 4 tests, 246 total pass | 2026-02-25 |
| -- | API retry logic (embed_with_retry) | `src/api_retry.py` + 6 tests, wired into graph_builder + rag_baseline | 2026-02-25 |
| -- | Methods filter (`run_suite.py --methods`) | 3 tests in test_suite_config.py | 2026-02-25 |
| -- | V2 method matrix alignment | agentic_cold_start→retrieval, repomap/agentless→patching, 258 tests pass | 2026-02-25 |
| T8 | Fix seaborn source_prefixes | Added to SOURCE_PREFIXES in generator, regenerated manifests | 2026-02-25 |
| T9 | Dashboard redesign | 3-tab dark UI, 11 new tests, 274 total | 2026-02-25 |
| -- | run_suite --skip-completed | `_find_completed_methods()` + `--skip-completed` flag | 2026-02-25 |
| -- | Campaign runner | `tools/run_campaign.py` + `campaigns/v2_full.yaml` | 2026-02-25 |
| -- | T3 aggregation script | `tools/aggregate_v2_results.py` | 2026-02-25 |
| -- | Paper archival + V2 skeleton | `research_report/archive/v1/` + stubs + `03_method.tex` complete | 2026-02-25 |
