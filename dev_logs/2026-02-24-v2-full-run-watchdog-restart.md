# 2026-02-24 - V2 Full-Run Watchdog Restart

## Context

- Original full-run launcher (`logs/v2_full_run_20260223_222457.log`) remained stuck on manifest #1 for ~8h with no additional log lines.
- Runner and child process were alive, but no `patch_summary.json` artifacts were being produced.

## Decision

- Stop the stalled runner and restart full V2 queue with a watchdog launcher.
- Keep same manifest list and results root; rely on per-manifest completion-skip logic.

## Alternatives Considered

1. Wait longer on the original process.
Tradeoff: no observability and no bounded failure behavior.

2. Restart exact same launcher only.
Tradeoff: risks repeating silent stall mode.

3. Restart with watchdog + unbuffered logs (chosen).
Tradeoff: introduces timeout/continue policy at launcher layer, but preserves throughput and debuggability.

## Evidence

- Stalled run:
  - `logs/v2_full_run_20260223_222457.log` had only START lines for manifest #1.
  - Process remained alive (`run_patch.py` on `astropy_astropy_agentic_cold_start_v1.yaml`) with no artifact progress.
- Restarted run artifacts:
  - `logs/v2_full_kickoff_20260223_223555.txt`
  - `logs/v2_full_run_20260223_223555.log`
  - `logs/v2_full_failures_20260223_223555.log`
  - runner script: `/tmp/v2_full_runner_watchdog_20260223_223555.sh`
- New runner behavior confirmed by immediate unbuffered output in log (run header + issue listing).

## Consequences

- Expected benefits:
  - Visible, real-time log output.
  - One hung manifest no longer blocks entire 48-manifest sweep.
- Known risks:
  - Timeout threshold (4200s/manifest) may terminate a legitimately long manifest.
  - Continue-on-failure requires post-run failure replay for strict completeness.
- Monitoring signals:
  - `tail -f logs/v2_full_run_20260223_223555.log`
  - `logs/v2_full_failures_20260223_223555.log`
  - dashboard API `/api/status`

## Follow-up

1. Let watchdog runner progress through queue.
2. Re-run timed-out/failed manifests after primary sweep completes.
3. Aggregate completed summaries under `results/v2_full_runs/patch_runs/*/patch_summary.json`.
