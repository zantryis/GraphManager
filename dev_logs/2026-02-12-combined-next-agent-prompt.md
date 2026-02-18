# 2026-02-12 - Combined Next-Agent Prompt For Retrieval + Regeneration

## Context

- A new execution request required combining two dependent tasks:
  1. deterministic retrieval implementation,
  2. clean-slate evaluation regeneration and artifact refresh.
- Existing prompts were split (`NEXT_AGENT_PROMPT_RETRIEVAL.md` and evaluation/regeneration instructions), which risked sequencing drift.

## Decision

- Add a single operational handoff prompt:
  - `NEXT_AGENT_PROMPT_COMBINED.md`
- The prompt enforces:
  - Stage 1 retrieval implementation first,
  - Stage 2 phased matrix reruns from a clean results root,
  - Stage 3 viewer/artifact/handoff refresh.
- Included exact experiment index phases and CLI-compatible commands.

Scope boundary:
- no behavior changes in code this step,
- no experiment execution this step.

## Alternatives Considered

1. Keep separate prompt files and rely on manual ordering.
- Tradeoff: less editing, but high chance of inconsistent execution.
2. Replace existing prompt files with one file.
- Tradeoff: simpler surface, but loses focused prompt variants.
3. Add a combined prompt while keeping focused prompts (chosen).
- Tradeoff: one extra file, but clear sequencing and lower ambiguity.

## Evidence

- Added:
  - `NEXT_AGENT_PROMPT_COMBINED.md`

## Consequences

- Expected benefits:
  - clearer execution order,
  - lower risk of running matrix before retrieval implementation,
  - better reproducibility and phase-level reporting discipline.
- Known risks:
  - prompt set now has multiple entry points; agents must pick the right one for scope.
- Monitoring signals:
  - next session should cite `NEXT_AGENT_PROMPT_COMBINED.md` when both implementation and regeneration are requested.

## Follow-up

1. If scope is implementation-only, continue using `NEXT_AGENT_PROMPT_RETRIEVAL.md`.
2. If scope is end-to-end implementation + regeneration, use `NEXT_AGENT_PROMPT_COMBINED.md`.
