# 2026-02-24 - V2 stalled timeout recovery and rerun orchestration

## Context

- User reported stalled manifests during full V2 run and requested investigation + reruns to avoid missing data.
- Dashboard showed multiple stalled rows with partial progress and no summaries.
- Full-run scheduling was split between an 8-way repo pool and a watchdog chain.

## Decision

- Investigate stall cause from scheduler failure logs before rerunning.
- Resume stalled runs in-place (`--resume --run-dir`) instead of restarting from scratch.
- Increase rerun manifest timeout to `10800s` for recovery runs.
- Add a recovery daemon that monitors stalled rows and resumes when repo contention clears.

Scope boundaries:
- No retrieval/patch model behavior changes.
- No manifest content edits in this step.

## Alternatives Considered

1. Re-run stalled manifests from scratch
Tradeoff: simpler launch, but throws away partial checkpoint progress and extra cost.

2. Stop all schedulers and restart one clean orchestrator
Tradeoff: cleaner control plane, but interrupts in-flight work and risks losing active progress.

3. In-place resume + background recovery monitor (chosen)
Tradeoff: higher operational complexity, but preserves progress and avoids dropping data cells.

## Evidence

- Root cause confirmed: manifest timeout `rc=124` at `4200s`
  - `logs/v2_repo_pool_failures_20260223_225727.log` (7 agentic timeouts)
  - `logs/v2_full_failures_20260223_223555.log` (astropy agentic + astropy bm25 timeouts)
- Immediate reruns launched:
  - `logs/v2_recovery_sympy_agentic_20260224_005430.log`
  - `logs/v2_recovery_sphinx_agentic_20260224_005430.log`
- Recovery daemon:
  - script: `/tmp/v2_stalled_resume_queue.py`
  - log: `logs/v2_stalled_resume_queue_20260224_005835.log`

## Consequences

- Stalled manifests are now actively being resumed instead of remaining dead rows.
- Recovery is gated by repo-idle checks to avoid concurrent checkout contention.
- Remaining risk: scheduler overlap (watchdog vs pool) can still cause duplicate effort if not consolidated later.

## Follow-up

1. Monitor recovery daemon log and verify `patch_summary.json` creation for each previously stalled run.
2. After current pool/watchdog wave completes, consolidate orchestration to one queue controller.
3. Recompute completion matrix (`manifest -> summary presence`) and patch any remaining gaps.
