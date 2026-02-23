# 2026-02-19 - N=100 Oracle Resume After OOM

## Context

- N=100 oracle-first queue was interrupted mid-run while processing scikit-learn manifests.
- Two scikit-learn attempts were incomplete and did not emit `patch_summary.json`:
  - `results/patch_runs/20260219_063236`
  - `results/patch_runs/20260219_081208`
- Workstream affected: B (patching pipeline execution only).

## Decision

- Resume oracle queue from interrupted manifest sequence using a resilient chain runner that logs per-manifest start/end and return code.
- Preserve frozen manifests and study protocol; no manifest edits, no code changes.
- Start from `scikit_learn_scikit_learn_oracle_v1.yaml`, then continue `sphinx_doc_sphinx_oracle_v1.yaml`, `sympy_sympy_oracle_v1.yaml`.

## Alternatives Considered

1. Skip scikit-learn and continue to sphinx/sympy
Main tradeoff: faster progress, but leaves an unclosed oracle cell in the fixed split.

2. Restart full oracle queue from beginning
Main tradeoff: clean replay, but significant wasted compute and duplicated finished manifests.

3. Resume from interrupted point (chosen)
Main tradeoff: minimal recomputation, keeps timeline moving; requires careful run ledger updates for failed/incomplete attempts.

## Evidence

- OOM/build failure signature in follow-up log:
  - `logs/n100_oracle_followup_20260218_225303.log`
  - observed `BuildImageError ... non-zero code: 137`
- Incomplete scikit runs:
  - `results/patch_runs/20260219_063236` (`predictions.json` present, no `patch_summary.json`)
  - `results/patch_runs/20260219_081208` (patches only, no predictions/summary)
- Active recovery chain run:
  - live session id: `91403`
  - log: `logs/n100_oracle_resume_chain_20260219_124650.log`
  - current run id: `20260219_124650`

## Consequences

- Oracle queue can continue without re-running completed oracle manifests.
- Study ledger now explicitly tracks incomplete attempts and root-cause class (OOM during harness/docker build).
- Residual risk: additional OOM during harness can still interrupt runs; needs continued monitoring.

## Follow-up

1. Monitor session `91403` and record `patch_summary.json` for scikit/sphinx/sympy when complete.
2. After oracle queue closes, continue N=100 execution for `gm_progressive`, `rag_progressive`, `none`.
3. Keep appending run IDs + per-manifest completion status in `CURRENT_STATE.md`.
