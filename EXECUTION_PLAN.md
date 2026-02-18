# GraphManager Execution Plan (V1)

Last updated: 2026-02-11
Owner: GraphManager research track

## 1. Goal And Order

Execution order is fixed:

1. Adapt proven graph-plumbing logic from `vitali87/code-graph-rag` (minimal, targeted, Python-first).
2. Build and harden evaluation (retrieval + amortization + execution anchor).
3. Produce a research-grade report in LaTeX from frozen artifacts.

This plan assumes the current project goal remains:

- shared, cheap-to-query world model for codebases,
- manager policy that is cost-aware,
- strong retrieval signal before full MAS integration.

## 2. Working Principles

## Test-Driven Development (mandatory)

For every implementation unit:

1. `RED`: write/extend tests that fail for the missing behavior.
2. `GREEN`: implement minimal code to pass tests.
3. `REFACTOR`: simplify internals while preserving test pass.
4. `VERIFY`: run full project tests + task-specific regression checks.

No behavior change should merge without tests.

## Reproducibility

- Pin issue/task manifests for every benchmark run.
- Save run metadata (`model`, `commit`, `dataset`, `seed`, `timestamps`).
- Keep code snapshots and result folders versioned per run.

## Decision logging

- Every non-trivial design choice gets a short decision log entry in `dev_logs/`.
- Entries must include alternatives considered and evidence source.

## 3. Workstream A: Vitali Adaptation (First Priority)

Scope: Adapt only lower-layer graph plumbing. Do not import full product stack (Memgraph, MCP server, editing orchestration).

Target source areas from Vitali repo:

- `codebase_rag/parsers/call_resolver.py`
- `codebase_rag/parsers/call_processor.py`
- `codebase_rag/parsers/import_processor.py`
- `codebase_rag/parsers/type_inference.py`
- `codebase_rag/parsers/structure_processor.py`
- `realtime_updater.py` (ideas for future incremental graph updates)

## A1. Introduce resolver abstraction in local graph builder

Deliverable:

- Split current call/import/inheritance resolution in `src/graph_builder.py` into explicit components:
  - `ImportResolver`
  - `TypeInferenceEngine` (Python-focused, minimal)
  - `CallResolver`

TDD tasks:

1. Add failing tests for ambiguous call targets and imported-symbol disambiguation.
2. Add failing tests for method calls resolved via local variable type hints/inference.
3. Add failing tests for fallback behavior (same-module > imported > global fallback).

Acceptance criteria:

- Existing tests pass.
- New resolver tests pass.
- CALL edge precision improves on held-out issue slice (tracked in eval logs).

## A2. Build explicit import mapping cache

Deliverable:

- Module-level import mapping cache keyed by file/module ID (decoupled from call resolution loop).

TDD tasks:

1. Red tests for alias imports, `from x import y as z`, module imports, relative imports.
2. Red tests for cache consistency when parsing multiple files.

Acceptance criteria:

- Deterministic import-map outputs across repeated runs.
- Lower unresolved-call rate in diagnostic stats.

## A3. Add confidence-based call-link policy

Deliverable:

- Confidence tiers for call links:
  - high: exact local/import/type-resolved,
  - medium: same-module name match,
  - low: global suffix/trie-like fallback.

TDD tasks:

1. Red tests ensuring high-confidence links are preferred when multiple candidates exist.
2. Red tests ensuring low-confidence links are either marked or optionally skipped.

Acceptance criteria:

- Graph export includes confidence metadata.
- Ablation (`low-confidence disabled`) is runnable in evaluation.

## A4. Prepare incremental update interface (no heavy implementation yet)

Deliverable:

- Interface contract for incremental graph updates:
  - `update_files(changed_paths)`
  - `recompute_edges_for(changed_nodes, strategy=...)`

TDD tasks:

1. Red tests validating behavior equivalence:
   - incremental update output equals full rebuild output for controlled change sets.

Acceptance criteria:

- Interface exists + tests; full implementation can come later without API churn.

## 4. Workstream B: Evaluation Build-Out (Second Priority)

## B1. Unified dataset adapter layer

Deliverable:

- `src/datasets/` adapters for:
  - SWE-bench-style issue datasets,
  - SWE-PolyBench retrieval metrics mode.

TDD tasks:

1. Adapter unit tests for schema normalization (`instance_id`, `repo`, `base_commit`, `gold_files` extraction).
2. Regression tests for commit-fidelity grouping.

Acceptance criteria:

- Same evaluator entrypoint can run multiple dataset backends.

## B2. Amortization reporting as first-class metric

Deliverable:

- Add summary fields:
  - `commit_repeat_ratio`
  - `cache_hit_rate`
  - `N_break_even` (pairwise methods)
  - strict vs same-snapshot track separation

TDD tasks:

1. Unit tests for metric formulas.
2. Tests that strict and amortized tracks cannot be merged accidentally in aggregation.

Acceptance criteria:

- `summary.json` contains full amortization block.
- Plot/report scripts consume the new fields.

## B3. Manager policy efficiency diagnostics

Deliverable:

- Per-issue manager telemetry:
  - tool-call count by tool,
  - token-per-F1 delta,
  - stop reason (`budget`, `sufficient confidence`, `max_turns`).

TDD tasks:

1. Unit tests for telemetry serialization.
2. Regression tests for token accounting consistency.

Acceptance criteria:

- Can compare policy quality/cost explicitly, not just aggregate F1.

## B4. Evaluation tracks and gates

Track definitions:

1. Retrieval track: SWE-PolyBench metrics-only (+ node metrics when available).
2. Execution anchor: SWE-bench Verified subset.
3. Amortization study:
   - strict commit-fidelity,
   - same-snapshot world-model reuse.

Acceptance gates before moving to report phase:

1. All tests passing.
2. At least 3 repeat runs for main retrieval comparison.
3. Paired delta + bootstrap CI generated.
4. Manifest and run metadata archived.

## 5. Workstream C: Research-Grade Report (Third Priority)

Deliverable:

- LaTeX manuscript scaffold + reproducible figure/table pipeline.

Sections to complete:

1. Problem and hypothesis.
2. Method (graph, manager policy, amortization model).
3. Experimental setup.
4. Main results.
5. Ablations (resolver quality, policy budget, confidence filtering).
6. Threats to validity.
7. Limitations and future MAS integration.

Evidence policy:

- No claim in text without matching artifact:
  - table/figure,
  - config/manifest,
  - raw result path.

## 6. Milestone Plan

## M1: Vitali adaptation foundation

Exit criteria:

- Resolver modularization done.
- New resolver tests green.
- No regression on existing tests.

## M2: Evaluation hardening

Exit criteria:

- Unified adapters.
- Amortization metrics and strict-vs-amortized tracks.
- Repeated runs + CI stats available.

## M3: Report-ready package

Exit criteria:

- LaTeX draft compiles.
- Figures/tables generated from frozen results.
- Decision log references all major choices.

## 7. Test Matrix

Mandatory test layers per milestone:

1. Unit tests: resolvers, metrics, adapters.
2. Integration tests: end-to-end retrieval on small fixed issue set.
3. Regression tests: golden outputs for key resolver cases.
4. Statistical sanity checks: script-level checks for run completeness and CI computation.

Definition of done for each PR:

1. New failing tests introduced first.
2. Implementation passes full test suite.
3. Evaluation delta (if behavior change) recorded in dev log.
4. Documentation updated (`EVALUATION_SPEC.md`, plan, or report notes).

## 8. Immediate Next Actions (Concrete)

1. Implement A1 skeleton (resolver classes + wiring only) with failing tests first.
2. Implement A2 import-map cache + tests.
3. Implement A3 confidence policy + ablation switch + tests.
4. Add B2 amortization metrics block and tests.
5. Run pilot evaluation on a small fixed manifest and log outcomes.

