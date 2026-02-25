# 2026-02-24 - Dashboard Progress Accuracy and Duplicate Attempt Dedup

## Context

- Dashboard showed `1/?` for active runs and displayed duplicate `agentic_cold_start` rows after a restart attempt.
- Root causes:
  - no planned instance-count metadata before `patch_summary.json` exists;
  - multiple in-flight run dirs for the same manifest were surfaced independently.

## Decision

- Add run-start metadata emission in patch runner (`run_meta.json`).
- Use run metadata in dashboard to populate `n_instances` and method before summary exists.
- Deduplicate in-flight rows by manifest path, keeping the freshest record.

## Alternatives Considered

1. Keep current behavior and rely only on `patch_summary.json`.
Tradeoff: simple but misleading during long runs.

2. Parse runner logs for run-level metadata.
Tradeoff: brittle and expensive parsing path.

3. Emit explicit metadata file at run start (chosen).
Tradeoff: small write path addition, robust and cheap.

## Evidence

- Code changes:
  - `run_patch.py`: write `run_meta.json` at run start.
  - `src/patch_dashboard.py`: consume `run_meta.json`; dedupe by manifest.
  - `tests/test_patch_dashboard.py`: added metadata + dedupe coverage.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_patch_dashboard -v` passed.
  - `./.venv/bin/python -m unittest discover -s tests -v` passed (`205` tests).
- Live verification:
  - Dashboard API now reports single active astropy run with denominator:
    `n_instances=22`, `n_completed=2`, `progress_pct=9.1`.

## Consequences

- Expected benefits:
  - Accurate in-flight progress (`x/y`) before summary write.
  - No duplicate rows for restarted attempts on the same manifest.
- Known risks:
  - Very old runs without `run_meta.json` may still appear with limited metadata unless backfilled.
- Monitoring signals:
  - `/api/status` should show one row per active manifest and non-null `n_instances` for new runs.

## Follow-up

1. Let current watchdog run continue; monitor via dashboard and runner log.
2. Keep failure replay loop for entries in `logs/v2_full_failures_20260223_223555.log`.
3. After sweep, aggregate summaries for method-level report.
