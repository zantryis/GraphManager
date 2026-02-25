# 2026-02-24 - V2 Method Matrix Mismatch: Queue Stop and Reconciliation

## Context

- User expected a broader V2 method matrix (including deterministic GM/RAG and planned Agentless/RepoMap-like baselines).
- Active full-run queue was based on `logs/v2_full_manifests_20260223_222457.txt`.
- That manifest list was generated from a 4-method generator and did not include expanded methods.

## Decision

- Stop the active full-run pool immediately to avoid additional spend on a known-mismatched matrix.
- Preserve all partial outputs in-place for possible reuse/comparison as a 4-method subset run.
- Reconcile and explicitly freeze the intended V2 method matrix before restarting any full-run queue.

Scope boundaries:
- No deletion of existing run artifacts.
- No forced rerun of completed manifests in this step.

## Alternatives Considered

1. Let current queue finish
- Produces more data quickly, but on the wrong matrix relative to current study intent.

2. Stop immediately (chosen)
- Prevents further drift and cost; requires up-front matrix reconciliation.

3. Run parallel second queue for new methods while old queue continues
- Highest cost/risk and increases analysis confusion.

## Evidence

- Active queue list (`logs/v2_full_manifests_20260223_222457.txt`) includes only:
  - `oracle`, `gm_progressive`, `bm25`, `agentic_cold_start`
- Generator hardcoded 4-method full set in:
  - `tools/generate_v2_verified_manifests.py` (`FULL_METHODS`)
- Runtime support mismatch observed:
  - `run_patch.py` dispatch currently does not implement `repomap_like` / `agentless_like_localization`.

## Consequences

- Expected benefits:
  - Avoids compounding wrong-matrix data.
  - Clears path to run the correct, agreed matrix once frozen.

- Known risks:
  - Delays completion of any full sweep until matrix + implementation are aligned.

- Monitoring signals:
  - No active `run_manifest_pool.py`/`run_patch.py` processes after stop.
  - Dashboard should show no new progress until queue restart.

## Follow-up

1. Freeze exact V2 full-run method roster (explicit names, count, and oracle inclusion policy).
2. Implement missing retrieval methods/dispatch required by that roster.
3. Regenerate manifests + manifest list for the frozen roster, then restart queue.
