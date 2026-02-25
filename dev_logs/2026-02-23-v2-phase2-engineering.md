# 2026-02-23 - V2 Phase 2 Engineering Fixes

## Context

V1 pilot complete. Starting V2 with pipeline improvements before new experiments.
Affected files: `run_patch.py`, `.claude/settings.local.json`, `tests/test_checkpoint_resume.py`.

## Decisions and Changes

### Settings (permissions)
Added `permissions.defaultMode: "bypassPermissions"` to `.claude/settings.local.json`.
The invalid `""` prefix on line 2 (from a previous session) was also removed.

### E1: Modal harness timeout bump (COMPLETE)
`timeout=300` → `timeout=600` in both `swebench_eval()` call sites:
- `_run_evaluate_only()` line ~803
- `run_patch_pipeline()` line ~1346
Motivation: one instance timed out at 296.67s in the V1 Modal pilot.

### E4: max_workers investigation (COMPLETE, no code change needed)
Finding: when `modal=True`, `run_evaluation.main()` routes to `run_instances_modal()` which
uses Modal `.starmap()` — all sandboxes run fully parallel regardless of `max_workers`.
The `max_workers=1 if modal else 4` was dead code for the modal path.
Fix: changed to `max_workers=4` always with a clarifying comment.
No behavior change; only correctness of intent.

### E3: Checkpoint/resume for Stage 1 (COMPLETE)
Three new functions added to `run_patch.py`:
- `_load_partial_checkpoint(run_dir)` → reads `predictions_partial.jsonl`, returns dict
- `_flush_instance_to_checkpoint(run_dir, iid, prediction, per_instance)` → appends one line
- `_merge_worker_predictions(run_dir, n_workers)` → merges N worker JSONL files (E2 prereq)

Stage 1 loop now:
1. Flushes each completed instance to `predictions_partial.jsonl` immediately after completion
2. On `--resume --run-dir <prior_run>`, loads checkpoint and skips already-done instances
3. Restores prior results into `per_instance_results` and `swebench_predictions` before loop

CLI changes: `--resume` flag added; `--run-dir` now also applies to resume mode.
New `run_patch_pipeline()` param: `resume: bool = False`.

TDD: wrote 12 tests in `tests/test_checkpoint_resume.py` before implementing.
All 12 pass.

### E2: Parallel Stage 1 with --workers N (SCAFFOLDED, execution engine pending)
Added to `run_patch.py`:
- `_distribute_instances(instances, n_workers)` → contiguous chunk distribution
- `--workers N` CLI flag (default=1, backward compatible)
- `n_workers` param added to `run_patch_pipeline()`
- When `n_workers > 1`: prints warning, falls back to sequential

Parallel execution engine NOT YET IMPLEMENTED. Design is documented in the code comment
in `run_patch_pipeline()`. Infrastructure in place: distribute + merge + checkpoint.
Remaining work: extract inner per-issue loop into `_run_worker_chunk()` then call via
`ThreadPoolExecutor`. See E2 in `v2_next_session_plan.md` for design constraints.

TDD: wrote 6 tests for `_distribute_instances`, 4 tests for `_merge_worker_predictions`
(total 10, all passing).

## Test Results

161 tests total (was 143). All pass.
- 143 original tests unchanged
- 18 new tests: 12 checkpoint/resume + 6 distribute_instances

## Follow-up

1. Implement `_run_worker_chunk()` to complete E2 parallel execution engine
2. Validate `--resume` with a real interrupted run before using in production
3. Validate `--workers 2` on n=10 pilot (1 repo) before using at scale
