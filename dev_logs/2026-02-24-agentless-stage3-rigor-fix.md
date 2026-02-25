# 2026-02-24 - Agentless Stage-3 Rigor Fix

## Context

- V2 baseline rebuild introduced `agentless_like_localization`, but Stage-3 had two scientific rigor risks:
  - non-stable sampling seed (`hash(...)`) across Python processes,
  - configured `stage3_max_tokens_per_file` was not effectively useful for low-cap ablations.
- A dashboard status check was also requested to verify current V2 full-run health.

## Decision

- Harden Stage-3 localization for reproducibility and clean ablation semantics:
  - switch Stage-3 deterministic seed to SHA256-derived integer seed,
  - enforce Stage-3 per-file context token cap and emit per-file cap usage metadata,
  - lower minimum allowed Stage-3 cap from `128` to `1` so low-cap ablations are valid.
- Scope boundary:
  - no change to run pool scheduling logic in this patch,
  - no restart/requeue action performed automatically on active V2 pool jobs.

## Alternatives Considered

1. Keep Python `hash(...)` seeding
- Tradeoff: simpler code, but unstable across processes and weaker reproducibility.

2. Keep minimum Stage-3 cap at 128
- Tradeoff: fewer edge-case prompts, but invalidates low-cap ablations.

3. Add only tests without code changes
- Tradeoff: detects issues but leaves method behavior non-rigorous.

## Evidence

- Code changes:
  - `src/agentless_like_localization.py`
  - `tests/test_agentless_like_localization.py`
- Test outputs:
  - `./.venv/bin/python -m unittest tests.test_agentless_like_localization tests.test_repomap_like -v` (pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (`242` tests, pass)
- Runtime status snapshot:
  - `http://127.0.0.1:5051/api/status` and `.../api/status?active_only=0&include_complete=1&include_stale=1`

## Consequences

- Expected benefits:
  - reproducible Stage-3 sampling behavior across machines/processes,
  - ablations on Stage-3 context budget are now meaningful,
  - metadata supports auditability of Stage-3 context pressure.
- Known risks:
  - lower Stage-3 caps can reduce context quality for difficult instances.
- Monitoring signals:
  - `agentless_like_meta.stage3_context_tokens_per_file`,
  - localization quality deltas under cap sweeps.

## Follow-up

1. Add `repomap_like` and `agentless_like_localization` manifests into the active full-run plan before claiming 8+ method coverage.
2. Add a lightweight run-health command/script that prints `running/stalled/complete` and per-method denominator for checkpointing.
3. Run bounded ablation pilots (e.g., requests/flask/pytest) before queueing full 500-instance sweeps for new methods.
