# 2026-02-22 — Paper Rewrite: Two-Column Format + Figures + Vulnerability Fix

## Context

Continuation from 2026-02-22 reruns-complete session. All patching pilot numbers locked
(43%/38%, 4.4×, McNemar p=0.38). User requested paper rewrite with two-column format
and useful visuals. Plan approved and executed.

## Work Completed

### Phase 1: compute_metrics vulnerability fix (TDD)

**Problem**: `compute_metrics([], [])` returned `{"f1": 1.0}` — silently inflating mean
F1 when any instance has an empty gold list due to data-loading error.

**Fix applied**:
- `src/evaluation.py:83-90`: Empty gold guard now returns
  `{"precision": 0.0, "recall": 0.0, "f1": 0.0, "skipped_empty_gold": True}`
- `tests/test_evaluation_logic.py`: Added 4 new tests covering empty gold, empty predicted,
  exact match, and nonempty-predicted/empty-gold cases.
- Test suite: 143 tests, all pass (was 139 before this fix).

**TDD order**: failing test → fix → full suite pass. No regressions.

### Phase 2: Pending retrieval experiments (background, in progress)

Launched sequential background script `/tmp/run_pending_retrieval.sh` for:
- `tiangolo/fastapi` (SWE-bench, n=10, strict + same-snapshot)
- `yt-dlp/yt-dlp` (SWE-PolyBench, n=5, strict + same-snapshot)
- `langchain-ai/langchain` (SWE-PolyBench, n=10, strict + same-snapshot)
- `keras-team/keras` (SWE-PolyBench, n=10, strict + same-snapshot)

Parameters: manager_max_turns=4, rag_max_turns=4, seed=17, single repeat.
Matches matrix_v2 defaults for consistency with Flask/Requests/Pytest runs.

FastAPI strict completed: `results/runs/20260222_031854/`
  - GM-prog: F1=0.463, RAG-prog: F1=0.445
  - GM-det: F1=0.382, Setup=9,757 tokens

Remaining runs in progress (yt-dlp started at time of log write).

### Phase 3a: Two-column arXiv format

**main.tex changes**:
- `\documentclass[10pt,twocolumn]{article}` (was `11pt,article`)
- `\usepackage[margin=0.75in,top=0.9in]{geometry}` (was `margin=1in`)
- Added: `\usepackage{balance}`, `\usepackage[protrusion=true,expansion=true]{microtype}`
- Added: `\graphicspath{{figures/}}`
- Added: `\balance` before bibliography

**Wide tables converted to `table*`** (span both columns):
- `tab:main_results` (7 cols) — 03_method.tex was already set; 05_results.tex ✓
- `tab:methods` (5 cols) — 03_method.tex ✓
- `tab:repos` (5 cols) — 04_experimental_setup.tex ✓
- `tab:strict_requests` (5 cols) — 05_results.tex ✓
- `tab:amortization` (5 cols) — 05_results.tex ✓
- `tab:cost_cross_repo` (4 cols) — 05_results.tex ✓
- `tab:patching_resolved` (4 cols) — 05_results.tex ✓
- `tab:patching_cpr` (complex multi-col) — 05_results.tex ✓

**Overfull hbox fixes**:
- `eq:deterministic_score`: converted `equation` → `multline` to break wide formula
- `09_appendix.tex`: replaced SHA verbatim block with inline text
- `04_experimental_setup.tex`: shortened manifest ID example, replaced verbatim command
- `microtype` resolved most paragraph-level overfull issues

**Result**: 13 pages (before figures), clean compile, no hbox overflows.

### Phase 3b: 4 matplotlib figures

**Scripts** in `research_report/figures/`:
- `fig_resolved_rates.py` → `fig_resolved_rates.pdf` (grouped hbar, patching resolved rates)
- `fig_cpr_comparison.py` → `fig_cpr_comparison.pdf` (log-scale CPR bars, 4.4× arrow)
- `fig_retrieval_f1_cost.py` → `fig_retrieval_f1_cost.pdf` (F1 vs cost scatter, 7 methods)
- `fig_amortization.py` → `fig_amortization.pdf` (strict vs same-snapshot cost+F1)

Data sources: all figures use only locked published values (no raw result parsing).
matplotlib installed to project venv.

### Phase 3c: Paper content updates

**05_results.tex**:
- Figures inserted: Fig 1 (resolved rates) after patching table, Fig 2 (CPR) after CPR table,
  Fig 3 (F1 vs cost scatter) before cost analysis paragraph, Fig 4 (amortization) before cost section.
- `figure*` used for wide figures (1, 3); `figure` for single-column (2, 4).
- Cross-benchmark section left for update after Phase 2 completes.

**06_discussion.tex**:
- Patching pilot numbers corrected: 42%→43%, 33%→38%, 490K→479K, 2.4M→2.1M
- "Reruns in progress" → "reruns complete"
- McNemar p=0.38 added to patching paragraph
- Figure references added: Fig 3 in cost-frontier paragraph, Fig 4 in amortization paragraph,
  Figs 1/2 in patching findings paragraph

### Phase 4: Verification

- All 143 tests pass ✓
- CLAIMS_LOCK audit: all 5 claims use permitted framing ✓
- Paper compiles: 15 pages, 508 KB ✓ (includes figures)
- Only 1.5pt overfull vbox (benign float size) ✓
- Numbers spot-check: abstract/conclusion/discussion all consistent with locked pilot numbers ✓

## Remaining Work

- Phase 3c-ii: Update Table 3 (tab:main_results) once Phase 2 runs complete.
  FastAPI data available now; yt-dlp, langchain, keras pending.
- Update 05_results.tex cross-benchmark section to replace stale yt-dlp partial data.
- Final compile after Table 3 update.

## Files Changed

| File | Change |
|------|--------|
| `src/evaluation.py` | Empty-gold guard in compute_metrics |
| `tests/test_evaluation_logic.py` | +4 compute_metrics tests |
| `research_report/main.tex` | Two-column, microtype, graphicspath, balance |
| `research_report/sections/03_method.tex` | table→table*, multline eq |
| `research_report/sections/04_experimental_setup.tex` | table→table*, verbatim cleanup |
| `research_report/sections/05_results.tex` | All tables→table*, 4 figure inserts |
| `research_report/sections/06_discussion.tex` | Number corrections + figure refs |
| `research_report/sections/09_appendix.tex` | SHA verbatim → inline text |
| `research_report/figures/*.py` | New: 4 figure scripts |
| `research_report/figures/*.pdf` | New: 4 generated figures |
