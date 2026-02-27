# 2026-02-27 — T1 Campaign Monitoring and Stalled Worker Recovery

## Session overview

Monitoring session for the T1 patch generation campaign. Pool PID 8246 (task `bli2am9bv`) was
confirmed alive; identified and recovered two stalled agentless workers; identified a T2 design gap.

---

## Findings

### 1. Pool alive (PID 8246)

`pgrep -af "run_manifest_pool"` confirmed PID 8246 running. Note: `pgrep -af "run_manifest_pool\|run_patch"`
with escaped `\|` gave exit code 1 — use separate pgrep calls or unescaped `|` with `-E` flag.

### 2. Completion count: 115/135 manifests

Python script using `patch_summary.json` glob + `run_meta.json` fallback: **115** unique (repo, method)
pairs complete. Pool's internal count at start: 117 (difference likely due to counting method on pilot
manifests and timestamp-vs-path matching).

Incomplete repos:
- django/django: 2/11 complete (agentic_cold_start, bm25)
- sympy/sympy: 3/11 complete (agentic_cold_start, bm25, oracle)

All other 10 repos: fully complete (11 methods each).

### 3. Stalled workers — W1 and W3

At 13:15 MST, discovered both active workers were stalled:

| Worker | PID  | Method              | Last output      | Elapsed stall |
|--------|------|---------------------|------------------|---------------|
| W1     | 8310 | django/agentless    | 01:33 AM MST     | ~10 hours     |
| W3     | 8309 | sympy/agentless     | ~22:50 yesterday | ~14.7 hours   |

Root cause: `git cat-file --batch-check` subprocesses (PIDs 8459, 8460, 8461) were sleeping,
waiting for stdin that the Python parent was not sending — classic GitPython deadlock symptom.
Pool has `--manifest-timeout-s 0` (no timeout), so the pool could not self-recover.

**Action**: Sent SIGTERM to 8309 and 8310. Pool coordinator (8246) detected rc=-15 and immediately
advanced both workers to next manifest in queue:

```
[13:17:28] W1 FAIL django/agentless rc=-15
[13:17:29] W1 START django/gm_deterministic mode=resume
[13:17:29] W3 FAIL sympy/agentless rc=-15
[13:17:29] W3 START sympy/gm_deterministic mode=resume
```

Agentless checkpoints preserved on disk: 45/231 instances (django), 8/75 (sympy).

### 4. T2 design gap identified

`_is_manifest_completed()` in `tools/run_manifest_pool.py` (line 25) checks for `patch_summary.json`
only, regardless of whether Stage 2 (harness) has been run. This means:

- T2 pool with `--evaluate-mode stage12 --resume-incomplete` would **SKIP** all 115 Stage-1-complete
  manifests (treats them as fully complete).
- T2 CANNOT run Stage 2 on already-done Stage 1 runs using the current pool code.

Modal IS configured (workspace: boblycheeee, token valid, created 2026-02-22).

Campaign state file (`campaigns/v2_full_state.json`): T1 status = "running" (set 2026-02-25T20:36).
Using `run_campaign.py --resume` would re-run T1 (competing with PID 8246) since T1 is not "done".

**Fix needed before T2**: Update `_is_manifest_completed()` to accept evaluate_mode and check harness
completion when mode=stage12 (e.g., `patch_summary.json` has non-null `n_resolved` or `harness_run_id`).
Alternatively, write a separate script that calls `_run_evaluate_only()` for each Stage-1-complete run dir.

### 5. make verify: PASSED

All 297 tests pass.

---

## Current state after session

- Pool PID 8246: alive
- W1: django/gm_deterministic (resume from 37/231)
- W3: sympy/gm_deterministic (resume from 5/75)
- W2: idle (no remaining standalone repos)
- Remaining: ~17 manifests (django 9 methods, sympy 8 methods, less the 2 now in progress)
- Agentless to re-run separately: django (186/231 remaining), sympy (67/75 remaining)

---

## Recommendations for researcher

1. **Agentless rerun**: After T1 completes for non-agentless methods, run a separate pool with
   `--manifest-timeout-s 7200` for the agentless manifests only to prevent git hang recurrence.
   Consider also investigating GitPython subprocess leak in agentless_like_localization.

2. **T2 design gap**: Before running T2 harness, fix `_is_manifest_completed` to distinguish
   Stage 1 from Stage 1+2 complete. Without this fix, T2 pool does nothing for all
   Stage-1-complete manifests.

3. **Unblock suggestion**: Run `_run_evaluate_only()` as a one-off script across all
   Stage-1-complete run dirs (no pool needed) if the code fix is not worth the effort.
