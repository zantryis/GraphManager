# 2026-02-24 - Dashboard stale-filter and manifest-attempt polish

## Context

- V2 monitoring dashboard still showed confusing stale/stopped rows in some retry scenarios.
- User requested clearer row semantics (what each row represents) and cleaner active run tracking.
- A dedupe edge case in `src/patch_dashboard.py` could prefer an older `complete` attempt over a newer retry attempt for the same manifest.

## Decision

- Keep the dashboard contract as "one row per manifest attempt" with active-only defaults.
- Change manifest dedupe selection to prefer freshest `last_seen_ts` attempt regardless of status.
- Retain active-only filtering (`running` + recent `not_started`) and explicit stale/complete opt-in toggles.

Scope boundaries:
- No change to patch execution pipeline or manifest generation behavior.
- No change to harness/evaluation semantics.

## Alternatives Considered

1. Keep "complete wins" dedupe
Tradeoff: hides newer retries; confusing for live monitoring.

2. Disable dedupe entirely
Tradeoff: duplicates and noise increase; harder to read dashboard during retries.

3. Dedupe by freshest `last_seen_ts` (chosen)
Tradeoff: old completed rows can be hidden when new retry starts, but this matches live monitoring intent.

## Evidence

- Code update: `src/patch_dashboard.py` dedupe now uses `last_seen_ts` ordering.
- Test additions: `tests/test_patch_dashboard.py`
  - `test_collect_dashboard_status_prefers_new_attempt_over_old_complete`
  - `test_collect_dashboard_status_active_only_hides_stale_and_old_pending`
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` (8 tests, pass)
  - `./.venv/bin/python -m unittest discover -s tests -v` (208 tests, pass)
- Live API check:
  - `GET /api/status` returns active rows with manifest metadata and filtered statuses.

## Consequences

- Active dashboard view is more faithful to currently running work and less polluted by stale attempts.
- Manifest-level progress interpretation is clearer in UI (manifest/repo/run split columns).
- Remaining risk: pending rows (`not_started`) can still be numerous in very large pooled launches; mitigated by pending grace filtering.

## Follow-up

1. Add a lightweight "hide pending" toggle if queued manifests become visually noisy.
2. Consider adding per-manifest elapsed runtime and ETA fields in API for better operational triage.
3. Keep dashboard active-only defaults for V2 pool monitoring.
