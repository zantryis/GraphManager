# 2026-02-12 - Deterministic Retrieval Redesign Spec

## Context

- Current retrieval in `src/manager_agent.py` and `src/rag_baseline.py` uses looped tool-calling, which may increase token/latency cost and introduce recall loss under strict gating.
- User requested a concrete redesign doc with explicit mechanism and coefficient tuning plan.
- Prior work review was refreshed by cloning `previous_work/vitali-code-graph-rag`.

## Decision

- Draft a repository-level design spec for deterministic graph-first retrieval:
  - `docs/RETRIEVAL_REDESIGN_V1.md`
- The spec defines:
  - one-shot seed retrieval + bounded graph expansion,
  - explicit file-scoring formula with coefficients,
  - tuning protocol, ablations, integration plan, and acceptance criteria.
- Add discoverability link in:
  - `docs/README.md`

Scope boundary:
- no retrieval implementation changes in this step,
- no experiment reruns in this step.

## Alternatives Considered

1. Keep current looped retrievers and tune prompts only.
- Tradeoff: lower immediate code change, but weak control over cost and ranking determinism.
2. Remove LLM entirely from retrieval and use pure lexical graph heuristics.
- Tradeoff: deterministic and cheap, but likely weaker recall on semantic issues.
3. Deterministic graph-first with semantic seeding (chosen).
- Tradeoff: moderate engineering work with better controllability and explainability.

## Evidence

- New spec:
  - `docs/RETRIEVAL_REDESIGN_V1.md`
- Docs index update:
  - `docs/README.md`
- Prior work reference reviewed:
  - `previous_work/vitali-code-graph-rag`

## Consequences

- Expected benefits:
  - clearer retrieval behavior,
  - lower runtime-token pressure,
  - easier coefficient tuning and reproducibility.
- Known risks:
  - coefficient overfitting on small dev slices,
  - potential recall loss if traversal budgets are too strict.
- Monitoring signals:
  - paired F1 delta vs `gm_progressive`,
  - runtime token delta,
  - bootstrap CI stability across tracks.

## Follow-up

1. Implement `DeterministicGraphRetriever` behind a new method flag.
2. Add failing tests for ranking/penalty/budget invariants, then implement minimally.
3. Run manifest-based coefficient tuning with frozen dev splits and CI-backed comparison.
