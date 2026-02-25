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

### T1: Complete Stage 1 for remaining V2 manifests
**Priority:** P0 (blocking everything downstream)
**Acceptance criteria:**
- All 96 manifests in `logs/v2_full_manifests_8method_20260224_100240.txt` have `predictions_partial.jsonl` or `predictions.json` in their run directory
- Dashboard shows 0 pending/stalled rows for Stage 1
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** ~1500/4000 instances done. Pool is resumable: `tools/run_manifest_pool.py --resume-incomplete`

### T2: Run Stage 2 (SWE-bench harness) on all completed Stage 1 data
**Priority:** P0 (blocking results)
**Acceptance criteria:**
- Every run directory with a `predictions.json` also has `harness_output/` with `report.json`
- `patch_summary.json` contains `n_resolved` for each manifest
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T1
**Notes:** Requires Docker or `--modal`. Modal credits should be checked first.

### T3: Aggregate V2 results into scorecard
**Priority:** P1
**Acceptance criteria:**
- CSV/JSON artifact with columns: repo, method, n_instances, n_resolved, resolve_rate, CPR_method_accounted, CPR_as_run
- Covers all 12 repos x 8 methods (+ oracle)
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Depends on:** T2

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
- Telemetry added to `src/agentless_like_localization.py` showing LLM call count per run
- At least 1 pilot run confirms LLM path executes (not silent deterministic fallback)
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** See STATE.md known issue I3

### T7: Add fail-fast mode to dataset adapter
**Priority:** P3 (quality)
**Acceptance criteria:**
- `src/evaluation.py` dataset loading raises on split-load failure instead of silent skip
- Test covering the fail-fast behavior
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** See STATE.md known issue I4

---

## Done

| ID | Description | Evidence | Date |
|----|-------------|----------|------|
| -- | V2 infrastructure (BM25, symmetric tools, manifests, checkpoint, parallel, Modal, dashboard) | 242 tests pass, pilot gates passed | 2026-02-24 |
| -- | Provenance capture in run_patch.py | `_capture_provenance()` + Makefile smoke test | 2026-02-25 |
| -- | Model tracking in evaluation.py | `model_name` parameter added | 2026-02-25 |
