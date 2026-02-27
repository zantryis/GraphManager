# Fix: repo_name=null in patch_summary.json silently discarded all patching rows

**Date**: 2026-02-27
**Author**: Claude (T1 campaign audit + hotfix session)
**Severity**: Critical data pipeline bug (silent data loss at aggregation)

---

## Problem

`tools/aggregate_v2_results.py`'s `collect_patching_results()` was producing
**0 patching rows** even with 140 completed runs on disk.

Root cause: `run_patch_stage1()` wrote `repo_name` to `run_meta.json` at job start
but omitted it from the `patch_summary.json` dict at job end. Every completed run
had `"repo_name": null` in its summary. The aggregate script read that field, got
`repo = ""`, then silently skipped the run at:

```python
if not repo or not method: continue   # line 169 — discarded EVERYTHING
```

Before the fix, running `aggregate_v2_results.py` printed:
> 0 cells across 0 repos (patching)

After the fix:
> 114 cells across 12 repos (patching)

---

## Fixes

### 1. `tools/aggregate_v2_results.py` — run_meta.json fallback

Added fallback: when `patch_summary.json` has `repo_name=null`, read
`repo_name` from the adjacent `run_meta.json` (always present, always correct).

```python
repo = str(data.get("repo_name") or "")
if not repo:
    run_meta = _load_json(summary_path.parent / "run_meta.json")
    if run_meta:
        repo = str(run_meta.get("repo_name") or "")
```

This is a read-only fix — existing on-disk data is intact, aggregate now
correctly surfaces it.

### 2. `run_patch.py` Stage 1 summary dict

Added `"repo_name": repo_name` to the Stage 1 summary dict so **future runs**
write the field correctly and the fallback is never needed.

```python
summary = {
    "run_id": run_id,
    "manifest": manifest_path,
    "dataset_name": dataset_name,
    "retrieval_method": retrieval_method,
    "repo_name": repo_name,          # ← ADDED
    "retrieval_max_files_for_patch": retrieval_max_files_for_patch,
    ...
```

### 3. `run_patch.py` `_run_evaluate_only()` — manifest-based recovery

Added `repo_name` recovery from manifest alongside the existing `split` recovery,
so evaluate-only reruns on older Stage-1 output also populate the field correctly:

```python
if manifest_path and Path(manifest_path).exists():
    try:
        manifest = yaml.safe_load(Path(manifest_path).read_text())
        split = manifest.get("split", "test")
        if not summary.get("repo_name"):
            summary["repo_name"] = manifest.get("repo_name", "")
    except Exception:
        pass
```

---

## Tests added

- `tests/test_aggregate_v2_results.py`: `test_collect_patching_falls_back_to_run_meta_for_repo_name`
  — integration test with a real temp dir, patch_summary with `repo_name=null`,
  run_meta with correct name. Asserts the correct key appears in the output dict.

- `tests/test_run_patch_summary.py` (new file): source-structure regression test.
  Reads `run_patch.py` source, regex-locates the Stage-1 summary dict literal, and
  asserts `"repo_name"` appears. Guards against accidental deletion.

Test suite: **297 tests, all pass** (was 288 before this session).

---

## Campaign status at time of fix

- 140/135 completed run dirs with `patch_summary.json` (duplicates from concurrent pool coordinators)
- 112/132 unique (repo, method) pairs complete (20 missing: django 9 methods, sympy 7 methods + repomap_like for both)
- Two pool coordinators (PIDs 15549 and 32704) still running — will fill gaps automatically
- Killed PID 47095 (scikit-learn/repomap_like duplicate with 0 JSONL lines written; dir 20260227_082831 already complete at 32/32 lines)

---

## Non-actions

- django/gm_progressive (61/231 instances) and matplotlib/rag_progressive (33/34 instances) are
  stalled partials — pool coordinator 32704 will resume them via `--resume-incomplete`.
- sphinx/raw_rag_function: already complete, but a resume worker (PID 49586) is running against
  it — harmless, left to finish.
- 25 duplicate (repo, method) completion dirs: aggregate uses "latest wins" (by run_id
  timestamp sort) — all valid, just wasted compute.
