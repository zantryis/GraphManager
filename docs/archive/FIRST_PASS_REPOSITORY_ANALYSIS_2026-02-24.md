# GraphManager First-Pass Repository Analysis (Current Runnable State)

Date: 2026-02-24
Scope anchor: current runnable repository state (code + tests + manifests + state/docs)

## 1) Problem Being Solved

GraphManager targets cost-efficient software issue resolution by reusing a structural codebase world model (AST graph + graph index) across issues, instead of rebuilding dense retrieval context for each task.

- Primary thesis (paper framing): cost efficiency with retrieval quality parity, not quality superiority.
- Operational decomposition in repo: retrieval stage (graph/RAG/BM25/deterministic baselines) feeding a patch generation stage with optional harness evaluation.

Evidence:
- `CURRENT_STATE.md` (project goal and thesis block)
- `RESEARCH_INTENT.md:55-57`
- `README.md:3-14`

## 2) Current Architecture and Functional Map

Core pipeline surfaces:

1. Retrieval experiments:
- Entrypoints: `run_experiment.py`, `run_suite.py`
- Orchestration + scoring: `src/evaluation.py`
- Retrieval methods: `src/manager_agent.py`, `src/rag_baseline.py`, `src/deterministic_retrieval.py`, `src/bm25_baseline.py`
- Graph construction/indexing: `src/graph_builder.py`

2. Patching pipeline:
- Entrypoint: `run_patch.py`
- Patch generation: `src/patch_agent.py`
- Dataset normalization: `src/datasets/adapters.py`

3. Reporting/artifacts:
- Analysis scripts + paper artifacts under `tools/` and `research_report/`

Observed runtime posture:
- Unit test baseline is healthy (`182` tests passing via `./.venv/bin/python -m unittest discover -s tests -v`).
- No evidence of end-to-end harness integration tests in `tests/`.

## 3) Academic Rigor Assessment

### Strengths

- Strong local unit-test density around critical utility logic (retry policy, schema handling, deterministic retrieval, manifest constraints, path canonicalization).
- Explicit claims-discipline docs (`RESEARCH_INTENT.md`, `CLAIMS_LOCK.md`, `docs/RIGOR_CHECKLIST.md`).
- Clear strict vs same-snapshot track distinction in evaluation logic (`src/evaluation.py`).

### Weaknesses (severity-ranked findings below)

- Several active claim-to-implementation mismatches materially affect interpretability.
- Documentation and protocol drift (V1/V2 mixed state) increases risk of running wrong experiments.
- Missing reproducibility hardening in dependency and dataset failure behavior.

## 4) Production-Grade Readiness Assessment

### Strengths

- Retry/backoff and per-instance timeout controls in patching path.
- Checkpoint/resume semantics and robust per-instance accounting.
- Method-scoped setup accounting and structured summaries.

### Weaknesses

- Security boundary issue in patch file reading path.
- CLI contract vs behavior mismatch for worker parallelism.
- Runtime failure edge in retrieval runner under method subsets.
- Sparse integration-level verification (API/harness/dataset pinning).

## 5) Methodology / Clarity / Evaluation / Documentation Gaps

## 6) Vulnerabilities, Edge Cases, Architectural Weaknesses

The following findings are ordered by severity.

### Critical

1. `agentic_cold_start` baseline is not actually implemented as agentic.
- What is wrong:
  - Research intent defines `agentic_cold_start` as an agent with file tools and no index.
  - V2 manifest generation maps `agentic_cold_start` to retrieval method `none`.
  - `none` path returns empty retrieval output and no retrieval tools; patch stage receives zero files.
- Why it matters:
  - Invalidates the intended baseline semantics for V2 claims and can materially distort comparative conclusions.
- Evidence:
  - `RESEARCH_INTENT.md:23-24`
  - `tools/generate_v2_verified_manifests.py:60-66`
  - `run_patch.py:180-187`
  - `src/patch_agent.py:123-127`
- Recommended mitigation:
  - Add a true `agentic_cold_start` mode (patch agent with bounded file tools and explicit accounting), keep `none` as a separate empty-context control.

2. Scope contract contradiction on retrieval vs patching populations.
- What is wrong:
  - Intent states retrieval and patching should run on the same repos.
  - Current state records retrieval on Flask/Requests/Pytest but patching on full Verified multi-repo set.
- Why it matters:
  - Weakens causal interpretation between retrieval quality and end-to-end patch outcomes.
- Evidence:
  - `RESEARCH_INTENT.md:25`
  - `CURRENT_STATE.md:336-337`
- Recommended mitigation:
  - Declare one authoritative V2 evaluation population policy and enforce it in manifests + reporting scripts.

3. Patch file-read path can traverse outside repo root.
- What is wrong:
  - `PatchAgent._read_file` joins `repo_dir / rel_path` without verifying path containment.
  - Oracle retrieval path returns normalized issue/patch paths without canonical validation against repo file set.
- Why it matters:
  - Security and data-leak risk (local file disclosure into model prompts), and possible contamination of patch generation context.
- Evidence:
  - `src/patch_agent.py:154-157`
  - `run_patch.py:189-196`
- Recommended mitigation:
  - Apply `resolve()+relative_to(repo_root)` containment check in patch file reading, and canonicalize oracle file list against valid in-repo paths.

### High

4. BM25 dependency used but not declared in `requirements.txt`.
- What is wrong:
  - Code imports `rank_bm25`, but requirements omit it.
- Why it matters:
  - Fresh environment setup can fail at runtime for BM25-enabled flows, harming reproducibility.
- Evidence:
  - `src/bm25_baseline.py:25`
  - `requirements.txt:1-12`
- Recommended mitigation:
  - Add `rank_bm25` to requirements and validate environment bootstrap in CI.

5. `run_experiment` can fail when graph methods are excluded.
- What is wrong:
  - Results finalization always copies `graph.json`, but this file is only produced when graph build runs.
  - Method subsets like `--methods bm25` can skip graph build and trigger `FileNotFoundError`.
- Why it matters:
  - Breaks advertised method-subset execution and impacts experiment automation reliability.
- Evidence:
  - `src/evaluation.py:557-570`
  - `src/evaluation.py:944-951`
- Recommended mitigation:
  - Guard graph copy operations on file existence, or emit modality-specific artifacts.

6. Protocol/document drift likely to cause wrong commands and interpretation.
- What is wrong:
  - V2 handoff document references pilot manifest names that do not exist (`pilot_gm_v1.yaml`) and states 10-instance requests pilot while Verified has 8.
- Why it matters:
  - High operator error risk for study execution and reproducibility.
- Evidence:
  - `v2_phase3_handoff.md:127-130`
  - `v2_phase3_handoff.md:169`
  - `v2_phase3_handoff.md:147`
  - `tools/generate_v2_verified_manifests.py:159`
  - `tools/generate_v2_verified_manifests.py:40`
- Recommended mitigation:
  - Freeze one authoritative execution doc generated from manifest ledger metadata.

7. README has stale claims that now conflict with implemented code.
- What is wrong:
  - README says no BM25 baseline and tool asymmetry remain, while code now includes BM25 and optional symmetric RAG file tool.
  - README references an `education/` directory that is absent.
- Why it matters:
  - External readers may draw incorrect conclusions about experimental rigor and current capabilities.
- Evidence:
  - `README.md:184`
  - `README.md:203-206`
  - `src/bm25_baseline.py:1-18`
  - `src/rag_baseline.py:62-75`
- Recommended mitigation:
  - Update README limitations and project structure to match actual runnable state.

### Medium

8. Dataset loading silently suppresses split-level failures.
- What is wrong:
  - Adapter swallows all exceptions while loading dataset splits and continues.
- Why it matters:
  - Can silently produce partial/biased issue sets if a split fails due to network/auth/schema change.
- Evidence:
  - `src/datasets/adapters.py:123-126`
  - `src/datasets/adapters.py:169-172`
- Recommended mitigation:
  - Log split failures explicitly and fail fast unless an explicit permissive mode is enabled.

9. CLI advertises worker parallelism that is currently disabled.
- What is wrong:
  - `--workers` help implies active parallel processing, but runtime falls back to sequential with warning.
- Why it matters:
  - Operational planning and cost/runtime expectations can be materially wrong.
- Evidence:
  - `run_patch.py:1657-1666`
  - `run_patch.py:1126-1150`
- Recommended mitigation:
  - Mark flag experimental/disabled in CLI help until engine is implemented, or implement the worker engine.

10. Model provenance metadata is partly hardcoded and not fully configuration-driven.
- What is wrong:
  - Retrieval summary metadata records `"model": "gemini-2.0-flash"` as a constant.
- Why it matters:
  - Weakens traceability if runtime model settings evolve; threatens paper reproducibility bookkeeping.
- Evidence:
  - `src/evaluation.py:521`
  - `src/evaluation.py:923`
- Recommended mitigation:
  - Thread explicit model identifiers through CLI/config and persist them in run metadata.

11. Intent doc references a missing path for V2 plan.
- What is wrong:
  - `RESEARCH_INTENT.md` points to `education/v2_next_session_plan.md`, but current repo path is `v2_next_session_plan.md`.
- Why it matters:
  - Increases onboarding friction and risk of following stale instructions.
- Evidence:
  - `RESEARCH_INTENT.md:15`
- Recommended mitigation:
  - Correct path and add a doc consistency check in CI/lint.

### Low

12. Mixed-era state narrative increases cognitive overhead.
- What is wrong:
  - `CURRENT_STATE.md` combines frozen V1 artifacts, V2 agenda, and historical notes in one long operational file.
- Why it matters:
  - Harder to identify authoritative next actions quickly.
- Evidence:
  - `CURRENT_STATE.md:307-410`
- Recommended mitigation:
  - Split into concise “Current Execution State” and “Historical Archive Notes”.

## 7) Prioritized Remediation Backlog (P0/P1/P2)

### P0 (blockers for credible V2 execution)

1. Implement true `agentic_cold_start` baseline and separate it from `none`.
2. Fix patch file path containment + oracle path canonicalization.
3. Resolve retrieval/patch population policy conflict and enforce single policy in manifests/reporting.
4. Fix method-subset artifact writing bug in `run_experiment`.

### P1 (high-impact rigor/reproducibility)

1. Add `rank_bm25` to pinned dependencies and verify bootstrap path.
2. Remove stale/incorrect run commands and claims from README + handoff docs.
3. Make dataset adapter split failures explicit and observable.
4. Align `--workers` CLI contract with actual implementation state.

### P2 (hardening and maintainability)

1. Add integration tests for:
   - patch stage + harness interface,
   - dataset/split/version pinning behavior,
   - adversarial patch-path inputs.
2. Improve model provenance capture in run summaries.
3. Reduce state-document drift via a generated status index.

## Public API / Interface / Types Coherence Audit (Requested)

CLI interfaces:
- `run_experiment.py`: rich and configurable; subset-method run has artifact edge-case bug.
- `run_patch.py`: interface is broad; worker-parallel contract currently aspirational.
- `run_suite.py`: good config-driven orchestration; limited explicit method subset exposure at CLI level.

Manifest contracts:
- V1 and V2 manifests coexist; V2 generator is deterministic and ledgered.
- Method taxonomy (`agentic_cold_start -> none`) currently encodes a semantic mismatch.

Retrieval taxonomy:
- Implemented: `gm_*`, `rag_*`, `raw_rag_*`, `bm25`, `none`, `oracle`.
- Intended-doc taxonomy diverges on “agentic cold start”.

Summary/report schema:
- Retrieval summary schema is detailed and useful.
- Patch summary includes dual accounting fields; claims-doc acknowledges design-vs-as-run accounting caveat.

## Test Coverage and Missing Scenarios (Requested)

Validated baseline:
- Full suite passing: `182` tests.

Coverage concentration is strong on:
- Retrieval/pipeline helper logic,
- deterministic ranking/tuning,
- patch retries/checkpointing,
- manifest invariants and path canonicalization.

Missing scenario classes:
1. End-to-end API + harness integration tests (real or high-fidelity contract tests).
2. Dataset version pinning / split availability regression tests.
3. Adversarial patch-path safety tests for patch file loading.
4. Provenance consistency tests tying configured model IDs to summary metadata.

## Assumptions Used

- Existing uncommitted workspace changes are intentional and in scope.
- No external reruns were required for this first-pass critique.
- Where docs and code conflict, code path was treated as ground truth.
