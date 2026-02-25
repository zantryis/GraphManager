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

### T0: Run retrieval expansion on 9 new repos
**Priority:** P0 (fixes population mismatch — STATE.md issue I1)
**Acceptance criteria:**
- `experiments_retrieval_expansion_v2.yaml` run to completion (9 repos x 3 methods x 10 issues)
- Results in `results/runs/` with summary.json per experiment
- Retrieval F1 values recorded in STATE.md
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** Config ready at `experiments_retrieval_expansion_v2.yaml`. Run with `run_suite.py`. Cheap — no Docker needed, ~2-4 hours API time. Must run BEFORE patching campaign to validate retrieval on new repos.
**Command:** `./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml`

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
**Notes:** Docker is available locally (v28.4.0). No Modal needed.

### T3: Aggregate V2 results into scorecard
**Priority:** P1
**Acceptance criteria:**
- CSV/JSON artifact with columns: repo, method, n_instances, n_resolved, resolve_rate, CPR_method_accounted, CPR_as_run
- Covers all 12 repos x 8 methods (+ oracle)
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

### T8: Fix seaborn source_prefixes in patching manifests
**Priority:** P3 (correctness)
**Acceptance criteria:**
- All 8 `mwaskom_seaborn_*_v1.yaml` manifests have `source_prefixes: [seaborn]` instead of `source_prefixes: []`
**Owner:** unassigned
**Status:** `[BACKLOG]`
**Notes:** Empty source_prefixes means the pipeline indexes the entire repo. Only 2 instances so low impact, but should be correct.

---

## Done

| ID | Description | Evidence | Date |
|----|-------------|----------|------|
| -- | V2 infrastructure (BM25, symmetric tools, manifests, checkpoint, parallel, Modal, dashboard) | 242 tests pass, pilot gates passed | 2026-02-24 |
| -- | Provenance capture in run_patch.py | `_capture_provenance()` + Makefile smoke test | 2026-02-25 |
| -- | Model tracking in evaluation.py | `model_name` parameter added | 2026-02-25 |
| -- | Repo cleanup + all V2 work committed | PR #1 merged, 186 files, 242 tests pass | 2026-02-25 |
| -- | Retrieval expansion config generated | `experiments_retrieval_expansion_v2.yaml` (9 repos, SWE-bench Verified) | 2026-02-25 |
