# 2026-02-24 - V2 Concurrency Safety and Monitoring Follow-up

## Context

- Concurrent V2 pilot launches exposed two collision hazards:
  1. harness run IDs were keyed only by `run_id` second-level timestamp,
  2. output run directories also used second-level timestamp and could collide in shared `--results-dir`.
- User asked to proceed with recommended follow-up steps and to assess speed + dashboard viability.

## Decision

- Added collision-safe harness run ID generation in `run_patch.py`.
- Added collision-safe run directory allocation in `run_patch.py`.
- Produced compact pilot comparison artifact for V2 docs.
- Assessed dashboard reuse: existing `../dag-lbmas/dashboard/server.py` is reusable in UI pattern only; backend schema is incompatible as-is.

## Alternatives Considered

1. Keep current IDs/paths and rely on staggered process starts
   - Fast to do, but still brittle and operator-dependent.
2. Add random-only suffixes
   - Avoids collisions, but weak reproducibility and awkward evaluate-only continuity.
3. Deterministic method/path-scoped IDs + suffix-on-collision output dirs (chosen)
   - Reliable under concurrency, reproducible, and backward-compatible for evaluate-only.

## Evidence

- Code changes:
  - `run_patch.py`
    - `_build_harness_run_id(...)`
    - `_allocate_run_output_dir(...)`
    - wired into Stage1+2 evaluation and evaluate-only paths
  - `tests/test_patch_runner.py`
    - `HarnessRunIdTests`
    - `RunOutputDirAllocationTests`
- New artifact:
  - `docs/V2_PILOT_RESULTS_2026-02-24.md`
- Updated run design notes:
  - `docs/V2_RUN_DESIGN_2026-02-24.md`

## Consequences

- Expected benefits:
  - Concurrent runs no longer share harness IDs or output directories by timestamp collision.
  - Better safety for full V2 multi-manifest launches.
- Known risks:
  - Old runs without `harness_run_id` field still rely on reconstructed IDs; fallback remains supported.
- Monitoring signals:
  - `patch_summary.json` now carries stable `harness_run_id` for post-hoc traceability.

## Follow-up

1. Build GraphManager-specific dashboard adapter endpoint over `results/**/patch_runs/*` if browser-based live monitoring is needed.
2. Keep process-level concurrency with isolated workdirs for large sweeps.
3. Validate full-run launch orchestration with at least one same-second concurrent dry run.
