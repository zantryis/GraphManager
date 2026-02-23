# 2026-02-19 - gm_deterministic same-snapshot reruns + N=100 oracle launch

## Context

- Strict gm_deterministic reruns had completed for Flask/Requests/Pytest.
- Master plan required continuing execution without pause: close remaining paper-minimum retrieval cells, then start N=100 oracle-first patching.

## Decision

- Complete the three same-snapshot gm_deterministic reruns immediately using frozen selected config.
- Start Workstream B oracle-first N=100 execution right after retrieval completion.
- During oracle batch launch, switched from buffered shell-pipeline mode to direct per-manifest mode after detecting a stalled/buffered execution pattern.

## Alternatives Considered

1. Pause after strict reruns and wait for manual confirmation.
Main tradeoff: safer coordination, but violates requested uninterrupted execution.
2. Use `run_suite.py` for retrieval completion.
Main tradeoff: easy matrix execution, but cannot restrict to gm_deterministic-only method.
3. Keep buffered oracle batch command despite poor observability.
Main tradeoff: fewer commands, but hard to diagnose progress/stalls in real time.

## Evidence

- Same-snapshot retrieval commands executed (all with `--methods gm_deterministic` + selected config):
  - Flask same-snapshot run: `results/runs/20260218_221905/summary.json` → F1 `0.645`
  - Requests same-snapshot run: `results/runs/20260218_221920/summary.json` → F1 `0.603333...`
  - Pytest same-snapshot run: `results/runs/20260218_221935/summary.json` → F1 `0.473333...`
- Oracle launch:
  - Initial batch wrapper attempt failed fast due CLI arg mismatch (`--manifest` required).
  - Buffered batch attempt started but was hard to inspect and was terminated/relaunched.
  - Direct run launched: `./.venv/bin/python -u run_patch.py --manifest patch_manifests/n100_verified/astropy_astropy_oracle_v1.yaml --evaluate`
  - Active run ID: `results/patch_runs/20260218_223151`
  - Observed instance progress during run:
    - `astropy__astropy-12907`: `apply_failed`
    - `astropy__astropy-13398`: `timeout_budget_exceeded`
    - `astropy__astropy-13453`: `patched`
    - `astropy__astropy-13579`: `patched`
    - later instances in progress

## Consequences

- Workstream A paper-minimum gm_deterministic strict+same cells are now complete for Flask/Requests/Pytest.
- Workstream B oracle-first N=100 execution has started and is actively processing astropy manifest.
- Long-running patch calls show sparse stdout intervals due per-instance execution; direct mode improves observability.

## Follow-up

1. Continue oracle manifests sequentially across `patch_manifests/n100_verified/*_oracle_v1.yaml`.
2. Record each oracle run ID and summary metrics once manifest completes.
3. After oracle-first pass per repo, proceed to gm/rag/none manifests on identical frozen IDs.

## Addendum (uninterrupted execution wiring)

- To preserve uninterrupted oracle progression, a follow-up orchestrator was launched:
  - Session waits for active astropy oracle PID (`19296`) to finish, then runs remaining oracle manifests sequentially.
  - Follow-up log: `logs/n100_oracle_followup_20260218_225303.log`
