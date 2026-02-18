# Development Logs

This directory records major engineering/research decisions.

Purpose:

- preserve reasoning behind design choices,
- make experiments auditable,
- reduce repeated debate about previously-settled tradeoffs.

## Logging Rules

Create one file per decision batch:

- format: `YYYY-MM-DD-short-title.md`
- example: `2026-02-11-execution-plan-bootstrap.md`

Required fields per entry:

1. `Context`
2. `Decision`
3. `Alternatives considered`
4. `Evidence`
5. `Consequences`
6. `Follow-up`

Keep entries short, factual, and linked to code paths and result artifacts.

## Cadence

Add an entry when:

1. architecture changes,
2. evaluation protocol changes,
3. benchmark selection changes,
4. metric definitions change,
5. report claims are added/removed due to evidence.

## References

- Execution roadmap: `EXECUTION_PLAN.md`
- Evaluation protocol: `EVALUATION_SPEC.md`
- Report scaffold: `research_report/main.tex`
