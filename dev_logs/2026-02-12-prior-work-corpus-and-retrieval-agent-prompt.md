# 2026-02-12 - Prior Work Corpus Curation And Retrieval Agent Prompt

## Context

- User requested adding the most relevant prior work into `previous_work/` with emphasis on borrowable retrieval ideas and research framing references.
- User also requested a concrete prompt for a new implementation agent focused on the deterministic retrieval redesign.

## Decision

- Curate a focused prior-work corpus under `previous_work/`:
  - key papers as local PDFs,
  - repository URL pointers for implementation references,
  - a concise index documenting "what to borrow" from each item.
- Add a dedicated implementation handoff prompt:
  - `NEXT_AGENT_PROMPT_RETRIEVAL.md`
  - scope: deterministic retriever implementation with strict TDD and reproducible comparison.

Scope boundary:
- no retrieval code implementation in this step,
- no benchmark reruns in this step.

## Alternatives Considered

1. Keep only links, no local PDFs.
- Tradeoff: lighter repo footprint, weaker offline usability.
2. Clone every related external repository.
- Tradeoff: richer code corpus, but high repo bloat and low signal-to-noise.
3. Curated hybrid (chosen): selective PDFs + URL pointers + one cloned core implementation.
- Tradeoff: practical depth without excessive sprawl.

## Evidence

- New index:
  - `previous_work/README.md`
- Added papers:
  - `previous_work/papers/2403.06095_RepoHyper.pdf`
  - `previous_work/papers/2406.07003_GraphCoder.pdf`
  - `previous_work/papers/2410.14684_RepoGraph.pdf`
  - `previous_work/papers/2507.14791_RepoScope.pdf`
  - `previous_work/papers/2310.06770_SWE-bench.pdf`
  - `previous_work/papers/2005.11401_RAG.pdf`
- Added repo pointers:
  - `previous_work/repos/FSoft-AI4Code_RepoHyper.url`
  - `previous_work/repos/ozyyshr_RepoGraph.url`
  - `previous_work/repos/princeton-nlp_SWE-bench.url`
  - `previous_work/repos/vitali87_code-graph-rag.url`
- Existing cloned reference:
  - `previous_work/vitali-code-graph-rag/`
- New implementation prompt:
  - `NEXT_AGENT_PROMPT_RETRIEVAL.md`

## Consequences

- Expected benefits:
  - faster onboarding for retrieval redesign work,
  - clearer synthesis positioning (borrow-first vs context references),
  - lower hallucination risk in future design decisions.
- Known risks:
  - larger repository size due paper PDFs and cloned external repository.
- Monitoring signals:
  - future retrieval implementation docs/tests should cite this curated corpus,
  - next agent should follow deterministic retrieval scope without prompt drift.

## Follow-up

1. Implement deterministic retriever module and wire into evaluation (`gm_deterministic`).
2. Add TDD-first ranking and budget-guard tests.
3. Run reproducible small-cell comparison and freeze tuned coefficients.
