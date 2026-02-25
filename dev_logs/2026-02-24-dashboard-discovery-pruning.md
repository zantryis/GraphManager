# 2026-02-24 - Dashboard Discovery Pruning for Run-Scoped Repo Clones

## Context

- Dashboard UI appeared empty/intermittent after stage-1 moved to run-scoped clone directories (`_repos`).
- `/api/status` could hang/timed out while scanning `results/v2_full_runs`.
- Existing discovery used recursive globbing from root (`rglob("patch_runs/*")`), which became expensive once run directories included full repo clones.

## Decision

- Replaced recursive glob discovery with pruned `os.walk` in `src/patch_dashboard.py`:
  - Skip `_repos` subtrees.
  - When encountering `patch_runs`, collect only immediate run-dir children and stop descending there.

Scope boundaries:
- No schema/UI payload changes.
- No run orchestration changes.

## Alternatives Considered

1. Increase HTTP timeout only
- Masks the issue; still expensive and unstable under growth.

2. Keep recursive glob and add caching
- More complexity, stale-cache risk, and still slow cold scans.

3. Prune traversal to known structure (chosen)
- Minimal code, deterministic behavior, immediate latency fix.

## Evidence

- Code updated:
  - `src/patch_dashboard.py` (`discover_run_dirs`)
- Validation:
  - `./.venv/bin/python -m unittest tests/test_patch_dashboard.py -v` (pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (224 tests, pass)
- Runtime check:
  - `curl http://127.0.0.1:5051/api/status` returns promptly with running rows.

## Consequences

- Expected benefits:
  - Dashboard API no longer blocked by deep `_repos` scans.
  - UI remains responsive during long stage-1 campaigns.

- Known risks:
  - Discovery now assumes run dirs are immediate children of any `patch_runs` folder.
  - If future layout deviates from that contract, rows may be missed.

- Monitoring signals:
  - `/api/status` latency
  - mismatch between expected running manifests and dashboard row count

## Follow-up

1. If run layout changes in future, update `discover_run_dirs` contract + tests.
2. Consider adding lightweight timing telemetry to `/api/status` for regression detection.
3. Continue monitoring stalled rows; failed manifests should be re-queued explicitly.
