# 2026-02-24 - V2 Data Completeness Mop-up Supervisor

## Context

- Active V2 8-method full run had partial completion with stalled/failed manifests due transient API exhaustion.
- Requirement: do not miss data, and do not rerun already valid/completed runs.

## Decision

- Keep current primary pool running unchanged.
- Add a detached mop-up supervisor that starts only after primary pool exit and then runs additional passes for incomplete manifests.
- Rely on manifest-path completion checks in `tools/run_manifest_pool.py` to skip already completed runs.

## Alternatives Considered

1. Restart entire campaign immediately
- Tradeoff: simpler, but risks duplicate execution and wasted spend.

2. Manual one-by-one reruns from failure logs
- Tradeoff: precise but operationally brittle and easy to miss manifests.

3. Detached pass-loop supervisor (chosen)
- Tradeoff: minimal code churn and low operator burden; retries incomplete work while preserving completed data.

## Evidence

- Completion skip check validated with one completed manifest:
  - `/tmp/test_skip_completed.log` contained `SKIP completed ...`
- Active campaign status snapshot:
  - `http://127.0.0.1:5051/api/status?active_only=0&include_complete=1&include_stale=1`
  - `96` planned manifests, `58` complete, `6` running, `20` stalled (snapshot time)
- Supervisor launched detached via `setsid`:
  - script: `/tmp/v2_full_mopup_loop.sh`
  - pid: `10035`
  - log: `logs/v2_full_mopup_supervisor_20260224_142123.log`

## Consequences

- Expected benefits:
  - failed/stalled manifests are retried until completion,
  - completed manifests are skipped and not rerun.
- Known risks:
  - repeated 429 rate-limit failures may require more passes.
- Monitoring signals:
  - supervisor log pass count/pending count,
  - dashboard `summary_started.status_counts.stalled` trend toward zero,
  - increase in `patch_summary.json` count toward planned manifest count.

## Follow-up

1. Confirm supervisor transitions from "waiting for primary pool" to "launching mop-up pass" after pool exit.
2. If pending remains after max passes, reduce parallelism for retry passes (e.g., 8 -> 4) and rerun remaining manifests.
3. After completion, generate final coverage report (planned vs completed manifests and per-method completed instances).
