# V2 Baseline Rebuild Design: `repomap_like` and `agentless_like_localization`

Date: 2026-02-24
Status: Proposed
Author: Codex

## 1) Goal

Decide whether to lift the "published-numbers only" lock for Agentless/RepoMap and, if so,
define a technically defensible implementation plan in this repository.

This design targets **component-equated comparison** under the existing GraphManager patching
pipeline (fixed-context patch stage), rather than full end-to-end reproduction of external systems.

## 2) Comparability Levels (Explicit)

## L0: Contextual-only (current lock)
- Use published Agentless/RepoMap numbers as references.
- No internal implementation.

## L1: Component-equated "X-like" baselines (recommended)
- Implement `repomap_like` and `agentless_like_localization` as retrieval/localization components.
- Keep downstream patch stage constant (`PatchAgent`, single-sample, fixed-context).
- Claim: "comparable localization strategies under a shared downstream pipeline."

## L2: Full system reproduction (not recommended now)
- Rebuild full Agentless pipeline (including multi-sample repair and test generation/selection).
- Rebuild full RepoMap interactive usage loop as primary context mechanism.
- Claim: direct end-to-end parity with originals.

Decision boundary:
- L1 is scientifically useful for this thesis and feasible in this codebase.
- L2 is a separate project scope and likely derails current V2 timeline.

## 3) Proposed Baseline Contracts

## 3.1 `repomap_like` (new retrieval method)

Intent:
- Approximate RepoMap's file-level graph + PageRank ranking behavior for file selection.

Inputs:
- `issue_text`
- `repo_dir`
- optional `source_prefixes`

Outputs:
- ordered file list (`list[str]`), same contract as other retrieval methods.
- token/cost metadata.

Core algorithm:
1. Build a symbol map (functions/classes + owning files) using tree-sitter.
2. Build a file-level directed graph with explicit edge semantics:
   - `import`: file A imports module/file B
   - `symbol_ref`: file A references symbol defined in file B
   - `test_ref`: test file A references source file B
   - `same_module` (optional, default off): weak adjacency for files in same module/package
3. Assign deterministic edge weights (fixed defaults; no learned weights):
   - `import=1.0`, `symbol_ref=1.0`, `test_ref=0.5`, `same_module=0.2`
   - if multiple edges of same type exist, sum then row-normalize outgoing edge weights
4. Build personalization vector from issue tokens and explicit path mentions.
5. Run personalized PageRank to rank files.
6. Generate a token-budgeted map snapshot (symbol-level map text) for auditability.
7. Induce file ranking from symbol-level map and return top-k files.

Required manifest/config fields:
- `retrieval_method: repomap_like`
- `repomap_like_map_tokens` (default 1000)
- `repomap_like_top_k_files` (default 10)
- `repomap_like_use_llm_selector` (default false)
- `repomap_like_refresh_mode` (`static_per_issue` default; optional `dynamic_turn`)
- `repomap_like_edge_weights` (optional override map; defaults above)
- `repomap_like_enable_same_module_edge` (default false)

Design note:
- We build a symbol-level map but evaluate its induced file ranking, because the current
  patch stage consumes file context rather than symbol spans.

## 3.2 `agentless_like_localization` (new retrieval method)

Intent:
- Approximate Agentless's hierarchical localization while preserving fixed-context patching.

Inputs:
- `issue_text`
- `repo_dir`
- optional `source_prefixes`

Outputs:
- ordered file list (`list[str]`) for patch stage.
- stage-by-stage metadata and token accounting.

Core algorithm:
1. Stage 1 (file-level combined):
   - Constrained LLM file ranking branch over an explicit candidate file list.
   - Dense retrieval branch (embedding-based file/chunk ranking).
   - Merge/rerank candidates.
2. Stage 2 (element-level):
   - Build skeleton view for candidate files.
   - LLM selects relevant classes/functions from provided candidates only.
3. Stage 3 (edit-location-level):
   - Input: skeleton + bounded surrounding context window per selected symbol.
   - Output schema: `(file, start_line, end_line, confidence)` (or equivalent typed JSON).
   - Sampling: default 4 location proposals (1 deterministic + 3 stochastic with fixed seed path).
   - Enforce hard per-file token caps in Stage 3 context.
4. Convert selected spans/symbols to final file set for patch stage.

Required manifest/config fields:
- `retrieval_method: agentless_like_localization`
- `agentless_like_stage2_enabled` (default true)
- `agentless_like_stage3_enabled` (default true)
- `agentless_like_edit_location_samples` (default 4)
- `agentless_like_file_branch_top_n` (default 3)
- `agentless_like_embed_branch_top_k` (default 20)
- `agentless_like_merge_top_k` (default 12)
- `agentless_like_stage3_context_window_lines` (default 10)
- `agentless_like_stage3_max_tokens_per_file` (default fixed cap)
- `agentless_like_constrained_candidates_max` (default 200; candidate pool bound)
- `agentless_like_reject_out_of_candidate_paths` (default true)

## 4) Integration Points in This Repo

1. Retrieval experiment path
- Add methods to `run_experiment.py`/`src.evaluation` method lists and dispatch.

2. Patching path
- Extend `run_patch.py` retrieval dispatch (`_run_retrieval`) and method-scoped context builder.

3. Cost accounting
- Preserve current schema; add optional per-stage counters for `agentless_like`.
- Add `repomap_like_map_tokens_used` to retrieval metadata.

4. Canonicalization and path safety
- Reuse current canonicalization + repo containment checks already hardened.

## 5) Ablation Plan (Must-Have)

## `repomap_like` ablations
1. map token budget: 512 vs 1000 vs 2000
2. personalization: on vs off
3. selector mode: deterministic rank-only vs LLM selector over map text
4. refresh mode: static_per_issue vs dynamic_turn

## `agentless_like_localization` ablations
1. stage toggles: stage1 only vs stage1+2 vs stage1+2+3
2. file-level branch: llm-only vs embed-only vs merged
3. edit-location samples: 1 vs 4
4. skeleton compression: on vs off
5. constrained candidate pool size: 50 vs 100 vs 200

## Cross-method fairness ablations
1. fixed downstream patch config held constant
2. identical `patch_max_file_chars` and patch model across methods
3. retrieval budget caps reported per method
4. shared post-retrieval patch cap (`retrieval_max_files_for_patch`, default `6`) held constant

## 6) Validation and Tests

Required tests before running pilots:
1. unit tests for new method dispatch and schema fields
2. deterministic behavior tests for ranking outputs given fixed seed
3. path-safety tests for all new file-read paths
4. artifact contract tests (`summary.json`, per-instance stage metadata)
5. retrieval-only smoke run with `--methods repomap_like,agentless_like_localization`
6. constrained generation tests:
   - out-of-candidate path proposals are rejected
   - invalid selection rate is reported
   - final files are subset of allowed candidate pool

Required monitoring metrics for fidelity:
1. `invalid_path_selection_rate` (Stage 1 LLM branch)
2. `out_of_candidate_rejection_count`
3. `stage3_span_schema_violation_rate`
4. `repomap_edge_type_counts` and effective row-normalized weight distribution

## 7) Execution Phases

## Phase A (recommended to execute now)
- Implement `repomap_like` + `agentless_like_localization` in L1 form.
- Run retrieval-only comparisons on Flask/Requests/Pytest.
- If quality/cost are stable, include in patch pilot manifests for a bounded subset.

## Phase B (conditional)
- Add selected ablations from Section 5.
- Decide whether to include both methods in full 500-instance patch sweep.

## Phase C (optional future)
- Full L2 reproduction attempt (external-system-parity study).

## 8) Threats and Claim Language

Allowed claim:
- "We implement RepoMap-like and Agentless-like localization baselines under a shared,
  fixed downstream patching protocol to isolate retrieval/localization contribution."

Disallowed claim:
- "We faithfully reproduced full Agentless/RepoMap end-to-end performance."

## 9) Self-Evaluation and Proceed Decision

My evaluation:
- Technical feasibility: HIGH for L1, LOW/MEDIUM for L2 in current timeline.
- Scientific value: HIGH for L1 (directly addresses your strongest comparison concern).
- Risk to schedule: MODERATE for L1, HIGH for L2.

Would I proceed?
- **Yes, I would proceed with L1 now.**
- **No, I would not proceed with L2 right now.**

Reason:
- L1 gives meaningful, defensible comparisons while preserving thesis focus and execution velocity.
- L2 likely delays V2 substantially and introduces major confounds (pipeline/model/runtime mismatch)
  before your core question is answered.

## 10) Concrete Next Step

Implement `repomap_like` first (smaller surface area, mostly deterministic), then implement
`agentless_like_localization` Stage 1 only, then stage up to Stage 2/3 after initial retrieval
smoke results confirm stability.
