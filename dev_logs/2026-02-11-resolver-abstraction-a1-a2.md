# 2026-02-11 - Resolver Abstraction And Import-Map Cache (A1/A2)

## Context

- Workstream A in `EXECUTION_PLAN.md` requires resolver modularization (A1) followed by import-map cache hardening (A2).
- `src/graph_builder.py` contained inline import/base/call resolution logic, which made policy changes (ordering, disambiguation, inference) difficult to test in isolation.
- New test requirements called out ambiguous call handling, imported-symbol disambiguation, type-driven method calls, and cache consistency across files.

## Decision

- Introduced explicit resolver components in `src/resolvers.py`:
  - `ImportResolver`
  - `TypeInferenceEngine`
  - `CallResolver`
- Kept parsing/syntax-tree traversal in `GraphBuilder`, but delegated import parsing, import target resolution, base-class resolution, and call linking to resolver components.
- Updated call-link ordering for unqualified calls to `same-module > imported > global`.
- Added deterministic import-name binding semantics (`latest import wins`) and module-aware handling for `from ... import ...` submodule aliases (including relative imports like `from . import local as alias`).
- Scope boundary: no confidence-tier metadata (A3) and no incremental update API (A4) in this change.

## Alternatives Considered

1. Keep resolver logic inline in `GraphBuilder`.
Tradeoff: fewer files, but poor testability and harder iteration for A2/A3 behaviors.
2. Full port of external parser stack from `vitali87/code-graph-rag`.
Tradeoff: faster feature breadth, but too large/risky vs current minimal Python-first scope.
3. Extract only call resolution and leave imports/inheritance inline.
Tradeoff: partial cleanup, but import cache and base-class behavior would remain coupled and harder to harden.

## Evidence

- Tests added:
  - `tests/test_graph_builder_resolution.py`
    - `test_call_resolution_prefers_same_module_symbol_over_imported_and_global`
    - `test_call_resolution_uses_latest_import_binding_for_same_alias`
    - `test_call_resolution_disambiguates_methods_using_local_type_hint`
  - `tests/test_import_mapping_cache.py`
    - `test_import_map_cache_captures_module_symbol_and_relative_module_aliases`
    - `test_import_map_cache_is_isolated_per_file`
- Required full suite run:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 16 tests, all passing.

## Consequences

- Expected benefits:
  - More deterministic call links in ambiguous/import-heavy files.
  - Better precision for object-method calls when local type hints/constructor bindings are present.
  - Import-map cache behavior is explicit and validated per file.
- Known risks:
  - Type inference remains intentionally shallow (assignment/type-hint driven only).
  - Python edge cases around dynamic imports or complex typing expressions are still unresolved.
- Monitoring signals:
  - unresolved-call rate in diagnostics,
  - multi-target call-edge frequency for ambiguous names,
  - resolver regression tests in CI.

## Follow-up

1. Implement A3 confidence tiers on call edges (high/medium/low) using resolver provenance.
2. Add resolver regression cases for annotation unions/generics and chained relative imports.
3. Measure A1/A2 effect on unresolved-call rate and held-out call-edge precision slice in eval artifacts.
