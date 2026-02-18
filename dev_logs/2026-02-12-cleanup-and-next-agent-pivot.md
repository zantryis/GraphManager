# 2026-02-12 - Cleanup And Next-Agent Priority Pivot

## Context

- The repository had accumulated intermediate build artifacts and incomplete run directories that added noise.
- The next phase needed a clearer priority order aligned to current research needs: broader evaluation design, then viewer redesign, then fresh data generation.
- Affected files: `NEXT_AGENT_PROMPT.md`, `FUTURE_AGENT_HANDOFF.md`, `research_report/main.*`, `results/runs/*`.

## Decision

- Perform a conservative cleanup pass:
  - remove transient LaTeX build byproducts while keeping `research_report/main.pdf`,
  - move incomplete runs out of `results/runs/` into `results/runs_incomplete/` (non-destructive),
  - remove local non-venv `__pycache__` directories.
- Rewrite next-agent instructions to enforce this order:
  1. evaluation redesign across broader benchmarks/domains,
  2. viewer redesign around cross-task tradeoff analysis,
  3. data regeneration and frozen-artifact insight pass.
- Scope boundary: no new experiment runs and no viewer/evaluation code changes in this pass.

## Alternatives Considered

1. Delete incomplete runs outright.
- Tradeoff: cleaner immediately, but loses forensic traces.
2. Leave all artifacts in place.
- Tradeoff: preserves everything, but keeps repo noisy and confusing.
3. Non-destructive archive of incomplete runs (chosen).
- Tradeoff: slightly more files, but clear separation and lower risk.

## Evidence

- Prompt and handoff edits:
  - `NEXT_AGENT_PROMPT.md`
  - `FUTURE_AGENT_HANDOFF.md`
- Cleanup targets:
  - removed: `research_report/main.aux`, `research_report/main.bbl`, `research_report/main.blg`, `research_report/main.fdb_latexmk`, `research_report/main.fls`, `research_report/main.log`, `research_report/main.out`
  - moved: `results/runs/20260211_111939`, `results/runs/20260211_112301`, `results/runs/20260211_171718`, `results/runs/20260211_172040` -> `results/runs_incomplete/`

## Consequences

- Expected benefits:
  - lower repo noise for handoff and review,
  - clearer execution order for the next implementation cycle.
- Known risks:
  - archived incomplete runs may still be mistaken for usable evidence unless filtered by completion checks.
- Monitoring signals:
  - next-agent artifacts should reference only completed run folders with `summary.json`,
  - viewer/report should pull from frozen bundles produced after redesign work.

## Follow-up

1. Execute the new prompt sequence (evaluation redesign -> viewer redesign -> reruns/analysis).
2. Run full unit suite after each behavior-changing implementation step.
3. Generate new repeat sets and frozen report artifacts from the redesigned benchmark matrix.
