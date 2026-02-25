# 2026-02-24 - V2 8-Method Accounting, Matrix Fix, and Queue Kickoff

## Context

- The in-flight V2 full run had been launched from a 4-method manifest set (48 manifests / 2000 issue-method instances), while the agreed direction expanded to deterministic GM/RAG methods.
- User requested a full accounting first, then immediate plan+execution with oracle preserved.
- A corrected campaign needed to preserve existing data, resume incomplete runs, and add the missing methods without discarding prior completed artifacts.

## Decision

- Keep existing completed 4-method artifacts; do not discard/restart from scratch.
- Expand V2 manifest generation to an explicit 8-method matrix (including `oracle`).
- Add missing `run_patch` retrieval dispatch support for deterministic RAG methods (`raw_rag_function`, `raw_rag_fixed`) so new manifests are executable.
- Relaunch pool on the corrected 96-manifest campaign with resume enabled and no manifest timeout.

Scope boundary:
- This change does **not** implement `repomap_like` / `agentless_like_localization` yet.
- This change runs stage1-only local execution (Modal unavailable) and does not perform stage2 harness evaluation.

## Alternatives Considered

1. Keep the old 4-method campaign and finish it.
- Tradeoff: faster short-term completion, but misaligned matrix and unusable for intended comparisons.

2. Delete existing outputs and restart everything from zero.
- Tradeoff: clean campaign bookkeeping, but wastes completed data/time/cost and delays execution.

3. Preserve completed artifacts, add missing methods, and resume on a superset manifest list. (chosen)
- Tradeoff: mixed campaign history must be tracked explicitly, but preserves data and minimizes rework.

## Evidence

- Accounting report: `docs/V2_RUN_ACCOUNTING_AND_EXECUTION_2026-02-24.md`
- Corrected manifest list: `logs/v2_full_manifests_8method_20260224_100240.txt`
- Corrected ledger: `patch_manifests/v2_verified/manifest_ledger_v2.json`
- Pool log (corrected campaign): `logs/v2_repo_pool_20260224_100338.log`
- Test run: `./.venv/bin/python -m unittest discover -s tests -v` → 228 passed

## Consequences

- Benefits:
  - Campaign denominator now matches intended 8-method setup (96 manifests / 4000 issue-method instances).
  - Existing completed runs are retained and reused via manifest-level completion checks.
  - New deterministic RAG method manifests are runnable in patch pipeline.
- Risks:
  - High concurrency can still trigger provider rate limits/quota pressure.
  - Stage1-only mode delays resolved-rate updates until stage2 evaluation is available.
- Monitoring signals:
  - `logs/v2_repo_pool_20260224_100338.log` for failures/timeouts/retries.
  - Dashboard `/api/status` summary_plan vs summary_started drift.

## Follow-up

1. Let corrected 8-method stage1 queue run; monitor failures and resume behavior.
2. If 429 pressure rises, reduce `--run-workers` first, then `--max-parallel-repos`.
3. When Modal access returns, run staged evaluation passes (`--evaluate-only --modal`) for completed predictions.
