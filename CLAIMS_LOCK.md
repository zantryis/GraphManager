# Claims Lock (Phase 4)

Status: Active for Paper 1 drafting. Last updated: 2026-02-25.

This file constrains claim strength and phrasing for the current evidence state.
It does not replace `RESEARCH_INTENT.md`; it operationalizes wording discipline
for report writing and handoff execution.

| Claim | Evidence | Permitted strength | Forbidden framing |
|---|---|---|---|
| GM setup cheaper than RAG | Retrieval eval (repeat sets, 3 repeats/cell) | Confirmatory | Do not extend to patching without dual-build disclosure |
| GM retrieval quality vs RAG | Retrieval F1 aggregates (strict + same-snapshot) | GM is competitive and often higher on observed F1; primary thesis remains cost-efficiency | Do not lead with quality-superiority thesis |
| GM resolves more issues under budget | N=100 patch runs (`gm_progressive` vs `rag_progressive`) | Directional / exploratory only | Do not use "significantly better" wording |
| GM design-cost per resolved issue | Method-accounted patch cost fields | Valid only with explicit dual-build disclosure footnote | Do not present as actual API spend without disclosure |
| Amortization widens cost gap | Same-snapshot retrieval track only | Confirmatory in retrieval section | Do not cite patching runs as amortization evidence |

## Required disclosure block (for patching cost tables)

1. Current frozen N=100 GM/RAG patch runs were produced with a dual-build path in
   `run_patch.py` (graph and rag indices both built for GM/RAG runs).
2. Report both views when cost is discussed:
   - method-accounted cost (design intent)
   - as-run-consumed reconstruction (analysis-side)
3. Keep rerun decisions analysis-gated (Phase 3), not default.
