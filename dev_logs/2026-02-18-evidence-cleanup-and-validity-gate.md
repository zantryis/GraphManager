# 2026-02-18 - Evidence Cleanup, Validity Gate, and Repo Hardening

## Context

- Independent technical review identified critical evidence quality issue: the `langchain-ai/langchain`
  strict cell was producing all-zero F1 across all methods (gm_progressive=0.0, rag_progressive=0.0,
  gm_deterministic=0.0) with `setup_embedding_tokens=0`, yet was marked `ci_ready=True` after 3 runs.
- Root cause: `source_prefixes: [libs/langchain]` in `experiments_matrix_v2.yaml` does not exist at
  commit `3a1bdce3f51e302d468807e980455d676c0f5fd6` (April 2023). The `libs/` monorepo layout was
  introduced later. The correct prefix at that commit is `[langchain]` (514 Python files).
- README referenced stale/nonexistent artifact paths from pre-clean-eval checkpoints.
- Several `NEXT_AGENT_PROMPT_*.md` files cluttered the repo root.

## Decision

1. Add `validate_commit_context()` to `src/evaluation.py`: raises `ValueError` if any index's
   `setup_embedding_tokens == 0`. Wired into `get_or_build_commit_context()` so every future run
   fails loudly on empty index rather than silently scoring zero.

2. Mark the existing langchain strict repeat set as `valid: false` (not deleted — preserved for
   audit trail). `visualize_results.py` `load_repeat_set()` now returns `None` for any repeat set
   with `valid: false`.

3. Fix `source_prefixes: [libs/langchain]` → `[langchain]` in `experiments_matrix_v2.yaml`.
   Langchain cell not immediately re-run (not a current priority); fix is in place for when it is.

4. Freeze a clean artifact bundle:
   `research_report/artifacts/frozen-20260212-matrix-v2-clean/` (11 valid cells).

5. Update README to cite current clean_eval_20260211_201431 repeat sets and correct numbers.

6. Move/delete stale agent handoff docs from repo root (`NEXT_AGENT_PROMPT_*.md`, `idea.md`,
   `FUTURE_AGENT_HANDOFF.md`) to `dev_logs/`.

## Alternatives Considered

1. Re-run langchain with fixed prefix immediately — rejected, not a priority.
2. Delete invalid langchain repeat sets — rejected, kept for audit trail with `valid: false` marker.
3. Soft warning instead of hard ValueError for empty index — rejected, silent zeros are more
   dangerous than noisy failures.

## Evidence

- Langchain 3 runs all show `setup_embedding_tokens=0` in:
  `results/clean_eval_20260211_201431/runs/20260211_231558/summary.json` (and repeat runs)
- Verified: `git -C langchain_repo ls-tree 3a1bdce3 | grep libs` returns empty.
- `find langchain_repo -path '*/langchain/*.py' | wc -l` = 514 files at current HEAD (post-restructure).
- New tests: 5 additional tests in `tests/test_evaluation_logic.py` (validate_commit_context),
  1 additional test in `tests/test_visualize_results.py` (invalid cell filtering).
- Full test suite: 69 tests, all passing.

## Consequences

- Any future run with a wrong `source_prefixes` will fail immediately with a descriptive error.
- Langchain cell excluded from dashboard and claims until re-run with corrected config.
- 11 valid cells remain: 4 SWE-bench repos × (strict + same-snapshot) minus langchain's 2 cells,
  plus yt-dlp strict+same-snapshot, plus keras strict.

## Follow-up

1. Re-run langchain strict + same-snapshot with `source_prefixes: [langchain]` (optional, low priority).
2. Run keras same-snapshot cell (missing from clean run).
3. Coefficient tuning for `gm_deterministic` on frozen Flask+yt-dlp dev split.
4. Phase 2: implement minimal patching pipeline.
