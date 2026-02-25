# 2026-02-24 - V2 8-Way Concurrency + Run Directory Race Fix

## Context

- Researcher requested higher throughput (`8` parallel).
- Initial 8-way pool launch exposed a run directory allocation race:
  concurrent `run_patch.py` processes could hit `FileExistsError` in `_allocate_run_output_dir`.

## Decision

- Keep repo-safe external parallelism (`tools/run_manifest_pool.py`) and increase to 8 concurrent repos.
- Fix run-dir allocator for concurrent process safety by retrying on `FileExistsError`.
- Relaunch the 8-way pool after allocator fix so previously failed manifests are re-queued.

## Alternatives Considered

1. Keep 3-way pool and avoid allocator race surface.
Tradeoff: too slow for full sweep timeline.

2. Disable shared results dir per process.
Tradeoff: complicates aggregation/dashboard and still requires orchestration changes.

3. Make allocator race-safe (chosen).
Tradeoff: minimal code change, robust under concurrent starts.

## Evidence

- Code updates:
  - `run_patch.py`: `_allocate_run_output_dir` now retries on `FileExistsError`.
  - `tests/test_patch_runner.py`: added `test_allocate_run_output_dir_retries_when_mkdir_races`.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_runner.RunOutputDirAllocationTests -v` passed.
  - `./.venv/bin/python -m unittest discover -s tests -v` passed (`206` tests).
- Runtime artifacts:
  - 8-way pool launch log: `logs/v2_repo_pool_20260223_225727.log`
  - failure log: `logs/v2_repo_pool_failures_20260223_225727.log`
  - astropy watchdog run remains isolated (excluded from pool) to avoid same-repo overlap.

## Consequences

- Expected benefits:
  - Much higher manifest throughput via multi-repo parallel execution.
  - No immediate allocator collisions at launch under high concurrency.
- Known risks:
  - Higher concurrent API pressure may increase transient rate limits.
  - More in-flight runs increase operational complexity and monitoring needs.

## Follow-up

1. Monitor pool failure log and replay any timed-out manifests after sweep.
2. When astropy watchdog completes, include remaining astropy methods in pool replay pass.
3. Aggregate finished `patch_summary.json` artifacts for method-level scorecards.
