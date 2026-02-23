# 2026-02-19 - Phase 0 validation + tuning artifact contract

## Context

- The master plan for Paper 1 requires Phase 0 gates to be explicitly verified, plus reproducible gm_deterministic tuning artifacts and deterministic N=100 patch manifests.
- Existing code already added most controls, but two gaps remained:
  - no locked tuning artifact contract containing full leaderboard + stability checks
  - no explicit tests asserting N=100 manifest determinism/policy pinning across methods.

## Decision

- Added a deterministic tuning artifact builder that records:
  - selection rule
  - baseline holdout scores and max-drop guard
  - selected config
  - full leaderboard with per-candidate guard pass/fail and holdout deltas.
- Extended tuning CLI (`tools/tune_gm_deterministic.py select`) to emit this artifact as report output.
- Added regression tests for frozen N=100 split and method-manifest identity/policy pinning.
- Executed an evaluated smoke run for `none` to verify complete patch summary schema and real patch-model token accounting.

Scope boundaries:
- Did not run full N=100 multi-method patch study.
- Did not run full Gemini-3 retrieval rerun matrix.

## Alternatives Considered

1. Keep current lightweight `selection_v1.json` output only.
- Rejected: insufficient for auditability/reproducibility in paper artifact review.

2. Build a larger orchestration framework for full tuning search.
- Deferred: adds complexity before immediate reproducibility gap is closed.

3. Add only docs, no tests for N=100 manifest determinism.
- Rejected: protocol drift risk remains undetected.

## Evidence

- Code changes:
  - `src/deterministic_tuning.py`
  - `tools/tune_gm_deterministic.py`
  - `tests/test_deterministic_tuning.py`
  - `tests/test_n100_manifests.py`
- Smoke artifact:
  - `results/patch_runs/20260218_195140/patch_summary.json`
  - `graphmanager-none.graphmanager_20260218_195140.json`
- Tuning candidate artifact:
  - `results/gm_deterministic_tuning/candidates_v1.json` (seed=17, n=60)
- Test output:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 132 tests passed.

## Consequences

- Tuning selection is now machine-checkable and paper-auditable from one artifact.
- N=100 manifest freeze now has automated guardrails against accidental drift.
- Phase 0 smoke gate now includes evidence that `none` is a real patch call path (`patch_runtime_tokens=397`) with complete summary schema.

Known risks:
- Full-study runtime/cost behavior still requires main experiment execution.
- Gemini API reliability can still induce timeout statuses at scale despite bounded retries.

Monitoring signals:
- Non-null `total_cost_tokens` fields in all patch summaries
- `timeout_budget_exceeded` incidence during scale runs
- Manifest hash consistency against `patch_manifests/n100_verified/manifest_ledger_v1.json`

## Follow-up

1. Run gm_deterministic tuning eval loop (Flask tune; Requests/Pytest holdout guard) and freeze selected config artifact.
2. Run Gemini-3 retrieval reruns for canonical matrix + patch-aligned subset.
3. Execute N=100 patching study in oracle-first order using frozen manifests.
