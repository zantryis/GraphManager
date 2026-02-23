# 2026-02-21 - Handoff v4 Prep and Protocol Lock

## Context

- The project reached a planning pivot after identifying a dual-build confound in
  patching runs: `run_patch.py` currently builds both graph and RAG indices for
  GM/RAG methods in frozen N=100 artifacts.
- Research writing risk increased because claim wording was not yet locked against
  current evidence limits.
- A repo-level handoff needed phase gates and unambiguous next actions.

## Decision

- Adopt a phase-gated handoff protocol (v4) as the execution path for Workstream B/C.
- Update `CURRENT_STATE.md` with:
  - preflight checks,
  - phase checklist,
  - frozen N=100 run ledger,
  - updated Workstream B next actions,
  - new known bug B10 for dual-build confound.
- Create `CLAIMS_LOCK.md` as the Phase-4 claim-strength contract without modifying
  `RESEARCH_INTENT.md`.
- Create a dedicated handoff checklist doc for the next agent.

## Alternatives Considered

1. Keep protocol only in chat history
Main tradeoff: fast, but brittle and non-auditable for multi-agent handoff.

2. Modify `RESEARCH_INTENT.md` directly
Main tradeoff: centralizes claims language, but violates contract policy without
researcher sign-off.

3. Add protocol + claims lock as new artifacts (chosen)
Main tradeoff: one more doc to maintain, but preserves scope contract and makes
handoff execution deterministic.

## Evidence

- Scope contract: `RESEARCH_INTENT.md`
- Execution state source of truth: `CURRENT_STATE.md`
- Frozen patch run artifacts under `results/patch_runs/`:
  - oracle (9 runs), gm_progressive (9 runs), rag_progressive (9 runs),
  - none pending completion post-`20260220_234209`.
- Prior vulnerability and timeout notes:
  - `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md`
  - `dev_logs/2026-02-20-eval-vulnerabilities-timeout-accounting.md`

## Consequences

- Next agent can execute Phase 1-5 without re-deriving decision context.
- Claim language is constrained before drafting resumes.
- Rerun policy is now explicitly analysis-gated, reducing unnecessary API spend.

## Follow-up

1. Phase 1: implement split-build fix with strict TDD and backward-compatible schema extension.
2. Phase 2: complete none baseline across 9 repos and verify completion markers.
3. Phase 3: run the single analysis script and decide rerun gate from measurable outputs.
