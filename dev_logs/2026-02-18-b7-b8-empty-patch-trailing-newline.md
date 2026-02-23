# 2026-02-18 - B7+B8: Empty patch submission and missing trailing newline

## Context

Oracle pilot run (20260218_150316, gold files → PatchAgent, no retrieval) reported
`resolved: 0` and `empty_patch_instances: 8` from the harness. This is impossible if
the pipeline is working correctly — an oracle with gold files should resolve at least
a few instances. This triggered a full investigation of the evaluation pipeline.

Affected files: `src/patch_agent.py`, `run_patch.py`, `tests/test_patch_agent.py`,
`tests/test_patch_runner.py`.

---

## Decision

Fix two independent bugs that combine to suppress all harness-evaluated scores:

**B8** (`src/patch_agent.py`): `extract_patch()` calls `.strip()` which removes any
trailing `\n`. Patch utilities (`patch -u`, used by the SWE-bench harness) require a
terminal newline; without it they emit "patch unexpectedly ends in middle of line" and
refuse to apply. Fix: append `\n` if the returned patch does not already end with one.
Applies to both the `<patch>` tag path (line 100) and the raw-diff fallback (line 87).

**B7** (`run_patch.py`): Predictions submitted to the harness used
`patch_text if status == "patched" else ""`. Any patch that failed our local
`git apply --check` got submitted as an empty string — the harness counted it as
`empty_patch_instances` and never evaluated it. The local check is diagnostic only;
the harness is the ground truth evaluator. Fix: extract `_make_swebench_prediction()`
helper using `patch_text or ""`, which submits the patch regardless of local check
outcome. `patch_text` is `None` only for `no_patch` status (model returned nothing),
in which case `or ""` correctly yields an empty string.

`apply_success_rate` is left unchanged — it continues to measure local `git apply --check`
pass rate as a pipeline diagnostic; it does not affect what reaches the harness.

Scope boundary: `patch_status` field in per-instance results and summary JSON is
unchanged. The local apply-check loop and repair retries are unchanged — they remain
useful for improving patch quality before submission.

---

## Alternatives Considered

1. **Remove local apply-check entirely** — Simpler. But the check still provides useful
   signal for the repair-retry loop (failure message is fed back to the model). Keeping
   it as a retry driver is correct; just don't use it to gate harness submission.

2. **Add `\n` at the point where patch is written to disk** — Also correct, but the bug
   also affects the in-memory string submitted via `model_patch`, so the fix needs to be
   in `extract_patch`. Fixing at the source is cleaner than fixing in the pipeline.

3. **Normalise patches in `_git_apply_check`** — Would fix the local check but not the
   harness submission. Does not address B7 at all.

---

## Evidence

**Oracle run (20260218_150316):**
- Harness report: `graphmanager-oracle.graphmanager_20260218_150316.json`
  → `empty_patch_instances: 8`, `resolved_instances: 0`
- Predictions file: all 8 entries had `"model_patch": ""`
- Patch files on disk: 7 non-empty `.patch` files (1 was CANNOT_PATCH)
- Cascade: B8 → local apply check rejected patches → B7 → submissions empty → harness zeroed

**gm_progressive run (20260218_133013):**
- `psf__requests-1921`: passed local check but harness rejected with
  "patch unexpectedly ends in middle of line" (B8 surviving into predictions)
- `psf__requests-2317`: applied in harness but wrong semantic fix → unresolved
  (model quality issue, not pipeline bug; out of scope here)

**Trailing newline confirmed missing:**
```
$ cat -A results/patch_runs/20260218_150316/patches/psf__requests-1766.patch
...
         return 'Digest %s' % (base)   ← no trailing $
```

**Tests written (TDD):**
- `test_extract_patch_adds_trailing_newline` — B8 tagged path
- `test_extract_raw_unified_diff_adds_trailing_newline` — B8 fallback path
- `test_apply_failed_patch_included_in_predictions` — B7
- `test_no_patch_yields_empty_model_patch` — B7 negative case
- `test_patched_status_included_in_predictions` — B7 positive case (regression guard)
- Updated `test_multiline_patch_preserved` — now asserts `diff.strip() + "\n"`

All 3 tests failed before fix; all 112 tests pass after fix.

---

## Consequences

**Benefits:**
- Oracle run should now show non-zero `resolved_rate` — first valid ceiling measurement.
- All previous runs with `apply_failed` patches were silently discarded; results were
  not just low but entirely invalid. Post-fix results are comparable across methods.
- Repair retry feedback loop still functions; no regression in retry behaviour.

**Risks:**
- Harness will now try to apply patches that previously returned empty strings.
  Some of these will fail in the harness (`error_instances`), which is equivalent
  in score to the previous `empty_patch_instances`. No regression in resolved count
  from previously-patched instances.
- `apply_success_rate` remains > 0 only when local git-apply passes. This metric
  is now purely diagnostic; do not use it as a quality gate.

**Monitoring signals post-fix:**
- Oracle run: expect `resolved_rate > 0` (≥ 1/8)
- `empty_patch_instances` in harness report: should drop significantly
- `apply_success_rate` in patch_summary.json: unchanged (diagnostic only)

---

## Follow-up

1. Re-run oracle manifest (`swebench_verified_requests_oracle_v1.yaml`) with
   `--evaluate` to confirm `resolved > 0`.
2. Re-run 8-instance requests baseline (gm_progressive) with `--evaluate` to
   establish a valid first baseline for the paper.
3. All prior run summaries (20260218_*) are invalid due to B7+B8; do not cite
   their `resolved_rate` values in the paper.
