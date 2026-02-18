# Vitali Parity Audit (Graph Plumbing)

Purpose: make it explicit what is close to Vitali's approach, what is adapted, and what is new.

## Summary

- Overall status: **adapted parity**, not line-by-line port.
- Confidence: high for import/call/type-flow ordering concepts; medium for edge-case equivalence.

## Component-by-component parity

1. Import mapping
- Vitali source: `codebase_rag/parsers/import_processor.py`
- Local: `src/resolvers.py::ImportResolver`
- Status: `adapted`
- Notes:
  - supports alias/module/from-import/wildcard handling
  - intentionally reduced surface for Python-first scope

2. Type inference for call disambiguation
- Vitali source: `codebase_rag/parsers/type_inference.py`
- Local: `src/resolvers.py::TypeInferenceEngine`
- Status: `adapted`
- Notes:
  - local keeps minimal local variable type hints + constructor inference
  - does not implement full multi-language inference stack

3. Call resolution decision order
- Vitali source: `codebase_rag/parsers/call_resolver.py`, `call_processor.py`
- Local: `src/resolvers.py::CallResolver`
- Status: `adapted + extended`
- Notes:
  - preserves ordered resolution strategy and import-aware disambiguation intent
  - adds confidence tiers and low-confidence edge suppression flag

4. Structural extraction and graph assembly
- Vitali source: `codebase_rag/parsers/structure_processor.py`
- Local: `src/graph_builder.py`
- Status: `adapted`
- Notes:
  - local schema narrowed to file/class/function nodes and key edges only

5. Incremental update surface
- Vitali source: `realtime_updater.py`
- Local: `src/graph_builder.py` (`update_files`, `recompute_edges_for`)
- Status: `concept adapted`
- Notes:
  - API contract exists, implementation intentionally conservative (full rebuild)

## What is clearly new in local repo

- Confidence-tagged CALL edge policy and tests
- Evaluation-track separation (strict vs same-snapshot)
- Amortization-first reporting, repeat CI gates, paired bootstrap deltas
- Manager telemetry and retrieval-loop token efficiency shaping

## Hallucination-risk checks

Use these checks whenever parity concerns arise:

1. Read source + local component side-by-side (paths above).
2. Verify behavior with local tests:
- `tests/test_graph_builder_resolution.py`
- `tests/test_import_mapping_cache.py`
- `tests/test_graph_builder_incremental.py`
3. If mismatch is suspected, write a targeted regression test first, then patch minimally.

