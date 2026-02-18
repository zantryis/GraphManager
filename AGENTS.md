# AGENTS.md

This file defines repository-specific instructions for any coding agent working in this project.

## Objective

Implement the GraphManager roadmap in this order:

1. Vitali-inspired graph plumbing adaptation (Python-first, minimal scope).
2. Evaluation hardening with amortization-first reporting.
3. Research-report artifact generation from frozen runs.

Authoritative planning docs:

- `EXECUTION_PLAN.md`
- `EVALUATION_SPEC.md`
- `RESEARCH_COMPARISON.md`
- `dev_logs/README.md`
- `docs/RETRIEVAL_REDESIGN_V1.md`
- `docs/EVALUATION_PLAN_V2.md`

## Must-Follow Workflow

1. Use strict TDD for behavior changes:
   - write failing tests first,
   - implement minimal fix,
   - refactor safely,
   - run full test suite.
2. Preserve existing behavior unless tests and plan explicitly call for change.
3. Prefer targeted adaptation over wholesale imports from external repos.
4. Record major decisions in `dev_logs/` with the template in `dev_logs/TEMPLATE.md`.
5. Keep experiments reproducible:
   - fixed manifests,
   - explicit run metadata,
   - clear artifact paths.

## Current Implementation Priority

Workstream A is largely implemented. Current priority is:

1. Deterministic graph-first retrieval redesign and implementation:
   - implement `docs/RETRIEVAL_REDESIGN_V1.md`,
   - reduce loop-heavy retrieval overhead,
   - use explicit evidence scoring + coefficient tuning with reproducible settings.
2. Evaluation redesign and rigor across broader benchmark/domain coverage:
   - move beyond narrow 3-4 repo slices,
   - keep manifested strict vs same-snapshot tracks,
   - report paired deltas + bootstrap CI.
3. Viewer/report alignment with redesigned retrieval + evaluation:
   - emphasize cross-task cost-quality/frontier views over noisy panels,
   - regenerate data and frozen artifacts,
   - keep docs/report text aligned to latest reproducible evidence.

Do not start MAS orchestration or large productization work yet.

## Testing Requirements

Before completing any implementation task:

1. Run unit tests:
   - `./.venv/bin/python -m unittest discover -s tests -v`
2. Add or update tests for new behavior.
3. Include regression coverage for resolver edge cases.

If test infra changes are required, document why in `dev_logs/`.

## Quality Bar

Every implementation PR-equivalent should include:

1. Code changes.
2. Tests proving the change.
3. Decision log entry (if the change is non-trivial).
4. Short note of evaluation impact or expected impact.
