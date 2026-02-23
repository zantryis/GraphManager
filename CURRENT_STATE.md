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

Last updated: 2026-02-22
Last agent: Claude Sonnet 4.6 (paper complete — all retrieval cells filled)

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

## Handoff Protocol (v4, Approved)

This repo is now staged for a **phase-gated handoff**. Use this protocol as the
authoritative execution order for Workstream B/C until researcher sign-off changes it.

### Preflight (must hold before execution)

- [x] Existing N=100 run IDs are treated as frozen evidence artifacts.
- [x] Rerun policy is analysis-gated (no default pilot rerun).
- [x] Claims lock is externalized to `CLAIMS_LOCK.md` (no edits to `RESEARCH_INTENT.md`).

### Phase checklist

- [x] **Phase 0 (doc freeze):** dual-build truth logged; state doc updated; no code changes.
- [x] **Phase 1 (pipeline fix, TDD):** split index build path + schema extension (backward compatible) + full tests.
- [x] **Phase 2 (data completion):** `none` baseline complete across 9 repos with completion markers.
- [x] **Phase 3 (analysis gate):** 4-method table, pooled CPR, dual accounting table, timeout sensitivity, paired McNemar, discordant analysis, rerun decision.
- [x] **Phase 4 (claims lock use):** claims language constrained by `CLAIMS_LOCK.md`.
- [x] **Phase 5 (final handoff pack):** state file + handoff log populated with phase-3 outputs and rerun decision.

### Frozen N=100 patch run set (for Phase 3 analysis)

Explicit repo → run_id mapping (verified against `patch_summary.json` manifests 2026-02-21):

| repo | oracle | gm_progressive | rag_progressive | none |
|------|--------|----------------|-----------------|------|
| astropy/astropy | `20260218_223151` | `20260219_172533` | `20260220_061030` | `20260220_234209` ✓ |
| matplotlib/matplotlib | `20260218_234323` | `20260219_190403` *(rerun pending)* | `20260220_094032` *(rerun pending)* | `20260221_005749` ✓ |
| pallets/flask | `20260219_021634` | `20260219_215321` | `20260220_115054` | `20260221_021918` ✓ |
| psf/requests | `20260219_022540` | `20260219_220131` | `20260220_115755` | `20260221_022439` ✓ |
| pydata/xarray | `20260219_030133` | `20260219_223642` | `20260220_123601` | `20260221_025638` ✓ |
| pytest-dev/pytest | `20260219_043417` | `20260220_000151` | `20260220_134949` | `20260221_042247` ✓ |
| scikit-learn/scikit-learn | `20260219_155601` | `20260220_014233` | `20260220_152959` | `20260221_055821` ✓ |
| sphinx-doc/sphinx | `20260219_133935` | `20260220_031810` *(rerun pending)* | `20260220_171540` *(rerun pending)* | `20260221_071644` ✓ |
| sympy/sympy | `20260219_145153` | `20260220_043013` *(rerun in progress)* | `20260220_184427` *(rerun queued)* | `20260221_083037` ✓ |

**none baseline status (Phase 2 gate — COMPLETE):** all 9 repos done — see frozen run ledger at bottom of this file

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
- **MISSING: gm_deterministic reruns — paper-minimum Flask/Requests/Pytest strict+same complete; extended matrix cells still pending.**
- deterministic tuning/tooling added:
  - machine-loadable deterministic config contract (`src/deterministic_config.py`)
  - deterministic sampler/selector utilities (`src/deterministic_tuning.py`)
  - locked tuning artifact builder with leaderboard + stability guard outcomes
  - `run_experiment.py --deterministic-config-path` support
  - `run_experiment.py --methods` support (subset execution; used for gm_deterministic-only tuning)
  - `src/evaluation.py` now supports `methods=...` and method-scoped index validation/build
  - `run_suite.py` now accepts `deterministic_config_path`
  - candidate set artifact generated: `results/gm_deterministic_tuning/candidates_v1.json` (seed=17, n=60)
  - Phase 1 orchestrator added: `tools/run_gm_deterministic_tuning_phase1.py`
  - Phase 1 tuning run completed (`./.venv/bin/python tools/run_gm_deterministic_tuning_phase1.py --coarse-limit 60 --top-k 10 --max-drop 0.03`)
  - final rerun artifact: `results/gm_deterministic_tuning/final_candidates_v1.json` (10/10 configs completed)
  - selected config artifact: `results/gm_deterministic_tuning/selection_v1.json`
    - selected `config_id=cfg-0054`
    - Flask train mean F1 `0.6786` (std `0.0000`)
    - holdout deltas vs baseline: Requests `+0.0900` (`0.5200` vs `0.4300`), Pytest `+0.0233` (`0.4733` vs `0.4500`)
    - `passes_stability_guard=true` (`max_drop=0.03`)
  - machine-loadable selected config frozen at `configs/gm_deterministic_selected_v1.json`
  - strict reruns completed with selected config (`--methods gm_deterministic`):
    - Flask strict: `results/runs/20260218_220114/summary.json` → F1 `0.6786`
    - Requests strict: `results/runs/20260218_220148/summary.json` → F1 `0.5200`
    - Pytest strict: `results/runs/20260218_220227/summary.json` → F1 `0.4733`
  - same-snapshot reruns completed with selected config (`--methods gm_deterministic`):
    - Flask same-snapshot: `results/runs/20260218_221905/summary.json` → F1 `0.6450`
    - Requests same-snapshot: `results/runs/20260218_221920/summary.json` → F1 `0.6033`
    - Pytest same-snapshot: `results/runs/20260218_221935/summary.json` → F1 `0.4733`
- FastAPI, Keras cells: not started (not required for paper minimum)

**Next action:**
Integrate strict+same gm_deterministic rerun outputs into retrieval reporting, then
run remaining Gemini-3 gm_deterministic matrix cells needed for amortization/extended matrix.
Commands:
- `./.venv/bin/python run_experiment.py --repo-name pallets/flask --source-prefix src/flask --n-issues 10 --evaluation-track same_snapshot_amortized --snapshot-commit d8c37f43724cd9fb0870f77877b7c4c7e38a19e0 --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json`
- `./.venv/bin/python run_experiment.py --repo-name psf/requests --source-prefix requests --n-issues 10 --evaluation-track same_snapshot_amortized --snapshot-commit 22623bd8c265b78b161542663ee980738441c307 --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json`
- `./.venv/bin/python run_experiment.py --repo-name pytest-dev/pytest --source-prefix src/_pytest --source-prefix src/pytest --n-issues 10 --evaluation-track same_snapshot_amortized --snapshot-commit aa55975c7d3f6c9f6d7f68accc41bb7cadf0eb9a --methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json`

---

### [DONE] Workstream B — Patching pipeline
**Owner files:** `run_patch.py`, `src/patch_agent.py`, `patch_manifests/`

**Pipeline hardening completed (Phase 0):**
- B1 (base_commit): fixed — `_checkout_issue_commit` uses per-issue base_commit ✓
- B2 (MAX_TOKENS Gemini 2.5): fixed — patch_max_output_tokens=12288 ✓
- B3 (manager termination): fixed — budget fallback to confirmed_files ✓
- B4 (retry code unvalidated): verified in run 20260218_133013 ✓
- B5 (redact_paths): fixed — patch stage now defaults to `patch_redact_paths_in_issue_text=false` ✓
- B6 (cold-start none): fixed — PatchAgent now performs issue-only model calls with zero files ✓
- B7 (empty patch submission): fixed — `_make_swebench_prediction` uses `patch_text or ""` ✓
- B8 (missing trailing newline): fixed — `extract_patch` appends `\n` before returning ✓
- B9 (thinking budget exhaustion): fixed — `patch_max_output_tokens=65536`; gemini-3-flash-preview
  shares output budget between thinking and text tokens; 12288 left only ~490 for output on large files ✓
- `run_patch.py` now has per-instance wall-clock caps (`instance_wall_clock_cap_s`) and timeout status ✓
- `patch_summary.json` now includes money-table fields:
  `retrieval_setup_tokens`, `retrieval_runtime_tokens`, `patch_runtime_tokens`,
  `total_cost_tokens`, `n_resolved`, `resolved_instances`, `cost_per_resolved_issue` ✓
- v4 Phase 1 (B10) complete in `run_patch.py`:
  - method-scoped setup build path (`gm_*`: graph-only; `rag_*`: rag-only; `none/oracle`: neither)
  - backward-compatible summary schema extension:
    `setup_tokens_graph_built`, `setup_tokens_rag_built`, `setup_tokens_method_accounted`
  - existing cost semantics preserved (`retrieval_setup_tokens`, `total_cost_tokens`)
- 139 unit tests passing (`./.venv/bin/python -m unittest discover -s tests -v`) ✓
- v4 Phase 3 artifacts generated via `tools/analyze_v4_handoff.py`:
  - `results/analysis_v4_handoff/resolved_rate_4method_table.csv`
  - `results/analysis_v4_handoff/pooled_cpr_table.csv`
  - `results/analysis_v4_handoff/dual_accounting_table.csv`
  - `results/analysis_v4_handoff/timeout_sensitivity_table.csv`
  - `results/analysis_v4_handoff/mcnemar_gm_vs_rag.json`
  - `results/analysis_v4_handoff/discordant_instances.csv`
  - `results/analysis_v4_handoff/rerun_gate_decision.md`
- v4 rerun gate outcome from current frozen evidence: **TRIGGERED (YES)**
  - criterion 2 passed (`GM-RAG` timeout-sensitivity gap shift `5.67pp` > `5pp`)
  - criterion 3 passed (timeout-confounded discordant majority: `17/23`)
  - targeted rerun scope if executed: `sympy/sympy`, `sphinx-doc/sphinx`, `matplotlib/matplotlib` for GM+RAG

**Validated runs (new config: patch=`gemini-3-flash-preview`, patch_max_file_chars=200000):**
- Oracle rerun (pre-B9): `20260218_163915` (`patch_max_output_tokens=12288`)
  - `n_patched=2/8`, `apply_success_rate=0.4000`, harness `resolved=3/8` (`37.5%`)
  - `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028` were `no_patch` with MAX_TOKENS.
- Oracle rerun (B9 validated): `20260218_172903` (`patch_max_output_tokens=65536`)
  - `n_patched=6/8`, `apply_success_rate=0.7500`, harness `resolved=4/8` (`50.0%`)
  - Resolved IDs: `psf__requests-1142`, `psf__requests-1724`, `psf__requests-1766`, `psf__requests-2317`
  - B9 target instances now emit patches with `stop_reason=FinishReason.STOP`:
    `psf__requests-2931`, `psf__requests-5414`, `psf__requests-6028`
- gm_progressive baseline (pre-B9): `20260218_165447` (`patch_max_output_tokens=12288`)
  - `n_patched=3/8`, `apply_success_rate=0.4286`, harness `resolved=2/8` (`25.0%`)
- gm_progressive baseline (B9 rerun): `20260218_175605` (`patch_max_output_tokens=65536`)
  - `n_patched=5/8`, `apply_success_rate=0.6250`, harness `resolved=2/8` (`25.0%`)
  - Resolved IDs: `psf__requests-1724`, `psf__requests-1766`
- Evaluated smoke (none baseline, schema validation): `20260218_195140` (1 instance)
  - `n_patched=0/1`, harness `resolved=0/1`, `patch_runtime_tokens=397`
  - Confirms complete cost schema + harness parse and non-zero patch-model usage for `none`
- Historical comparison oracle (pre-upgrade patch model): `20260218_154217` → `resolved=3/8` (`37.5%`), `apply_success_rate=0.5714`
- N=100 oracle-first study execution status:
  - completed manifests with summaries:
    - `patch_manifests/n100_verified/astropy_astropy_oracle_v1.yaml` → `results/patch_runs/20260218_223151/patch_summary.json`
    - `patch_manifests/n100_verified/matplotlib_matplotlib_oracle_v1.yaml` → `results/patch_runs/20260218_234323/patch_summary.json`
    - `patch_manifests/n100_verified/pallets_flask_oracle_v1.yaml` → `results/patch_runs/20260219_021634/patch_summary.json`
    - `patch_manifests/n100_verified/psf_requests_oracle_v1.yaml` → `results/patch_runs/20260219_022540/patch_summary.json`
    - `patch_manifests/n100_verified/pydata_xarray_oracle_v1.yaml` → `results/patch_runs/20260219_030133/patch_summary.json`
    - `patch_manifests/n100_verified/pytest_dev_pytest_oracle_v1.yaml` → `results/patch_runs/20260219_043417/patch_summary.json`
  - interrupted/incomplete attempts:
    - `results/patch_runs/20260219_063236` (scikit-learn, interrupted during harness; no `patch_summary.json`)
    - `results/patch_runs/20260219_081208` (scikit-learn retry, interrupted before predictions/summary)
  - root cause observed in logs: SWE-bench harness docker build OOM (`BuildImageError ... code 137`)
  - active recovery run:
    - `results/patch_runs/20260219_124650` (`patch_manifests/n100_verified/scikit_learn_scikit_learn_oracle_v1.yaml`)
    - live session id: `91403`, log: `logs/n100_oracle_resume_chain_20260219_124650.log`
    - recovery chain order after scikit: `sphinx_doc_sphinx_oracle_v1.yaml`, `sympy_sympy_oracle_v1.yaml`
  - unattended continuation supervisor (detached) is active:
    - pid: `341`
    - script: `/tmp/n100_unattended_runner.sh`
    - behavior: scans `patch_manifests/n100_verified/*.yaml`, enforces global oracle-first order, skips completed manifests, retries incomplete manifests in later cycles
    - log: `logs/n100_unattended_20260219_132505.log`
    - status heartbeat: `logs/n100_unattended_status.txt`

**Current patch manifest policy (all `patch_manifests/swebench_verified_*.yaml`):**
- Zero-shot: `patch_max_turns=1`, `patch_apply_repair_retries=1`, `patch_retrieval_retry_max=0`
- Backoff: `max_retries=2`, `initial_delay=0.5s`, `multiplier=1.7`, `max_delay=5.0s`, `jitter=0.2s`
- Cap: `instance_wall_clock_cap_s=480`
- Patch model/file context: `gemini-3-flash-preview`, `patch_max_file_chars=200000`, `patch_max_output_tokens=65536`
- Path redaction policy: retrieval redaction on, patch redaction off

**Next actions (in order):**
1. ✓ Phase 2 complete: all 9 `none` runs done.
2. ✓ Phase 3 analysis refreshed via `tools/analyze_v4_handoff.py` (results in `results/analysis_v4_handoff/`).
3. ✓ Targeted reruns complete (6/6). Final run IDs:
   - sympy GM: `20260221_111111`, sympy RAG: `20260221_123817`
   - sphinx GM: `20260221_141004`, sphinx RAG: `20260221_153148`
   - matplotlib GM: `20260221_165614`, matplotlib RAG: `20260221_202646`
   - Note: matplotlib RAG patch_summary corrected to n_resolved=1 (harness retry confirmed `matplotlib__matplotlib-22719`; `matplotlib__matplotlib-24870` is container apply-fail, counted unresolved).
4. ✓ `FROZEN_RUN_IDS` updated in `tools/analyze_v4_handoff.py` for all 6 entries.
5. ✓ Analysis re-run. Final locked numbers: GM=43/100, RAG=38/100, oracle=45/100, none=3/100. CPR method-accounted: GM=479,354, RAG=2,115,746 (~4.4× ratio). McNemar p=0.38 (not significant).
6. ✓ Patching tables in `05_results.tex` updated with final numbers. Abstract and conclusion updated. Paper compiled clean (20 pages).

**Pipeline additions (2026-02-22, post-pilot):**
- `--modal` flag added to `run_patch.py` — bypasses local Docker; uses Modal cloud Sandboxes for harness evaluation. Requires `modal setup` + `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` in `.env`.
- Two-stage pipeline added:
  - Stage 1: `run_patch.py --manifest <yaml>` — generates patches + writes `predictions.json`, no harness required
  - Stage 2: `run_patch.py --manifest <yaml> --evaluate-only --run-dir results/patch_runs/<run_id> [--modal]` — loads existing `predictions.json`, runs SWE-bench harness, updates `patch_summary.json` with `harness_results` and cost-per-resolved
- Modal pilot (psf/requests oracle, n=8): **COMPLETE** — 4/8 resolved (50%), 8/8 patched, CPR=15,373 tokens/resolved, Modal harness ~4 min total (parallel Sandboxes). One sandbox timeout (psf__requests-2317, 296.67s vs 300s limit). Run: `results/patch_runs/20260222_210339/`. See dev log `2026-02-22-modal-two-stage-pipeline.md`.
- Known issue: `timeout=300` in harness call too tight for slower instances — bump to 600 before next Modal run.

**Workstream B: DONE.**

---

### [DONE] Workstream C — Paper writing
**Owner files:** `research_report/sections/`, `research_report/main.tex`

**Status: COMPLETE (2026-02-22)**

**All retrieval cells filled. Paper compiles: 15 pages, 492 KB, 0 overfull hbox/vbox.**

**Completed this session (2026-02-22, session 2):**
- ✓ yt-dlp strict run complete: `results/runs/20260222_032232/` (GM-prog=0.347, RAG-prog=0.114, GM-det=0.297)
- ✓ LangChain strict run complete: `results/runs/20260222_035932/` (GM-prog=0.783, RAG-prog=0.366, GM-det=0.452)
- ✓ Keras strict run complete: `results/runs/20260222_040949/` (GM-det=0.274, GM-prog=0.267, RAG-prog=0.162)
- ✓ Table 3 (tab:main_results) fully filled — no pending cells remain
- ✓ Cross-benchmark section updated with all 4 new repos (FastAPI/yt-dlp/LangChain/Keras)
- ✓ Threats section updated: full retrieval matrix now complete
- ✓ Final clean compile: 15 pages, 492 KB, 0 overfull hbox

**Paper retrieval Table 3 summary (strict track):**

| Method | Flask | Requests | Pytest | FastAPI | yt-dlp | LangChain | Keras |
|--------|-------|----------|--------|---------|--------|-----------|-------|
| GM-det | 0.679 | 0.520 | 0.473 | 0.407 | 0.297 | 0.452 | 0.274 |
| GM-prog | 0.803 | 0.700 | 0.550 | 0.417 | 0.347 | **0.783** | 0.267 |
| RAG-prog | 0.704 | 0.733 | 0.602 | 0.421 | 0.114 | 0.366 | 0.162 |

**Next action:** None. Paper is ready for researcher review.

---

## Known Bugs

| ID | Severity | Description | Fixed? |
|----|----------|-------------|--------|
| B1 | CRITICAL | Wrong base_commit | YES — _checkout_issue_commit |
| B2 | CRITICAL | Thinking budget exhaustion (Gemini 2.5) | YES — max_output_tokens=12288 (Gemini 2.5 specific) |
| B3 | HIGH | Manager never terminates naturally | YES — budget fallback |
| B4 | HIGH | New retry/apply-check code unvalidated | YES — verified run 20260218_133013 |
| B5 | MEDIUM | redact_paths removes file hints in patching | YES — patch redaction defaults off |
| B6 | LOW | Cold-start crashes with ValueError | YES — issue-only no-context call path |
| B7 | CRITICAL | apply_failed patches submitted as "" to harness | YES — _make_swebench_prediction |
| B8 | HIGH | extract_patch strips trailing \\n → patch/git-apply rejects | YES — patch_agent.py |
| B9 | CRITICAL | gemini-3-flash-preview thinking tokens consume max_output_tokens budget → ~490 output tokens left → no patch extracted | YES — patch_max_output_tokens=65536 |
| B10 | HIGH | `run_patch.py` dual-build path (graph + rag both built for GM/RAG runs) confounds as-run cost/runtime interpretation | YES — fixed in v4 Phase 1 (method-scoped build path + split setup fields) |

B7+B8 root-cause analysis: `dev_logs/2026-02-18-b7-b8-empty-patch-trailing-newline.md`
Phase 0/1 details: `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md`

---

## Target Experiment Set (minimum for paper)

| Component | Target | Status |
|-----------|--------|--------|
| Retrieval: 6 methods × 3 repos × n=10 × 3 repeats | Flask, Requests, Pytest | ✓ done |
| Retrieval: gm_deterministic × 3 repos | Flask, Requests, Pytest | ✓ strict+same reruns complete (`20260218_220114`, `20260218_220148`, `20260218_220227`, `20260218_221905`, `20260218_221920`, `20260218_221935`) |
| Patching: oracle × 8 instances | psf/requests | ✓ done (`20260218_172903`, resolved 4/8, apply_success_rate 0.7500; historical `20260218_154217`=3/8 and pre-B9 `20260218_163915`=3/8) |
| Patching: N=100 Verified fixed split + 4 methods | 9 repos (anchors + capped extras) | manifests frozen ✓, runs pending ✗ |

---

## What NOT to do

- Do not start MAS orchestration (Paper 2 — see RESEARCH_INTENT.md)
- Do not change frozen N=100 split/manifests mid-study; regenerate only via script + new versioned split
- Do not touch Workstream A files while working on B, or vice versa
- Do not re-run retrieval cells that already have valid results
- Do not commit `*_repo/` or `results/` directories (gitignored)
- Do not promote Parking Lot items to [ACTIVE] workstreams — researcher does this

---

## Parking Lot
<!-- Agents: append observations and proposed tasks here. Do NOT self-promote to ACTIVE. -->
<!-- Researcher: review this section and promote/discard items each session. -->

## V2 AGENDA (next session — researcher to activate workstreams)
<!--
V1 pilot is ARCHIVED as reference. Paper is reference-only. V2 starts fresh.
Full plan: education/v2_next_session_plan.md
Sequencing: Research → Engineering → New experiments → Audit → Full runs
DO NOT skip to experiments without completing research phase first.
-->

**Phase 1 — Research (no code):**
- Study Agentless localization pipeline: token cost, BM25 vs LLM re-rank, patch agent tool access
- Study RepoMap (aider): graph vs flat summary, cost per repo, static vs dynamic
- Resolve open design question: fixed-context patch agent (Option A) vs agentic file-tool patch agent (Option B)
- Decision: comparison against published leaderboard numbers vs running their code

**Phase 2 — Engineering fixes (before new experiments):**
- E1: Bump Modal harness `timeout=300 → 600` in `run_patch.py` `swebench_eval()` calls (15 min)
- E2: Parallel Stage 1 — multiple repo clones + `--workers N` flag (1-2 days)
- E3: Checkpoint/resume for Stage 1 — flush per-instance results to partial JSONL (4-6 hours)
- E4: Investigate `max_workers` behavior with Modal (may be a no-op for Sandboxes)

**Phase 3 — New experiment design (after research):**
- New baseline lineup: BM25 (Tier 0), gm_det, raw_rag, gm_prog, rag_prog (symmetric tools), agentic_cold_start, oracle
- Replace `none` (empty context) with `agentic_cold_start` (agent with ls/cat/grep, no index)
- Aligned eval populations: same 3 repos (Flask/Requests/Pytest) for retrieval AND patching
- Symmetric tool interface: give rag_progressive a file-read tool to match GM's tool count
- Decide n≥300 (quality claim) vs cost-validation-only framing

**Phase 4 — Audit before full runs:**
- Small pilot (n=10, 2-3 methods, 1 repo) with new baseline lineup
- Adversarial audit (Professor Mean session) before committing to full runs

- 2026-02-22: Modal harness `timeout=300` is too tight — `psf__requests-2317` timed out at 296.67s. Bump to `timeout=600` in `run_patch.py` line `swebench_eval(..., timeout=300, ...)` before any Modal run on slower repos.
- 2026-02-22: `max_workers=1 if modal else 4` in the harness call may not control Modal parallelism — Modal Sandboxes appear to run all instances in parallel regardless. Investigate whether `max_workers` has a different meaning in the Modal context, and whether removing the special-case is safe.

- 2026-02-19: SWE-bench Verified has too few instances for the planned
  "10/repo across Flask+Requests+Pytest" patching design. Verified counts are:
  `psf/requests=8`, `pallets/flask=1`, `pytest-dev/pytest=19` (total 28 across
  these 3 repos). The prior "Flask has 11 in Verified" statement corresponds to
  full SWE-bench, not Verified. A scope decision is needed before scaling:
  either (a) keep Verified and include additional repos, or (b) switch patching
  scale runs to full SWE-bench for these 3 repos (`requests=44`, `flask=11`,
  `pytest=119`).
- 2026-02-19: N=100 Verified split and per-repo/method manifests generated:
  - split: `patch_manifests/verified_n100_split_v1.json`
  - manifests + hashes: `patch_manifests/n100_verified/manifest_ledger_v1.json`
- 2026-02-20: Evaluation-vulnerability notes (document-only; no protocol change yet):
  - Timeout censoring risk: `instance_wall_clock_cap_s=480` creates right-censoring on harder instances; this can bias both resolved-rate and cost-per-resolved if interpreted without caveat.
  - Timeout accounting choice: current primary metric includes timeout instances and any tokens spent before timeout; keep as operational headline, add timeout-excluded sensitivity table for interpretation.
  - Infra-vs-method failure separation: Docker/OOM/credential/harness failures should be tracked separately from model/pipeline failures; infra-affected IDs should be re-evaluated where possible.
  - External-validity constraint: current runs reflect researcher-local quotas/hardware/runtime constraints; production environments with higher quotas may reduce timeout pressure.
  - Partial comparability while runs are in flight: avoid final cross-method claims until rag+none complete on the frozen N=100 set.
  - Report framing requirement: explicitly present "budgeted deployment" primary results, with sensitivity analyses (`timeout-excluded`, `infra-recovered`) in threats/appendix.
- 2026-02-21: v4 handoff protocol approved:
  - claims lock moved to `CLAIMS_LOCK.md` (contract-safe; no `RESEARCH_INTENT.md` edit),
  - rerun decision is Phase-3 analysis-gated (not default),
  - Phase-1 requires TDD + backward-compatible schema extension.
- 2026-02-21: v4 execution update:
  - Phase 1 completed with full test pass (`139` tests),
  - Phase 3 artifacts generated in `results/analysis_v4_handoff/`,
  - rerun gate currently evaluates to YES on criteria 2+3,
  - Phase 2 remains in progress (`none` completion currently `1/9`).

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `RESEARCH_INTENT.md` | Paper scope, claims, experiment design principles |
| `CLAIMS_LOCK.md` | Permitted claim strength and forbidden framings |
| `CLAUDE.md` | Full dev policy (TDD, commits, scope rules, run_patch.py commands) |
| `dev_logs/2026-02-18-pipeline-vulnerability-assessment.md` | All 10 known bugs |
| `dev_logs/2026-02-18-end-to-end-improvement-plan.md` | Phased fix plan |
| `dev_logs/2026-02-18-phase0-1-patch-robustness-harness-fix.md` | Phase 0/1 work log |
| `dev_logs/2026-02-19-phase0-validation-tuning-contract.md` | Phase 0 gate validation + tuning artifact contract |
| `results/patch_runs/20260218_195140/patch_summary.json` | Latest evaluated smoke run (none baseline, schema/harness validated) |
| `EVALUATION_SPEC.md` | Metrics, protocols, statistical methods |
| `patch_manifests/swebench_verified_requests_v1.yaml` | 8-instance requests manifest |
| `patch_manifests/verified_n100_split_v1.json` | Frozen N=100 Verified split |
| `patch_manifests/n100_verified/manifest_ledger_v1.json` | Manifest hashes + per-repo method files |
| `tools/generate_n100_verified_manifests.py` | Deterministic N=100 split/manifest generator |
| `tools/tune_gm_deterministic.py` | gm_deterministic candidate sampling + config selection |
| `tools/run_gm_deterministic_tuning_phase1.py` | Phase 1 tuning protocol runner (coarse/top-k/holdout/select) |
| `results/gm_deterministic_tuning/final_candidates_v1.json` | Phase 1 top-k rerun results (10 configs) |
| `results/gm_deterministic_tuning/selection_v1.json` | Phase 1 selection artifact (leaderboard + guard outcomes) |
| `configs/gm_deterministic_selected_v1.json` | Frozen deterministic config for reruns |
| `results/clean_eval_20260211_201431/` | Valid retrieval results (frozen) |
| `research_report/artifacts/frozen-20260212-matrix-v2-clean/` | Frozen artifact bundle |
| `CLAIMS_LOCK.md` | Phase-4 permitted claim strength and forbidden framing |
| `dev_logs/2026-02-21-handoff-v4-prep.md` | v4 handoff prep decision log |
| `dev_logs/handoff-2026-02-21.md` | action-ready handoff checklist + artifact targets |
| `tools/analyze_v4_handoff.py` | v4 single-script analysis + rerun gate computation |
| `results/analysis_v4_handoff/` | Phase-3 output bundle (tables + McNemar + discordant + gate memo) |

**none baseline status (Phase 2 gate — COMPLETE):
- all 9 repos satisfy completion criterion (`harness_results.n_resolved` OR `harness_error` OR `harness_skipped_reason`) ✓
- astropy/astropy: `20260220_234209` marker=`harness_results` n_resolved=0
- matplotlib/matplotlib: `20260221_005749` marker=`harness_results` n_resolved=1
- pallets/flask: `20260221_021918` marker=`harness_results` n_resolved=0
- psf/requests: `20260221_022439` marker=`harness_results` n_resolved=1
- pydata/xarray: `20260221_025638` marker=`harness_results` n_resolved=0
- pytest-dev/pytest: `20260221_042247` marker=`harness_results` n_resolved=1
- scikit-learn/scikit-learn: `20260221_055821` marker=`harness_results` n_resolved=0
- sphinx-doc/sphinx: `20260221_071644` marker=`harness_results` n_resolved=0
- sympy/sympy: `20260221_083037` marker=`harness_results` n_resolved=0

