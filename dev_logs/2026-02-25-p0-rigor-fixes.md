# P0 Bug Fixes from External Rigor Audit

**Date:** 2026-02-25
**Session:** P0 code bug fixes (retrieval eval fairness + temperature parity)
**Tests before:** 288 | **Tests after:** 291 (3 new)

---

## Context

External reviewer performed a full scientific rigor audit and identified 3 P0 code bugs
in the retrieval evaluation pipeline that would bias the retrieval comparison between methods.
Fixes applied before any V2 retrieval (T0) data was written to disk. T1 patching pipeline
was separately confirmed correct and unaffected.

---

## Bug 1 — Model mismatch in retrieval eval

**File:** `src/evaluation.py`
**Severity:** HIGH (confounds retrieval F1 comparison across methods)

`ManagerAgent` and `RAGAgent` were instantiated without `model=model_name`, so they silently
fell back to their class default (`gemini-2.0-flash`). Meanwhile `AgentlessLikeLocalizer`
and `AgenticColdStartAgent` correctly received `model=model_name` (`gemini-3-flash-preview`).
Result: 4 methods used one model, 2 used another — in the same experiment.

**Fix:** Extracted agent construction into `_build_agentic_methods()` helper. Both
`ManagerAgent` and `RAGAgent` now receive `model=model_name`.

---

## Bug 2 — RAG missing symmetric tools in retrieval eval

**File:** `src/evaluation.py`
**Severity:** HIGH (biases retrieval F1 in GM's favour)

`rag_progressive` and `rag_baseline` were instantiated without `symmetric_tools=True`
or `repo_dir`. This gave RAG agents 1 tool (search) vs GM's 3 tools (search + neighbors +
file summary). The V2 design explicitly intended tool symmetry (STATE.md line 29), and the
patching pipeline (`run_patch.py`) was already correct — only the retrieval eval was missing it.

**Fix:** `_build_agentic_methods()` now passes `symmetric_tools=True, repo_dir=repo_dir`
to both `rag_progressive` and `rag_baseline`.

---

## Bug 3 — Missing temperature=0.0 in agentless_like LLM calls

**File:** `src/agentless_like_localization.py`
**Severity:** HIGH (non-deterministic vs deterministic for all other methods)

All other agentic methods (ManagerAgent, RAGAgent) explicitly set `temperature=0.0`.
`AgentlessLikeLocalizer` made 3 `generate_content` calls with no temperature config,
defaulting to the Gemini API default (~1.0). This made agentless_like non-deterministic
while all other methods were deterministic.

**Fix:** Added `from google.genai import types as _genai_types` and a module-level
`_TEMPERATURE_ZERO = _genai_types.GenerateContentConfig(temperature=0.0)` constant.
All 3 `generate_content` calls now pass `config=_TEMPERATURE_ZERO`.

---

## Data Impact

No data corruption. All fixes applied before any affected data was written:
- T0 retrieval eval: not yet started
- T1 agentless_like manifests: had not yet been dispatched by the pool

Currently running T1 methods (agentic_cold_start, bm25, oracle, rag_progressive)
were never affected — patching pipeline was already correct.

---

## Outstanding gaps (from audit, NOT fixed this session)

See STATE.md known issues I7–I17 and TASKS.md T12–T16 for tracking:

| Priority | Gap |
|----------|-----|
| P1 | Bootstrap CIs: must resample per-issue deltas, not run means (I7, T13) |
| P1 | McNemar: non-functional stub, needs T2 data + Holm-Bonferroni (I8/I9, T14) |
| P1 | Binomial CIs on patching resolve rates (I10, T15) |
| P1 | Missing bib entries: `aider2023`, `lv2011lower` block LaTeX compilation (I11, T12) |
| P2 | Agentless-like graph augmentation disclosure in §4 + §7 (I12) |
| P2 | repomap_like: PageRank baseline, not Aider repo map (I13) |
| P2 | Threats to Validity section (I12–I16, T16) |
| P2 | Data availability statement (I16) |
