# 2026-02-22 - Targeted Reruns Complete + Final Number Lock

## Context

Continuation from 2026-02-21 session. All 6 targeted reruns (sympy/sphinx/matplotlib × GM+RAG)
completed. matplotlib RAG required a harness retry due to WSL2 Docker vsock errors.
Final analysis run and paper updated with locked numbers.

## Run Completions

| Run | Method | Repo | Run ID | Resolved |
|-----|--------|------|--------|----------|
| 1/6 | gm_progressive | sympy | 20260221_111111 | 6/12 |
| 2/6 | rag_progressive | sympy | 20260221_123817 | 5/12 |
| 3/6 | gm_progressive | sphinx | 20260221_141004 | 2/12 |
| 4/6 | rag_progressive | sphinx | 20260221_153148 | 3/12 |
| 5/6 | gm_progressive | matplotlib | 20260221_165614 | 3/12 |
| 6/6 | rag_progressive | matplotlib | 20260221_202646 | 1/12* |

*matplotlib RAG: primary harness had 4 Docker vsock errors. Harness retry
(`graphmanager_rerun_mpl_rag_errors`) confirmed 1 resolved: `matplotlib__matplotlib-22719`.
`matplotlib__matplotlib-24870` failed patch apply in container (context mismatch between
agent's base_commit view and container environment) — counted unresolved.
`patch_summary.json` corrected to n_resolved=1 with audit note.

## FROZEN_RUN_IDS Updated

Updated `tools/analyze_v4_handoff.py` FROZEN_RUN_IDS for 6 entries:
- matplotlib GM: 20260219_190403 → 20260221_165614
- matplotlib RAG: 20260220_094032 → 20260221_202646
- sphinx GM: 20260220_031810 → 20260221_141004
- sphinx RAG: 20260220_171540 → 20260221_153148
- sympy GM: 20260220_043013 → 20260221_111111
- sympy RAG: 20260220_184427 → 20260221_123817

## Final Locked Numbers (N=100, 9 repos, 4 methods)

| Method | Resolved | Rate | CPR method-accounted | CPR as-run |
|--------|----------|------|----------------------|------------|
| oracle | 45/100 | 45% | 33,594 | 33,594 |
| gm_progressive | 43/100 | 43% | 479,354 | 1,250,676 |
| rag_progressive | 38/100 | 38% | 2,115,746 | 2,319,677 |
| none | 3/100 | 3% | 24,291 | 24,291 |

**CPR ratio method-accounted (RAG/GM): 4.41×**
**CPR ratio as-run (RAG/GM): 1.85×**
**McNemar exact p (GM vs RAG, two-sided): 0.383 — not significant**
**Discordant pairs: 21 (GM-only=13, RAG-only=8), timeout-confounded: 16/21**

## Paper Updates

- `05_results.tex`: patching resolved table final (removed $^*$ markers, updated sympy RAG 0.000→0.417, pooled GM 0.420→0.430, pooled RAG 0.330→0.380); CPR table updated (GM 42→43, RAG 33→38, new CPR values); key observations updated (4.9×→4.4×, 9pp→5pp, 17/23→16/21, McNemar p added).
- `00_abstract.tex`: 42%→43%, 4.9×→4.4×.
- `08_conclusion.tex`: same numbers updated; "reruns in progress" → "reruns complete"; stale "completing matrix" sentence removed.
- Paper compiled clean: 20 pages, 337 KB.

## Data Validity Assessment

- All 36 cells (9 repos × 4 methods) present with patch_summary.json.
- All manifest/run instance counts match (12/12 verified for 6 new reruns).
- B10 dual-build confound: 6 old frozen repos use proxy cost estimation; 6 new reruns use direct fields. Disclosed in paper.
- Single run per method, no CIs — correctly labeled exploratory throughout.
- matplotlib RAG harness correction documented in patch_summary.json with audit note.

## Known Remaining Issues

- Paper rewrite requested: two-column format, visuals, thorough claim verification.
