# CURRENT STATE
<!-- Every agent reads this first. Every agent updates it last. -->
<!-- Keep it short. Detailed reasoning lives in dev_logs/. -->

Last updated: 2026-02-18
Last agent: Claude Sonnet 4.6 (post-Phase-0/1 review)

---

## Project Goal

**Paper 1 (current):** Show that a graph-based world model reduces total token
cost for software issue resolution while maintaining competitive pass@1.

**Thesis in one sentence:** GraphManager amortizes codebase exploration across
tasks; the same graph index serves many issues cheaply, whereas RAG rebuilds
an expensive embedding index per snapshot.

This is NOT a "graph beats RAG" quality paper. It is a cost-efficiency paper
with quality parity as a secondary claim.

---

## Workstreams (keep them separate — different files, different agents)

### Workstream A — Retrieval evaluation [DONE, needs gm_deterministic]
**Owner files:** `src/evaluation.py`, `src/manager_agent.py`, `src/rag_baseline.py`,
`src/graph_builder.py`, `src/deterministic_retrieval.py`, `run_experiment.py`,
`run_suite.py`, `experiments_matrix_v2.yaml`, `visualize_results.py`

**Status:**
- 11 valid cells: Flask, Requests, Pytest × gm_progressive/gm_baseline/rag_progressive/rag_baseline × strict+same-snapshot
- raw_rag_function and raw_rag_fixed complete on 3 repos
- langchain excluded (valid:false, wrong source_prefix)
- **MISSING: gm_deterministic — all 7 cells pending. This is the most important gap.**
- FastAPI, Keras cells: not started

**Next action for this workstream:**
Run gm_deterministic on Flask, Requests, Pytest using existing manifests.
Command: `./.venv/bin/python run_experiment.py --method gm_deterministic ...`

---

### Workstream B — Patching pipeline [BLOCKED on B1]
**Owner files:** `run_patch.py`, `src/patch_agent.py`, `patch_manifests/`

**Phase 0/1 completed (commit 8dae81f, 2026-02-18):**
- MAX_TOKENS fixed: raising patch_max_output_tokens to 12288 resolved truncation ✓
- Apply check + repair loop: validated; retries now bounded (max 2 repair, max 1 retrieval) ✓
- Harness capture: now works; n_resolved populates correctly ✓
- Manager termination: now returns confirmed_files at stagnation/budget instead of [] ✓
- 104 unit tests passing ✓

**Latest run (20260218_133013, gm_progressive, 8 instances):**
- apply_success_rate=0.25 (2/8 patched), n_resolved=0/8
- All 8 retrieval stop at "budget" (confirmed_files fallback, not max_turns)
- 6/8 fail all repair retries (repair_retries_used=4, apply_failures=6)

**REMAINING CRITICAL BUG:**
- **BUG 1 (CRITICAL): Wrong base_commit.** `run_patch.py:587` uses
  `repo_issues[0].get("base_commit")` for ALL issues. All 8 instances have
  different base_commits; 7/8 checkout at the wrong commit → wrong file content
  → context mismatch → patches fail git apply. This is almost certainly the
  root cause of the 75% apply failure rate and 0/8 resolved.
  Fix: move per-issue checkout inside the issue loop.

**Next action for this workstream:**
1. Fix Bug 1 (base_commit). One-line change + move checkout into issue loop.
2. Run clean 8-instance run with `--evaluate` to get true baseline.
3. Run oracle (gold files → PatchAgent) to establish model ceiling.
4. Expand to 30 instances (10 per repo: Flask, Requests, Pytest) with
   3 methods (cold-start, rag_progressive, gm_progressive) + --evaluate.

---

### Workstream C — Paper writing [BLOCKED on B results]
**Owner files:** `research_report/sections/`, `research_report/main.tex`

**Status:**
- Introduction, method, related work, threats: drafted
- Results section: retrieval tables filled for 3 repos; patching section empty
- gm_deterministic rows all say "pending" in Table 1

**Next action for this workstream:**
Wait for Workstream B to produce clean patching numbers.
Meanwhile: fill gm_deterministic results once Workstream A runs them.

---

## Known Bugs (do not close until verified fixed)

| ID | Severity | Description | File | Fixed? |
|----|----------|-------------|------|--------|
| B1 | CRITICAL | Wrong base_commit: uses repo_issues[0] for all | run_patch.py:587 | NO |
| B2 | CRITICAL | Thinking budget exhaustion on Gemini 2.5 | patch_agent.py | YES (raised max_output_tokens to 12288) |
| B3 | HIGH | Manager never terminates naturally (max_turns every time) | manager_agent.py | YES (budget fallback to confirmed_files) |
| B4 | HIGH | New retry/apply-check code never executed | run_patch.py | YES (verified in run 20260218_133013) |
| B5 | MEDIUM | redact_paths removes file hints in patching context | run_patch.py:128 | NO |
| B6 | LOW | Cold-start (retrieval_method: none) crashes with ValueError | run_patch.py:171 | NO |

Full details: `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md`

---

## Target Experiment Set for Paper

### Retrieval (already have, need gm_deterministic)
- 6 methods × 3 repos (Flask, Requests, Pytest) × n=10 × 3 repeats ✓
- gm_deterministic × 3 repos × n=10 × 3 repeats ✗ (missing)

### Patching pilot (need clean runs)
- 3 methods: cold-start, rag_progressive, gm_progressive
- 3 repos: psf/requests (~10 instances each from SWE-bench Verified),
  pallets/flask (~10), pytest-dev/pytest (~10)
- Total: ~30 instances per method, single run each
- Required: oracle run first (gold files → patch agent) to establish ceiling

### Minimum for paper submission
- Retrieval: current 3 repos + gm_deterministic → complete
- Patching: 3 methods × 30 instances (across 3 repos) → directional pilot

---

## What NOT to do

- Do not start MAS orchestration or worker agent work (Paper 2)
- Do not expand patching to >30 instances until 8-instance pilot is clean
- Do not touch retrieval eval code while patching work is in progress
- Do not re-run retrieval experiments that already have valid cells
- Do not commit *_repo/ directories (gitignored)
- Do not commit results/ directory (gitignored)

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md` | All 10 known bugs |
| `dev_logs/2026-02-18-end-to-end-improvement-plan.md` | Phased fix plan |
| `dev_logs/2026-02-18-patch-run-handoff.md` | Patching pipeline overview |
| `dev_logs/2026-02-18-phase0-1-patch-robustness-harness-fix.md` | Phase 0/1 work log |
| `results/patch_runs/20260218_133013/patch_summary.json` | Latest run (apply=25%, resolved=0) |
| `EVALUATION_SPEC.md` | Metrics, protocols, statistical methods |
| `AGENTS.md` | Repo-level agent instructions |
| `patch_manifests/swebench_verified_requests_v1.yaml` | 8-instance manifest |
| `results/clean_eval_20260211_201431/` | Valid retrieval results (frozen) |
| `research_report/artifacts/frozen-20260212-matrix-v2-clean/` | Frozen artifact bundle |
