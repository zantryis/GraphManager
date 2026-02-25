# 2026-02-24 - V2 Pilot Runs on Modal (Concurrent Launch)

## Context

- V2 Phase 3 Step 4 required running the pilot manifest set:
  `pilot_oracle_v1`, `pilot_bm25_v1`, `pilot_gm_progressive_v1`.
- User request: run pilot fast, concurrent, and with Modal harness evaluation.
- Initial attempts hit two operational hazards:
  - sandbox-network restrictions (required escalated execution)
  - shared local repo checkout contention when multiple runs used the same cwd/repo clone path

## Decision

- Ran all 3 manifests concurrently with `--evaluate --modal` using isolated working directories:
  - `/tmp/gm_pilot_oracle`
  - `/tmp/gm_pilot_bm25`
  - `/tmp/gm_pilot_gmprogressive`
- Kept separate results roots per method under `results/v2_pilot_parallel/`.
- No code changes to experiment logic in this execution pass.

## Alternatives Considered

1. Sequential runs in one workspace
   - Lower risk, but violates the fast/concurrent execution objective.
2. Concurrent runs in one workspace
   - Fastest setup, but invalid due to git checkout race on shared `requests_repo`.
3. Isolated concurrent workdirs (chosen)
   - Preserves concurrency while preventing checkout races.

## Evidence

- Run logs:
  - `logs/pilot_oracle_v1_session_20260223_210845.log`
  - `logs/pilot_bm25_v1_session_20260223_210845.log`
  - `logs/pilot_gm_progressive_v1_session_20260223_210845.log`
- Run summaries:
  - `results/v2_pilot_parallel/pilot_oracle_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json`
  - `results/v2_pilot_parallel/pilot_bm25_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json`
  - `results/v2_pilot_parallel/pilot_gm_progressive_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json`
- Harness invocation confirmed by logs (`=== Running SWE-bench harness evaluation ===`) for all methods.

## Consequences

- Expected benefits:
  - V2 pilot Step 4 completed with Modal-evaluated outputs for all 3 methods.
  - Concurrent execution completed without local git checkout corruption.
- Known risks:
  - All 3 runs share second-level `run_id=20260223_210845`; this increases risk of cross-run harness artifact collisions in shared global harness paths.
- Monitoring signals:
  - Confirm per-run `patch_summary.json` and `harness_results` are present.
  - Verify harness report paths in each summary point to method-local run artifacts.

## Follow-up

1. Add unique harness run key suffix (e.g., retrieval method) for concurrent full runs.
2. Execute Step 5 adversarial/path-safety + contract audits before full sweep.
3. If full concurrent run proceeds, stagger launch by >=1s or provide explicit run-id override.
