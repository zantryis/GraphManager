# 2026-02-20 - Evaluation Vulnerabilities and Timeout Accounting Notes

## Context

- During N=100 unattended patching runs, multiple concerns surfaced about how to interpret timeout-heavy results under local quota/hardware constraints.
- The immediate need was to document vulnerabilities and guardrails without changing the in-flight protocol.
- Affected artifacts:
  - `CURRENT_STATE.md`
  - `results/patch_runs/*/patch_summary.json`
  - `run_patch.py` cost/timeout accounting paths

## Decision

- Keep current run protocol unchanged while N=100 is in progress.
- Record evaluation vulnerabilities explicitly in `CURRENT_STATE.md` Parking Lot.
- Preserve current primary accounting as operational all-in (timeouts included), and plan sensitivity views (timeout-excluded and infra-recovered) for final analysis.
- Scope boundary: no code-path or manifest-policy changes in this note.

## Alternatives Considered

1. Exclude timeouts from primary metrics now.
- Tradeoff: cleaner rates but optimistic and less operationally faithful; can hide robustness issues.

2. Keep all-in metrics only, no sensitivity analysis.
- Tradeoff: conservative but may over-conflate method quality with infra constraints.

3. Keep all-in primary and add sensitivity tables later.
- Tradeoff: more reporting work, but strongest rigor and transparency.

## Evidence

- Cost accounting implementation includes timeout rows in totals:
  - `run_patch.py` (`_compute_cost_summary_fields`, per-instance `total_tokens` aggregation)
- Timeout rows can carry non-zero spend in current data:
  - observed timeout instances with non-zero tokens in completed N=100 manifests
- In-flight run state and method completion snapshots:
  - `results/patch_runs/*/patch_summary.json`
  - `/tmp/n100_debug.log`

## Consequences

- Expected benefits:
  - Avoids rash metric decisions mid-experiment.
  - Creates explicit audit trail for reviewer-facing validity language.
- Known risks:
  - If sensitivities are not produced later, interpretation may remain ambiguous.
  - Infra-failure handling still requires explicit recovery bookkeeping.
- Monitoring signals:
  - timeout rate by method
  - infra error counts (OOM/credential/harness)
  - all-in vs timeout-excluded deltas in resolved rate and cost-per-resolved

## Follow-up

1. After N=100 completion, generate two companion tables:
   - all-in (primary)
   - timeout-excluded + infra-recovered (sensitivity)
2. Add explicit threats-to-validity language on resource-constrained deployment vs production deployment.
3. Keep run protocol fixed until current queue completes.
