# V2 New Baselines Implementation (2026-02-24)

## Implemented Methods

1. `repomap_like`
- Module: `src/repomap_like.py`
- Core behavior:
  - Builds file-level graph from explicit edge semantics (`import`, `symbol_ref`, `test_ref`, optional `same_module`).
  - Applies deterministic edge-weight policy and row-normalization.
  - Computes personalized PageRank over files.
  - Produces map snapshot token accounting.
  - Optional constrained LLM selector over candidate file list.

2. `agentless_like_localization`
- Module: `src/agentless_like_localization.py`
- Core behavior:
  - Stage 1: constrained candidate pool + dense retrieval branch + optional constrained LLM file ranking branch.
  - Stage 2: symbol-level selection over candidate files (deterministic fallback + optional constrained LLM selection).
  - Stage 3: edit-span proposal from selected symbols (deterministic fallback + optional constrained LLM span selection with schema checks).
  - Final output projected to file list for patch stage.

## Runtime Integration

- `run_patch.py`
  - `repomap_like` and `agentless_like_localization` supported in `_run_retrieval` dispatch.
  - Method-scoped setup behavior:
    - `repomap_like`: graph structure build only (no embedding setup tokens).
    - `agentless_like_localization`: graph structure + function-chunk RAG index (method-accounted setup = RAG embedding tokens).

- `src/evaluation.py` / `run_experiment.py`
  - Both methods added to method catalogs.
  - Validation updated so `repomap_like` requires non-empty graph structure (not graph embedding tokens).
  - `agentless_like_localization` requires graph structure and non-empty RAG-function index.

## Manifest Knobs (Ablation-ready)

### `repomap_like`
- `repomap_like_map_tokens`
- `repomap_like_top_k_files`
- `repomap_like_use_llm_selector`
- `repomap_like_refresh_mode`
- `repomap_like_edge_weights`
- `repomap_like_enable_same_module_edge`
- `repomap_like_personalization_enabled`

### `agentless_like_localization`
- `agentless_like_stage2_enabled`
- `agentless_like_stage3_enabled`
- `agentless_like_edit_location_samples`
- `agentless_like_file_branch_top_n`
- `agentless_like_embed_branch_top_k`
- `agentless_like_merge_top_k`
- `agentless_like_stage3_context_window_lines`
- `agentless_like_stage3_max_tokens_per_file`
- `agentless_like_constrained_candidates_max`
- `agentless_like_reject_out_of_candidate_paths`

## Scientific Ablation Generator

Script:
- `tools/generate_v2_baseline_ablation_manifests.py`

Profiles included:
- `repomap_base`
- `repomap_map512`
- `repomap_map2000`
- `repomap_no_personalization`
- `repomap_selector`
- `agentless_stage1_only`
- `agentless_stage12`
- `agentless_full`
- `agentless_embed_only`

Example:
```bash
./.venv/bin/python tools/generate_v2_baseline_ablation_manifests.py \
  --repos psf/requests pallets/flask pytest-dev/pytest \
  --output-dir patch_manifests/v2_ablation
```

## Validation

- Full unit suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: `240` passing tests.
- Added dedicated tests:
  - `tests/test_repomap_like.py`
  - `tests/test_agentless_like_localization.py`
  - `tests/test_generate_v2_baseline_ablation_manifests.py`
  - `tests/test_patch_runner.py` extended for new dispatch/setup paths.
