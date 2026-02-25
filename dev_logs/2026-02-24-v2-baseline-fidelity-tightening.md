# 2026-02-24 - V2 Baseline Design Fidelity Tightening

## Context

- User reviewed `docs/V2_BASELINE_REBUILD_DESIGN_2026-02-24.md` and identified fidelity risks:
  - ambiguous RepoMap-like graph semantics
  - unclear symbol-level vs file-level projection
  - underspecified Agentless-like Stage 3 I/O
  - unconstrained LLM file-branch behavior

## Decision

- Tighten the design spec without changing runtime code yet.
- Keep L1 component-equated direction, but make the baseline contracts auditable and reproducible.

## Alternatives Considered

1. Leave the original high-level design as-is.
   Tradeoff: faster, but weak defensibility for baseline fidelity claims.
2. Pivot to L2 full reproduction now.
   Tradeoff: higher nominal fidelity, but major scope expansion and schedule risk.
3. Tighten L1 contracts with explicit schemas/guardrails.
   Tradeoff: moderate spec effort, strong rigor gain.

Chosen: Option 3.

## Evidence

- Updated file:
  - `docs/V2_BASELINE_REBUILD_DESIGN_2026-02-24.md`
- Added constraints:
  - explicit RepoMap-like edge types and deterministic weights
  - symbol-map-to-file projection statement
  - Agentless-like Stage 3 typed span output contract
  - constrained candidate-list LLM selection and invalid-selection metrics

## Consequences

- Expected benefits:
  - Reduces "mystical ranking" risk in RepoMap-like baseline.
  - Prevents LLM path hallucination from contaminating Agentless-like file branch.
  - Makes Stage 3 sampling interpretable via fixed I/O schema and caps.
- Known risks:
  - Additional implementation complexity for validation metrics.
- Monitoring signals:
  - invalid path selection rate
  - out-of-candidate rejection count
  - Stage 3 span schema violation rate
  - RepoMap edge-type counts + normalized weight distribution

## Follow-up

1. Implement `repomap_like` with the exact edge schema and weight config from the spec.
2. Implement Agentless-like Stage 1 with constrained candidate generation first.
3. Add schema/guardrail tests before running retrieval smoke experiments.
