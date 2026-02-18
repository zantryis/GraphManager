# 2026-02-11 - Call Confidence Policy And Incremental Interface Contract (A3/A4)

## Context

- After A1/A2 modularization, Workstream A required confidence-tiered call links (A3) and a stable incremental-update interface (A4).
- Existing CALL edges had no confidence metadata and always emitted global fallback links.
- No incremental API existed to preserve forward compatibility for future non-full-rebuild update strategies.

## Decision

- Added confidence metadata to CALL edges:
  - `high`: exact local/self/import/type-inferred resolution
  - `medium`: same-module name fallback
  - `low`: global fallback by ranked path similarity
- Added `GraphBuilder(..., include_low_confidence_calls: bool = True)`:
  - default keeps current behavior,
  - `False` skips `low` confidence CALL edges (A3 ablation hook).
- Added incremental interface methods in `GraphBuilder`:
  - `update_files(changed_paths)`
  - `recompute_edges_for(changed_nodes, strategy="full")`
- Current A4 strategy is conservative full rebuild for deterministic equivalence; no partial updater yet.

## Alternatives Considered

1. Keep confidence logic external to graph edges.
Tradeoff: less intrusive, but downstream evaluation/export cannot filter by confidence without recomputing provenance.
2. Introduce aggressive partial incremental updates immediately.
Tradeoff: potential speedup, but higher regression risk without stable API/tests first.
3. Skip low-confidence links entirely by default.
Tradeoff: potentially higher precision, but behavior change too early; kept opt-in suppression instead.

## Evidence

- Tests added in `tests/test_graph_builder_resolution.py`:
  - `test_call_resolution_adds_confidence_metadata`
  - `test_call_resolution_can_disable_low_confidence_edges`
  - `test_graph_export_includes_call_confidence_metadata`
- Tests added in `tests/test_graph_builder_incremental.py`:
  - `test_update_files_matches_full_rebuild_for_controlled_changes`
  - `test_recompute_edges_for_matches_full_rebuild`
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 21 tests passing.

## Consequences

- Expected benefits:
  - Confidence-aware filtering/ablation is now possible without re-resolution.
  - Graph exports carry provenance-ready metadata for evaluation.
  - Incremental API surface is stable for future non-full-rebuild implementations.
- Known risks:
  - `medium` confidence still relies on lexical same-module heuristics.
  - A4 currently trades runtime for correctness (full rebuild fallback).
- Monitoring signals:
  - quality deltas with `include_low_confidence_calls=False`,
  - unresolved-call rate and false-link diagnostics,
  - parity checks between future incremental and full rebuild outputs.

## Follow-up

1. Add evaluation toggles/metrics that report confidence-tier usage and ablations.
2. Implement non-full incremental recomputation behind existing A4 API.
3. Start Workstream B1 dataset adapter layer with schema-normalization tests.
