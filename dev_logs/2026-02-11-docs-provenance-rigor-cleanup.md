# 2026-02-11 - Docs Cleanup + Provenance/Rigor Documentation Pack

## Context

- User requested a docs-first pass to address five concerns:
  1. missing credit for prior work,
  2. insufficient evaluation-plan detail,
  3. uncertainty about parity with Vitali adaptation,
  4. need for a plain-language explanation,
  5. concern about scientific/engineering rigor.
- Repository root also contained prompt-oriented intermediate markdown that was not part of the primary workflow.

## Decision

- Added a stable `docs/` documentation pack:
  - `docs/README.md`
  - `docs/PROVENANCE_AND_CREDITS.md`
  - `docs/VITALI_PARITY_AUDIT.md`
  - `docs/EVALUATION_PLAN_V2.md`
  - `docs/UNDERSTANDING_GRAPHMANAGER.md`
  - `docs/RIGOR_CHECKLIST.md`
- Archived non-core prompt doc:
  - moved `RED_TEAM_PROMPT.md` -> `docs/archive/RED_TEAM_PROMPT.md`
- Added explicit attribution references in manuscript text:
  - `research_report/sections/02_related_work.tex`
  - `research_report/sections/09_appendix.tex`
- Linked docs index from project README.

Scope boundary:
- No retrieval/pipeline behavior changes in this decision batch.

## Alternatives Considered

1. Leave docs in root and only add one FAQ file.
Tradeoff: minimal churn, but does not solve discoverability/cleanliness problem.

2. Remove all non-core markdown aggressively.
Tradeoff: cleaner root, but risks losing useful operational prompts/history.

3. Create structured docs pack and archive only clearly non-core prompt material (chosen).
Tradeoff: modest restructuring with low risk and better maintainability.

## Evidence

- New docs files under `docs/` provide direct coverage for each concern.
- Report now contains explicit external adaptation credit (`codegraphrag` citation + doc pointers).
- Root markdown count reduced by archiving red-team prompt file.

## Consequences

Expected benefits:
- Clearer documentation entrypoint and reduced ambiguity about what to read first.
- Explicit credit/provenance trail for adapted ideas.
- More concrete, benchmark/domain-oriented evaluation plan for next experiments.
- Better trust model via formal rigor checklist.

Known risks:
- Some operational prompts remain in root by design (`NEXT_AGENT_PROMPT.md`, `FUTURE_AGENT_HANDOFF.md`) because they are still active workflow artifacts.

Monitoring signals:
- Whether contributors can onboard from `docs/README.md` without additional handholding.
- Whether future report claims consistently cite frozen artifacts and pass rigor checklist gates.

## Follow-up

1. Execute `docs/EVALUATION_PLAN_V2.md` with larger fixed manifests and CI-ready repeat sets.
2. Keep `docs/VITALI_PARITY_AUDIT.md` updated when resolver logic changes.
3. Re-run report build and keep attribution references synchronized with code changes.
