# CURRENT STATE
<!-- Every agent reads this first. Every agent updates it last. -->
<!-- Keep it short. Detailed reasoning lives in dev_logs/. -->
<!--
RULES FOR AGENTS:
- You may update status, metrics, and next actions for your assigned workstream.
- You may append items to the Parking Lot section.
- You may NOT change a workstream status to [ACTIVE] — only the researcher does that.
- You may NOT create new workstreams — only the researcher does that.
- You may mark a workstream [DONE] if all its goals are verifiably met.
-->

Last updated: 2026-02-18
Last agent: Claude Sonnet 4.6 (restructure: add status tags + parking lot)

---

## Project Goal

**Paper 1 (current):** Show that a graph-based world model reduces total token
cost for software issue resolution while maintaining competitive pass@1.

**Thesis in one sentence:** GraphManager amortizes codebase exploration across
tasks; the same graph index serves many issues cheaply, whereas RAG rebuilds
an expensive embedding index per snapshot.

This is NOT a "graph beats RAG" quality paper. It is a cost-efficiency paper
with quality parity as a secondary claim.

See `RESEARCH_INTENT.md` for full paper scope and experiment design principles.

---

## Workstreams

### [ACTIVE] Workstream A — Retrieval evaluation
**Owner files:** `src/evaluation.py`, `src/manager_agent.py`, `src/rag_baseline.py`,
`src/graph_builder.py`, `src/deterministic_retrieval.py`, `run_experiment.py`,
`run_suite.py`, `experiments_matrix_v2.yaml`, `visualize_results.py`

**Status:**
- 11 valid cells: Flask, Requests, Pytest × gm_progressive/gm_baseline/rag_progressive/rag_baseline × strict+same-snapshot ✓
- raw_rag_function and raw_rag_fixed complete on 3 repos ✓
- langchain excluded (valid:false, wrong source_prefix)
- **MISSING: gm_deterministic — all 7 cells pending. Most important gap.**
- FastAPI, Keras cells: not started (not required for paper minimum)

**Next action:**
Run gm_deterministic on Flask, Requests, Pytest using existing manifests.
Command: `./.venv/bin/python run_experiment.py --method gm_deterministic ...`

---

### [ACTIVE] Workstream B — Patching pipeline
**Owner files:** `run_patch.py`, `src/patch_agent.py`, `patch_manifests/`

**All critical bugs closed (Phase 0/1, commit 8dae81f):**
- B1 (base_commit): fixed — `_checkout_issue_commit` uses per-issue base_commit ✓
- B2 (MAX_TOKENS): fixed — patch_max_output_tokens=12288 ✓
- B3 (manager termination): fixed — budget fallback to confirmed_files ✓
- B4 (retry code unvalidated): verified in run 20260218_133013 ✓
- 104 unit tests passing ✓

**Current manifest (swebench_verified_requests_v1.yaml) — fast iteration mode:**
- Zero-shot: patch_max_turns=1, repair_retries=0, retrieval_retry=0
- Backoff: initial=2s, max=10s, max_retries=1, cooldown=0

**Last run (20260218_133013):** apply=25%, resolved=0/8 — pre-fix baseline, not valid.
Need a clean run.

**Next actions (in order):**
1. Run 8-instance requests manifest with `--evaluate` → true apply/resolved baseline.
2. Run oracle (gold files → PatchAgent, no retrieval) → model ceiling.
3. Expand to 30 instances (10/repo: Flask, Requests, Pytest) with 3 methods
   (cold-start, rag_progressive, gm_progressive) + --evaluate.

---

### [ACTIVE] Workstream C — Paper writing
**Owner files:** `research_report/sections/`, `research_report/main.tex`

**Status:**
- Introduction, method, related work, threats: drafted ✓
- Results section: retrieval tables filled for 3 repos; patching section empty
- gm_deterministic rows: all "pending" in Table 1

**Next actions:**
- Fill gm_deterministic rows once Workstream A completes.
- Add patching pilot results section once Workstream B completes.

---

## Known Bugs

| ID | Severity | Description | Fixed? |
|----|----------|-------------|--------|
| B1 | CRITICAL | Wrong base_commit | YES — _checkout_issue_commit |
| B2 | CRITICAL | Thinking budget exhaustion (Gemini 2.5) | YES — max_output_tokens=12288 |
| B3 | HIGH | Manager never terminates naturally | YES — budget fallback |
| B4 | HIGH | New retry/apply-check code unvalidated | YES — verified run 20260218_133013 |
| B5 | MEDIUM | redact_paths removes file hints in patching | NO |
| B6 | LOW | Cold-start crashes with ValueError | NO |

Full details: `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md`

---

## Target Experiment Set (minimum for paper)

| Component | Target | Status |
|-----------|--------|--------|
| Retrieval: 6 methods × 3 repos × n=10 × 3 repeats | Flask, Requests, Pytest | ✓ done |
| Retrieval: gm_deterministic × 3 repos | Flask, Requests, Pytest | ✗ pending |
| Patching: oracle × 8 instances | psf/requests | ✗ pending |
| Patching: 3 methods × 30 instances across 3 repos | requests+flask+pytest | ✗ pending |

---

## What NOT to do

- Do not start MAS orchestration (Paper 2 — see RESEARCH_INTENT.md)
- Do not expand patching beyond 30 instances until pilot is validated
- Do not touch Workstream A files while working on B, or vice versa
- Do not re-run retrieval cells that already have valid results
- Do not commit `*_repo/` or `results/` directories (gitignored)
- Do not promote Parking Lot items to [ACTIVE] workstreams — researcher does this

---

## Parking Lot
<!-- Agents: append observations and proposed tasks here. Do NOT self-promote to ACTIVE. -->
<!-- Researcher: review this section and promote/discard items each session. -->

*(empty)*

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `RESEARCH_INTENT.md` | Paper scope, claims, experiment design principles |
| `CLAUDE.md` | Full dev policy (TDD, commits, scope rules) |
| `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md` | All 10 known bugs |
| `dev_logs/2026-02-18-end-to-end-improvement-plan.md` | Phased fix plan |
| `dev_logs/2026-02-18-phase0-1-patch-robustness-harness-fix.md` | Phase 0/1 work log |
| `results/patch_runs/20260218_133013/patch_summary.json` | Latest patch run (apply=25%, resolved=0) |
| `EVALUATION_SPEC.md` | Metrics, protocols, statistical methods |
| `patch_manifests/swebench_verified_requests_v1.yaml` | 8-instance requests manifest |
| `results/clean_eval_20260211_201431/` | Valid retrieval results (frozen) |
| `research_report/artifacts/frozen-20260212-matrix-v2-clean/` | Frozen artifact bundle |
