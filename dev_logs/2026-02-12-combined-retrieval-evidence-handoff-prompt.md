# 2026-02-12 - Combined Retrieval + Evidence Handoff Prompt

## Context

- A retrieval-implementation prompt already existed (`NEXT_AGENT_PROMPT_RETRIEVAL.md`).
- User provided an additional clean-slate evidence-regeneration execution plan that should run after retrieval implementation.
- Without consolidation, handoff risk increases (prompt drift, missing phase order, inconsistent deliverables).

## Decision

- Create a combined handoff prompt:
  - `NEXT_AGENT_PROMPT_RETRIEVAL_AND_EVIDENCE.md`
- Keep original focused prompt intact:
  - `NEXT_AGENT_PROMPT_RETRIEVAL.md`
- Update docs index to include both prompt entry points:
  - `docs/README.md`

Scope boundary:
- no retrieval/evaluation code changes,
- no experiment execution in this step.

## Alternatives Considered

1. Replace `NEXT_AGENT_PROMPT_RETRIEVAL.md` entirely.
- Tradeoff: single file, but loses focused implementation-only path.
2. Keep prompts separate and rely on manual stitching.
- Tradeoff: lower edit effort, higher execution ambiguity.
3. Add a combined prompt while retaining focused prompt (chosen).
- Tradeoff: one extra file, clearer operational sequencing.

## Evidence

- Added:
  - `NEXT_AGENT_PROMPT_RETRIEVAL_AND_EVIDENCE.md`
- Updated:
  - `docs/README.md`

## Consequences

- Expected benefits:
  - clearer next-agent execution order,
  - explicit phase-safe matrix rerun instructions,
  - better odds of reproducible, complete handoff artifacts.
- Known risks:
  - command assumptions can still break if external API reliability degrades.
- Monitoring signals:
  - next run should produce repeat sets with gate checks and explicit partial-cell reporting if blocked.

## Follow-up

1. Use `NEXT_AGENT_PROMPT_RETRIEVAL_AND_EVIDENCE.md` for the next end-to-end implementation+rerun session.
2. If retrieval implementation completes separately first, use `NEXT_AGENT_PROMPT_RETRIEVAL.md` then reuse Stage 2 from combined prompt.
