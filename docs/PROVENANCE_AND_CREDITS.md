# Provenance And Credits

This document records which ideas/components were adapted and where they came from.

## Primary external source

- `vitali87/code-graph-rag`:
  - URL: `https://github.com/vitali87/code-graph-rag`
  - Local reference pointer: `previous_work/code-rag-repo`

## Other prior material used for this project

- Original idea/proposal in this repo: `idea.md`
- Background paper snapshot in this repo: `previous_work/2601.08773v1.pdf`

## Adaptation map (high level)

1. Import parsing and alias handling:
- Source idea: `codebase_rag/parsers/import_processor.py`
- Local adaptation: `src/resolvers.py` (`ImportResolver`)
- Note: local code is Python-focused and simplified to current benchmark scope.

2. Type-aware call target inference:
- Source idea: `codebase_rag/parsers/type_inference.py`
- Local adaptation: `src/resolvers.py` (`TypeInferenceEngine`)
- Note: local implementation keeps only minimal local variable type-hint/constructor inference.

3. Call resolution ordering and fallback policy:
- Source idea: `codebase_rag/parsers/call_resolver.py`, `codebase_rag/parsers/call_processor.py`
- Local adaptation: `src/resolvers.py` (`CallResolver`) + `src/graph_builder.py` integration
- Note: local code adds confidence tiers (`high`, `medium`, `low`) and optional low-confidence filtering.

4. Structural graph extraction pattern:
- Source idea: `codebase_rag/parsers/structure_processor.py`
- Local adaptation: `src/graph_builder.py`
- Note: local graph schema is intentionally narrower (file/class/function + typed edges).

5. Incremental-update interface direction:
- Source idea: `realtime_updater.py`
- Local adaptation: `src/graph_builder.py` (`update_files`, `recompute_edges_for`)
- Note: current strategy is conservative full rebuild for deterministic behavior parity.

## Non-goals (explicit)

The following are intentionally NOT imported from the source system:

- Memgraph runtime/ingestor stack
- MCP service orchestration and product-level APIs
- full multi-language parsing/typing surface

## Citation policy for report/docs

When discussing adapted logic, cite:

1. `codegraphrag` reference in `research_report/references.bib`
2. this provenance doc (`docs/PROVENANCE_AND_CREDITS.md`)
3. local implementation paths (`src/resolvers.py`, `src/graph_builder.py`)

