# 2026-02-24 - V2 no-manifest-timeout cutover and resume relaunch

## Context

- V2 full runs were stalling due hard per-manifest timeout wrappers (`4200s`, `timeout rc=124`).
- User requested removing manifest timeout and relying on per-issue caps to avoid data loss.
- Affected orchestration paths: `tools/run_manifest_pool.py`, active V2 scheduler/watchdog/recovery processes, and `results/v2_full_runs` execution continuity.

## Decision

- Use per-issue timeout only for V2 full runs (manifest timeout disabled).
- Resume incomplete manifests in-place from latest `run_dir` using checkpoint files.
- Keep 8-way repo concurrency.

Scope boundary:
- No change to per-issue limit semantics (`instance_wall_clock_cap_s` remains from manifest).
- No redefinition of evaluation protocol or manifest contents in this step.

## Alternatives Considered

1. Keep `4200s` manifest timeout and rely on repeated retries.
- Tradeoff: causes avoidable global manifest truncation and repeated restarts.

2. Increase manifest timeout to larger fixed value (e.g., `10800s`).
- Tradeoff: reduces but does not remove failure mode; still arbitrary cutoff.

3. Disable manifest timeout and enforce only per-issue cap (chosen).
- Tradeoff: single manifest can run longer wall-clock, but avoids dropping late issues and preserves full data coverage.

## Evidence

- Code behavior: `tools/run_manifest_pool.py` supports `--manifest-timeout-s <= 0` (no timeout wrapper) and `--resume-incomplete`.
- Tests: `./.venv/bin/python -m unittest tests.test_manifest_pool -v` (4/4 passing).
- Old processes observed with timeout wrappers and then terminated.
- Relaunched active pool command:
  - `./.venv/bin/python tools/run_manifest_pool.py --manifest-list logs/v2_full_manifests_20260223_222457.txt --results-dir results/v2_full_runs --max-parallel-repos 8 --manifest-timeout-s 0 --resume-incomplete --log logs/v2_repo_pool_20260224_012417_no_manifest_timeout.log --failure-log logs/v2_repo_pool_failures_20260224_012417_no_manifest_timeout.log`
- Active run evidence:
  - pool pid shows alive with 8 concurrent `run_patch.py` workers.
  - no `timeout ... run_patch.py` wrappers in active orchestration stack.

## Consequences

- Expected benefits:
  - Eliminates manifest-level truncation; reduces risk of missing late issues.
  - Resumes use existing `predictions_partial.jsonl` checkpoint continuity.
- Known risks:
  - Long-tail manifests can occupy repo slots for extended periods.
  - Requires monitoring for true per-issue hangs/failures.
- Monitoring signals:
  - `logs/v2_repo_pool_20260224_012417_no_manifest_timeout.log`
  - dashboard `/api/status` and per-manifest `last_seen_ts`.

## Follow-up

1. Monitor pool log for `W* DONE/FAIL` and ensure no `TIMEOUT` class events from manifest wrapper.
2. If a run fails, resume same manifest/run_dir via `--resume` to preserve issue-level coverage.
3. After completion, run a completeness audit: all manifests have `patch_summary.json` and no unresolved stalled rows.
