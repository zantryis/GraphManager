# 2026-02-24 - V2 Baseline Rebuild Design Decision

## Context

- User requested lifting the "published numbers only" lock and evaluating whether Agentless/RepoMap-like baselines should be rebuilt in-repo.
- Existing project docs and state currently frame Agentless/RepoMap primarily as external references.
- Goal: produce a concrete design with explicit proceed/no-proceed recommendation.

## Decision

- Add a design spec for two new L1 component-equated baselines:
  - `repomap_like`
  - `agentless_like_localization`
- Keep downstream patch stage fixed (current `PatchAgent`) for comparability.
- Explicitly defer L2 full end-to-end reproductions of external systems.

Scope boundaries:
- No code implementation in this step.
- No manifest regeneration in this step.
- No run execution in this step.

## Alternatives Considered

1. Keep published-number-only lock as-is.
   Tradeoff: lowest engineering cost, but leaves a major comparison gap.
2. Attempt full faithful reproductions immediately.
   Tradeoff: maximal parity aspiration, but very high schedule and confound risk.
3. Implement component-equated "X-like" baselines first.
   Tradeoff: not full-system parity, but strong scientific value per unit effort.

Chosen: Option 3.

## Evidence

- New design artifact:
  - `docs/V2_BASELINE_REBUILD_DESIGN_2026-02-24.md`
- Referenced repo context:
  - `docs/V2_RUN_DESIGN_2026-02-24.md`
  - `dev_logs/2026-02-23-v2-phase1-research.md`
  - `CURRENT_STATE.md`

## Consequences

- Expected benefits:
  - Provides actionable blueprint for adding meaningful baselines without derailing V2.
  - Separates what can be claimed (component-equated) vs what cannot (full-system reproduction).
- Known risks:
  - Labeling/claim discipline is required to avoid overstatement.
  - Agentless-like Stage 2/3 may still add notable complexity.
- Monitoring signals:
  - Retrieval-only smoke stability for new methods.
  - Added method schema completeness in summary artifacts.
  - Pilot patch behavior under fixed patch protocol.

## Follow-up

1. Implement `repomap_like` retrieval method + tests.
2. Implement `agentless_like_localization` Stage 1 + tests, then stage up to Stage 2/3.
3. Run retrieval-only matrix cells first before adding these methods to patch pilots.
