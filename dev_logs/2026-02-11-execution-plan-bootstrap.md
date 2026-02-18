# 2026-02-11 - Execution Plan Bootstrap

## Context

- Project needed a concrete sequence: Vitali adaptation first, evaluation hardening second, report production third.
- Existing docs covered evaluation rationale but not implementation order, TDD gates, or decision-log process.

## Decision

- Adopt a three-workstream plan captured in `EXECUTION_PLAN.md`:
  1. Targeted adaptation of graph-plumbing ideas from `vitali87/code-graph-rag`.
  2. Evaluation build-out with explicit amortization tracks and metrics.
  3. Research-grade LaTeX report workflow.
- Introduce required development logs for major decisions under `dev_logs/`.
- Bootstrap manuscript scaffold under `research_report/`.

Scope boundaries:

- No immediate import of Memgraph/MCP/editing orchestration stack.
- Python-first adaptation; multi-language expansion deferred.

## Alternatives Considered

1. Keep current ad-hoc process with no formal plan.
   - Rejected: high risk of scope drift and unreproducible claims.
2. Implement adaptation first, document later.
   - Rejected: increased chance of undocumented design choices.
3. Fully port Vitali stack wholesale.
   - Rejected: over-engineering risk and novelty dilution for this project stage.

## Evidence

- Internal docs:
  - `idea.md`
  - `EVALUATION_SPEC.md`
  - `FUTURE_AGENT_HANDOFF.md`
- External source audit:
  - `vitali87/code-graph-rag` parser/resolver modules
  - SWE-bench, SWE-PolyBench, RepoBench, RepoExec repos/datasets

## Consequences

Expected benefits:

- Cleaner implementation sequencing and milestone gates.
- Better auditability of design choices.
- Faster path from experiments to paper-ready artifacts.

Known risks:

- More upfront process overhead.
- Potential drift if dev logs are not maintained consistently.

Monitoring signals:

- Presence of log entry for each major protocol or architecture change.
- Test-first PRs for resolver/evaluation modifications.

## Follow-up

1. Start A1 in `EXECUTION_PLAN.md` with failing tests first.
2. Add adapter/amortization metric tests before evaluation refactors.
3. Fill `research_report/sections/*` directly from frozen run artifacts.
