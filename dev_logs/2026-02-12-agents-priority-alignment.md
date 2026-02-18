# 2026-02-12 - AGENTS Priority Alignment

## Context

- Repository direction shifted toward deterministic graph-first retrieval implementation and broader evaluation/viewer redesign.
- `AGENTS.md` current-priority section still reflected older retrieval-hardening wording and did not reference the new retrieval redesign spec directly.

## Decision

- Update `AGENTS.md` to align active priorities with current project direction:
  1. deterministic retrieval redesign (`docs/RETRIEVAL_REDESIGN_V1.md`),
  2. broader evaluation redesign with strict/snapshot rigor,
  3. viewer/report alignment from regenerated frozen artifacts.
- Add `docs/RETRIEVAL_REDESIGN_V1.md` and `docs/EVALUATION_PLAN_V2.md` to authoritative planning docs.

Scope boundary:
- no behavior/code-path changes,
- no experiment reruns.

## Alternatives Considered

1. Leave `AGENTS.md` unchanged and rely on prompt files only.
- Tradeoff: less edit churn, but higher risk of conflicting instructions across sessions.
2. Move all guidance out of `AGENTS.md` into per-session prompts.
- Tradeoff: flexible but weak long-lived repository governance.
3. Keep `AGENTS.md` as stable policy + update priorities to current state (chosen).
- Tradeoff: minimal changes with clearer continuity.

## Evidence

- Updated:
  - `AGENTS.md`

## Consequences

- Expected benefits:
  - lower instruction drift between sessions,
  - clearer first-read source of truth for incoming agents.
- Known risks:
  - future priority changes still require periodic governance updates.
- Monitoring signals:
  - next-agent prompts and `AGENTS.md` should not conflict on primary sequence.

## Follow-up

1. Keep `AGENTS.md`, `NEXT_AGENT_PROMPT.md`, and `NEXT_AGENT_PROMPT_RETRIEVAL.md` synchronized when priorities change.
2. During retrieval implementation, enforce TDD and reproducible artifact logging per existing policy.
