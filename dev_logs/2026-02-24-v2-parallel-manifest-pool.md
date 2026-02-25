# 2026-02-24 - Repo-Safe Parallel Manifest Pool Launch

## Context

- Sequential manifest execution was too slow for 48-manifest V2 sweep.
- Existing `run_patch.py --workers` path still falls back to sequential by design.
- Needed immediate throughput gains without corrupting repo checkouts.

## Decision

- Implement `tools/run_manifest_pool.py` to parallelize across repos, while keeping one active manifest per repo.
- Keep per-manifest timeout and unbuffered logs.
- Launch pool with `--max-parallel-repos 3` and temporarily `--exclude-repo astropy/astropy` because an astropy watchdog run was already active.

## Alternatives Considered

1. Enable `--workers` inside `run_patch.py`.
Tradeoff: not implemented yet; currently hard-falls to sequential.

2. Run many manifests blindly in parallel.
Tradeoff: unsafe for same-repo git checkouts and likely state races.

3. Repo-safe pool scheduler (chosen).
Tradeoff: extra orchestrator script, but immediate speedup with safe isolation.

## Evidence

- New script: `tools/run_manifest_pool.py`
- Launch artifacts:
  - `logs/v2_repo_pool_20260223_225215.log`
  - `logs/v2_repo_pool_failures_20260223_225215.log`
- Active concurrent manifests observed:
  - `django_django_agentic_cold_start_v1.yaml`
  - `matplotlib_matplotlib_agentic_cold_start_v1.yaml`
  - `mwaskom_seaborn_agentic_cold_start_v1.yaml`
  - plus existing astropy watchdog run.

## Consequences

- Expected benefits:
  - Wall-clock reduction from single-manifest serial flow to multi-repo parallel execution.
- Known risks:
  - API quota pressure can increase with concurrency.
  - More simultaneous logs/runs increase monitoring complexity.
- Monitoring signals:
  - `ps` for active `run_patch.py` count.
  - pool logs for START/DONE/FAIL/TIMEOUT events.
  - dashboard `/api/status` for active run rows and progress.

## Follow-up

1. Keep pool runner active and monitor failures.
2. After astropy watchdog completes, run pool again without `--exclude-repo astropy/astropy` for remaining astropy methods.
3. Replay any timed-out manifests from failure log.
