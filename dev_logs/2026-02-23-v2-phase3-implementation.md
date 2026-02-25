# 2026-02-23 - V2 Phase 3 Implementation

## Context

Phase 1 (research) and Phase 2 (engineering fixes) complete. This session implements
the Phase 3 deliverables from `v2_phase3_handoff.md`:
- Step 1: BM25 retrieval baseline
- Step 2: Symmetric file-read tool for rag_progressive
- Step 3: V2 patching manifests

All work is TDD (tests before implementation). Full test suite must pass after each step.

## Step 1: BM25 Retrieval Baseline

### Decision
**File-level BM25Plus** over Python files only. One document per file.

### Implementation: `src/bm25_baseline.py`

Key choices:
- **BM25Plus** (not BM25Okapi): Okapi gives negative IDF scores for terms appearing in
  all documents (small corpora). BM25Plus guarantees non-negative IDF via
  `idf = log((N+1)/freq)`, which always ≥ 0.
- **Regex tokenizer** (`re.findall(r"[a-z0-9]+", text.lower())`): Splits camelCase and
  snake_case identifiers properly. `"main():"` → `["main"]`; `"alpha_function"` →
  `["alpha", "function"]`. Whitespace-splitting is inadequate for code.
- **`score > 0.0` filter**: Files with zero BM25 score (all query terms have zero IDF
  because they're absent from all files) are excluded. Keeps result list clean.

Interface:
```python
class BM25Index:
    def __init__(self, repo_dir: str, include_prefixes: tuple[str,...] | None = None)
    def build(self) -> None
    def query(self, query_text: str, top_k: int = 10) -> list[str]
    def find_relevant_files(self, issue_text: str, top_k: int = 10) -> tuple[list[str], dict]
    @property embedding_tokens_estimate -> int  # always 0
```

### Tests: `tests/test_bm25_baseline.py` (12 new tests)
All pass. Coverage:
- Relevant file ranked first for 2 different query types
- embedding_tokens_estimate = 0
- Empty repo → empty list
- include_prefixes filtering
- top_k limiting
- No duplicates (file-level index)
- Only .py files indexed
- No crash on unmatched query

### Pipeline wiring
1. `src/bm25_baseline.py` — new file
2. `run_experiment.py`: `"bm25"` added to `ALL_METHODS` list
3. `src/evaluation.py`:
   - Import `BM25Index`
   - `ALL_METHODS` and `METHOD_LABELS` updated
   - `validate_commit_context`: BM25 validated by `bm25_file_paths` set (not embedding tokens)
   - `get_or_build_commit_context`: `needs_bm25` build path added
   - Context dict: `"bm25_index"`, `"bm25_file_paths"` added
   - Per-commit setup: `"bm25"` added to `raw_methods` list
   - Per-issue loop: `valid_files` dispatch updated for BM25
4. `run_patch.py`:
   - `_run_retrieval`: `bm25_index=None` added; BM25 dispatch added
   - `_build_method_scoped_commit_context`: BM25 build path + context update added
   - Both `_run_retrieval` call sites updated with `bm25_index=context.get("bm25_index")`
5. `tests/test_evaluation_logic.py`: Updated `test_validate_commit_context_passes_on_valid_context`
   to include `bm25_file_paths` in context (required by new BM25 validation).

### rank_bm25 installation
```bash
./.venv/bin/pip install rank_bm25
```
Already present after install. `BM25Plus` class confirmed importable.

---

## Step 2: Symmetric File-Read Tool for rag_progressive

### Decision
- `get_file_contents(path)` tool added to `RAGAgent`
- Enabled via manifest flag `rag_symmetric_tools: true` (default `false` for backward compat)
- Requires `repo_dir` to be set; silently disabled otherwise
- `max_file_chars` param clips output (default 200K, matches patch agent)
- Path traversal protection: `resolve().relative_to(repo_root)` check

### Implementation: `src/rag_baseline.py`
Changes:
- Added `GET_FILE_CONTENTS_TOOL_DECLARATION` constant
- `RAGAgent.__init__`: added `repo_dir`, `symmetric_tools`, `max_file_chars` params
- `find_relevant_files`: tool declarations are dynamic (1 or 2 tools)
- Function-call dispatch loop: early-exit for `fc.name == "get_file_contents"` before
  the search_codebase path. Counts against `max_tool_calls_per_turn`.
- Added `_handle_get_file_contents(path, observed_files)`: reads file, clips, records
  to observed_files for final answer inclusion.

### run_patch.py changes
- `_run_retrieval` signature: added `rag_symmetric_tools=False`, `repo_dir=None`,
  `patch_max_file_chars=200_000`
- Manifest flag `rag_symmetric_tools` read from manifest (default False)
- Both `_run_retrieval` call sites updated to pass these params
- `rag_progressive` RAGAgent construction now passes all three params

### Tests: `tests/test_rag_symmetric_tools.py` (9 new tests)
All pass. Coverage:
- symmetric_tools=False by default (backward compat)
- symmetric_tools gracefully disabled when repo_dir=None
- symmetric_tools=True when repo_dir provided
- File contents returned correctly
- Error string for nonexistent file (no crash)
- max_file_chars clipping + truncation marker
- File added to observed_files on successful read
- Path traversal blocked

---

## Step 3: V2 Patching Manifests

### Implementation: `tools/generate_v2_verified_manifests.py`

Generates per-repo manifests for all 500 SWE-bench Verified instances.
Design: per-repo structure (same as N=100), not multi-repo single file.
Rationale: run_patch.py is single-repo-per-manifest; cross-repo support
would require pipeline changes not in Phase 3 scope.

### Output: `patch_manifests/v2_verified/`
- **3 pilot manifests** (psf/requests, 8 instances each):
  - `pilot_oracle_v1.yaml`
  - `pilot_gm_progressive_v1.yaml`
  - `pilot_bm25_v1.yaml`
- **48 full manifests** (12 repos × 4 methods):
  - Methods: oracle, gm_progressive, bm25, agentic_cold_start
- **Ledger**: `manifest_ledger_v2.json`

### V2 settings vs V1
| Setting | V1 | V2 |
|---------|----|----|
| instance_wall_clock_cap_s | 480 | 600 |
| rate_limit_max_retries | 2 | 3 |
| patch_repair_samples | (implicit 1) | explicit 1 |
| rag_symmetric_tools | (n/a) | false (default) |

### Dataset composition (Verified, 500 instances)
| Repo | Count |
|------|-------|
| django/django | 231 |
| sympy/sympy | 75 |
| sphinx-doc/sphinx | 44 |
| scikit-learn/scikit-learn | 32 |
| matplotlib/matplotlib | 34 |
| pytest-dev/pytest | 19 |
| astropy/astropy | 22 |
| pydata/xarray | 22 |
| pylint-dev/pylint | 10 |
| psf/requests | 8 |
| pallets/flask | 1 |
| mwaskom/seaborn | 2 |

---

## Test Results

```
182 tests total (was 173 at start of session).
All pass.
+12 BM25 tests (tests/test_bm25_baseline.py)
+9 symmetric tools tests (tests/test_rag_symmetric_tools.py)
+1 existing test updated (test_validate_commit_context_passes_on_valid_context)
```

## Follow-up (Phase 3 Step 4)

Run pilot manifests and validate gates before expanding to full 500-instance run.
See CURRENT_STATE.md → V2 AGENDA → Phase 3 for pilot commands and validation gates.

DO NOT run full manifests until pilot validation passes.
