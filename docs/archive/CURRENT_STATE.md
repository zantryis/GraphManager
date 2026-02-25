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

Last updated: 2026-02-24
Last agent: Codex (8-method matrix correction + resumed local stage1 pool)

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

**Dashboard monitoring updates (2026-02-24):**
- `src/patch_dashboard.py` dedupe now prefers freshest manifest attempt by `last_seen_ts`
  (prevents old completed/stale attempts from masking new in-flight retries).
- `tools/patch_dashboard.py` active-only defaults remain on, with explicit manifest/repo/run columns.
- Dashboard regression tests expanded in `tests/test_patch_dashboard.py` (active-only stale filter +
  newer attempt replacing older complete attempt).
- Dashboard UI refreshed with method-grouped collapsible sections and clearer per-row phase hints
  (`setup/queued` vs stale attempts) in `tools/patch_dashboard.py`.
- `run_patch.py` now writes `pid` into `run_meta.json`; dashboard status logic uses PID liveness
  (when available) and stale-age guards to reduce false `not_started` rows.
- Dashboard top-level stats now include overall `patched / total issues` across visible runs
  (computed from deduped, filter-scoped rows; wired through `/api/status` summary payload).
- Stage-1 parallel progress now includes worker checkpoint files
  (`predictions_worker_*.jsonl`) for status/progress/staleness accounting.
- Dashboard run discovery now prunes deep artifact traversal (notably `patch_runs/*/_repos/*`)
  to prevent `/api/status` timeouts after run-scoped clone isolation.

**Parallel stage-1 hardening (2026-02-24):**
- `run_patch.py --workers N` now runs issue-level parallel stage-1 with per-run isolated clone roots
  (`results/patch_runs/<run_id>/_repos/*`) to avoid cross-manifest git-dir contention.
- Resume/checkpoint merge is worker-aware (`predictions_partial.jsonl` + worker files), with
  `predictions_partial.jsonl` taking precedence for duplicate instance IDs.
- `tools/run_manifest_pool.py` now forwards issue-level parallelism via `--run-workers N`.

**Queue status update (2026-02-24 09:52 local):**
- Full-run pool `logs/v2_full_manifests_20260223_222457.txt` was **stopped intentionally**.
- Reason: method-matrix mismatch discovered before completion:
  - queued manifests were generated from a 4-method set (`oracle`, `gm_progressive`, `bm25`, `agentic_cold_start`);
  - this does not match the later V2 baseline expansion direction (`gm_deterministic`, deterministic RAG, and planned `repomap_like` / `agentless_like_localization`).
- Data already produced remains on disk (`results/v2_full_runs/patch_runs/*`) and is resumable, but is now treated as a partial 4-method run set pending matrix reconciliation.
- Dashboard API/UI now separates denominator scopes to avoid misleading totals:
  - `summary_visible`: filtered rows currently shown
  - `summary_started`: all discovered started manifests under results root
  - `summary_plan`: planned campaign totals from `--manifest-list` (e.g., 48 manifests / 2000 issues)
  - dashboard cards now show `visible`, `started`, and `campaign planned` patched/total concurrently.

**Queue status update (2026-02-24 10:05 local):**
- V2 matrix reconciliation executed: manifests regenerated for an explicit 8-method full campaign
  (`oracle`, `gm_progressive`, `rag_progressive`, `gm_deterministic`, `raw_rag_function`,
  `raw_rag_fixed`, `bm25`, `agentic_cold_start`).
- New campaign manifest list: `logs/v2_full_manifests_8method_20260224_100240.txt`
  (`96` manifests / `4000` issue-method instances).
- Full pool relaunched in resume mode (no manifest timeout, local stage1-only):
  - command:
    `./.venv/bin/python tools/run_manifest_pool.py --manifest-list logs/v2_full_manifests_8method_20260224_100240.txt --results-dir results/v2_full_runs --max-parallel-repos 8 --manifest-timeout-s 0 --resume-incomplete --execution-mode local --evaluate-mode stage1_only --run-workers 2`
  - active pool log: `logs/v2_repo_pool_20260224_100338.log`
  - active dashboard (`127.0.0.1:5051`) now points at the corrected 96-manifest list.
- Accounting/report artifact: `docs/V2_RUN_ACCOUNTING_AND_EXECUTION_2026-02-24.md`.

**Baseline rebuild update (2026-02-24):**
- Implemented new retrieval baselines:
  - `repomap_like` (`src/repomap_like.py`)
  - `agentless_like_localization` (`src/agentless_like_localization.py`)
- Integrated into runtime dispatch and setup paths:
  - `run_patch.py` now supports both methods in `_run_retrieval` and method-scoped context build.
  - `src/evaluation.py` / `run_experiment.py` method catalogs updated to include both methods.
- Added ablation-ready manifest knobs for both methods (manifest-driven, no code edits required per ablation).
- Added ablation manifest generator:
  - `tools/generate_v2_baseline_ablation_manifests.py`
  - profile set includes map-budget, selector, personalization, stage-toggle, and branch ablations.
- Validation:
  - full unit suite passed: `240` tests (`./.venv/bin/python -m unittest discover -s tests -v`).
- Implementation/report artifact:
  - `docs/V2_NEW_BASELINES_IMPLEMENTATION_2026-02-24.md`

**V2 timeout recovery operations (2026-02-24):**
- Investigated stalled runs: root cause is manifest wall-clock timeout (`timeout rc=124`, 4200s).
- Confirmed timeout manifests from logs:
  - pool failures (`logs/v2_repo_pool_failures_20260223_225727.log`): 7 agentic timeouts
    (`django`, `matplotlib`, `pydata/xarray`, `pytest`, `scikit-learn`, `sphinx`, `sympy`)
  - watchdog failures (`logs/v2_full_failures_20260223_223555.log`): `astropy` agentic + `astropy` bm25
- Recovery started:
  - immediate resume reruns (10800s timeout) launched for free repos:
    - `sympy_sympy_agentic_cold_start_v1.yaml` → run_dir `20260223_233317`
    - `sphinx_doc_sphinx_agentic_cold_start_v1.yaml` → run_dir `20260223_231510`
  - continuous stalled-run recovery daemon started:
    - script: `/tmp/v2_stalled_resume_queue.py`
    - process monitors dashboard stalled rows and resumes in-place when repo slot is free
    - log: `logs/v2_stalled_resume_queue_20260224_005835.log`
- Timeout policy change applied:
  - `tools/run_manifest_pool.py` now supports `--manifest-timeout-s <= 0` (disabled) + `--resume-incomplete`.
  - old timeout-based pool/watchdog/recovery workers were terminated to avoid duplicate/competing writes.
  - full V2 pool relaunched in resume mode with no manifest timeout and 8-way repo concurrency:
    - command: `./.venv/bin/python tools/run_manifest_pool.py --manifest-list logs/v2_full_manifests_20260223_222457.txt --results-dir results/v2_full_runs --max-parallel-repos 8 --manifest-timeout-s 0 --resume-incomplete`
    - active log: `logs/v2_repo_pool_20260224_012417_no_manifest_timeout.log`
    - behavior: per-manifest wall-clock cutoff removed; per-issue caps still enforced by manifest (`instance_wall_clock_cap_s`).
- Modal credit fallback (2026-02-24):
  - `tools/run_manifest_pool.py` now supports:
    - `--execution-mode {modal,local}` (controls `--modal` flag to `run_patch.py`)
    - `--evaluate-mode {stage12,stage1_only}` (full eval vs patch generation only)
  - local Docker harness fallback is currently unavailable in this environment:
    - `/var/run/docker.sock` missing
    - rootless daemon attempt failed (`newuidmap` missing; no sudo provisioning in-session)
  - active fallback execution switched to parallel stage1-only generation (no harness dependency):
    - command:
      `./.venv/bin/python tools/run_manifest_pool.py --manifest-list logs/v2_full_manifests_20260223_222457.txt --results-dir results/v2_full_runs --max-parallel-repos 8 --manifest-timeout-s 0 --resume-incomplete --execution-mode local --evaluate-mode stage1_only`
    - active log: `logs/v2_repo_pool_20260224_083920_stage1_local.log`
    - intent: continue patch generation now; run Stage 2 evaluation later when Modal credentials are restored.

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
| B11 | CRITICAL | PatchAgent file reads could traverse outside repo via `../` paths | YES — path containment guard in `_read_file` |
| B12 | CRITICAL | V2 `agentic_cold_start` baseline aliased to `none` (invalid baseline semantics) | YES — implemented dedicated retrieval mode + manifest mapping fix |
| B13 | HIGH | `run_experiment --methods <subset>` could crash copying missing `graph.json` | YES — artifact copy now conditional on file existence |
| B14 | HIGH | V2 handoff/manifests drifted on pilot names and request counts | YES — corrected `v2_phase3_handoff.md` + manifest mapping |

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

## V2 AGENDA (researcher to activate workstreams)
<!--
V1 pilot is ARCHIVED as reference. Paper is reference-only. V2 starts fresh.
Full plan: v2_next_session_plan.md
Sequencing: Research → Engineering → New experiments → Audit → Full runs
DO NOT skip to experiments without completing research phase first.
-->

**Phase 1 — Research: DONE (2026-02-23)**
- Q1: Agentless — 3-stage hierarchical embedding+LLM, NO BM25, fixed-context patch, $0.70/instance
- Q2: RepoMap — flat text output over file-level PageRank graph, dynamic per turn, ~1K tokens/turn
- Q3: Patch agent tools — Option A (fixed-context) is correct for thesis isolation claim
- Findings: `dev_logs/2026-02-23-v2-phase1-research.md`

**Phase 2 — Engineering fixes: DONE (2026-02-23)**
- ✓ E1: Modal harness timeout 300→600 (`run_patch.py` both call sites)
- ✓ E4: `max_workers` is irrelevant for Modal path (confirmed; fixed misleading special-case)
- ✓ E3: Checkpoint/resume (`_flush_instance_to_checkpoint`, `_load_partial_checkpoint`, `--resume`)
- ~ E2: `--workers N` flag + `_distribute_instances` + `_merge_worker_predictions` scaffolded;
       parallel execution engine (ThreadPoolExecutor + per-worker repo clones) NOT YET DONE — parked
- 161 tests pass (was 143; +18 new checkpoint/distribute/merge tests)
- Dev log: `dev_logs/2026-02-23-v2-phase2-engineering.md`

**Resolved decisions (2026-02-23):**
- Patching dataset: **SWE-bench Verified, full 500-instance test set** (SOTA standard; direct comparison
  to Agentless 38.8%, etc.; resolves per-repo count problem by not restricting to 3 repos)
- BM25 implementation: **rank_bm25 library** (Tier 0 retrieval baseline, same repo interface as gm_det;
  NOT the Princeton bm25_27K dataset which is fixed to SWE-bench and not usable for retrieval F1)
- Repair samples: **1 per instance** (keep current; document explicitly as "single-sample" in paper)
- Patching vs. retrieval populations: retrieval stays Flask/Requests/Pytest (existing data);
  patching uses full SWE-bench Verified (all repos)

**Phase 3 — New experiment design: IN PROGRESS (2026-02-23)**
Full design spec: `v2_phase3_handoff.md`; dev log: `dev_logs/2026-02-23-v2-phase3-implementation.md`

- ✓ Step 1: BM25 retrieval baseline implemented (`src/bm25_baseline.py`)
  - Uses BM25Plus + regex tokenizer (alphanumeric splits)
  - Wired into `run_experiment.py` (ALL_METHODS), `src/evaluation.py`, `run_patch.py`
  - 12 new tests in `tests/test_bm25_baseline.py`
  - `rank_bm25` installed in `.venv`
- ✓ Step 2: Symmetric file-read tool for rag_progressive
  - `RAGAgent` now accepts `symmetric_tools: bool`, `repo_dir: str`, `max_file_chars: int`
  - `get_file_contents(path)` tool added; enabled via manifest flag `rag_symmetric_tools: true`
  - Path traversal protection (resolve().relative_to() check)
  - 9 new tests in `tests/test_rag_symmetric_tools.py`
- ✓ Step 3: V2 patching manifests generated
  - `tools/generate_v2_verified_manifests.py` created
  - `patch_manifests/v2_verified/` populated: 3 pilot + 48 full manifests
  - Pilot: psf/requests × {oracle, gm_progressive, bm25} = 3 files × 8 instances
  - Full: 12 repos × 4 methods = 48 files, 500 total unique instances
  - V2 settings: instance_wall_clock_cap_s=600, rate_limit_max_retries=3
  - Ledger: `patch_manifests/v2_verified/manifest_ledger_v2.json`
- ✓ Step 3b: P0/P1 hardening from first-pass audit (2026-02-24)
  - Implemented real `agentic_cold_start` retrieval mode (`src/agentic_cold_start.py`) and wired into `run_patch.py`
  - Fixed patch path traversal in `PatchAgent._read_file` (`resolve().relative_to(repo_root)` guard)
  - Canonicalized oracle outputs against valid repo paths before patch prompt inclusion
  - Added missing BM25 dependency to `requirements.txt` (`rank_bm25>=0.2.2`)
  - Fixed `run_experiment` latest-artifact copy path to tolerate method subsets with no `graph.json`
  - Corrected V2 manifest method mapping (`agentic_cold_start` no longer aliases `none`) and handoff command/count drift
- ✓ Step 3c: cross-method patch-input fairness cap (2026-02-24)
  - Added global post-retrieval cap before patch stage: `retrieval_max_files_for_patch` (default `6`, `null` disables)
  - Applied cap to initial retrieval and retrieval-retry paths before feeding `PatchAgent`
  - Added per-instance telemetry fields:
    `retrieved_files_pre_cap`, `retrieved_files_post_cap`, `retrieval_max_files_for_patch`
  - Added retrieval-cap unit tests (`RetrievalFileCapTests`)
  - Added explicit `retrieval_max_files_for_patch: 6` to all `patch_manifests/v2_verified/*.yaml`
- ✓ Step 3d: concurrent-run collision hardening (2026-02-24)
  - Added method/path-scoped harness run IDs in `run_patch.py`:
    `graphmanager_<run_id>_<method>_<pathhash>`
  - Wired into both Stage1+2 and `--evaluate-only` codepaths; persisted as `harness_run_id` in summaries.
  - Added same-second run-directory collision protection under shared `--results-dir`:
    auto-allocate `run_id` with numeric suffix (`_01`, `_02`, ...).
  - Added unit tests:
    - `HarnessRunIdTests`
    - `RunOutputDirAllocationTests`
- ✓ Step 3e: GraphManager run dashboard implemented (2026-02-24)
  - Added run-status collector module: `src/patch_dashboard.py`
  - Added web dashboard server: `tools/patch_dashboard.py`
    - endpoint: `/api/status`
    - live HTML table at `/` (auto-refresh)
    - scans `results/**/patch_runs/*`, using `predictions_partial.jsonl` + `patch_summary.json`
  - Added dashboard tests: `tests/test_patch_dashboard.py`
  - Dashboard discovery now includes empty run dirs so freshly launched runs appear immediately as `not_started`
  - Added run metadata + dedupe improvements for in-flight accuracy:
    - `run_patch.py` now writes `run_meta.json` at run start (`manifest`, `retrieval_method`, `n_instances_planned`).
    - dashboard now reads `run_meta.json` to show denominator pre-summary (`n_completed/n_instances`).
    - dashboard dedupes duplicate in-flight attempts for the same manifest (keeps freshest attempt).
    - backfilled `run_meta.json` for active V2 astropy runs so live dashboard is immediately accurate.
- 201 tests pass (`./.venv/bin/python -m unittest discover -s tests -v`)
- ✓ Step 4: Pilot run completed (2026-02-24; concurrent launch + Modal eval)
  - Launch mode: 3 manifests started concurrently, each in isolated workdir:
    `/tmp/gm_pilot_oracle`, `/tmp/gm_pilot_bm25`, `/tmp/gm_pilot_gmprogressive`
    to avoid git checkout contention on shared `requests_repo`.
  - Manifest set:
    - `patch_manifests/v2_verified/pilot_oracle_v1.yaml`
    - `patch_manifests/v2_verified/pilot_bm25_v1.yaml`
    - `patch_manifests/v2_verified/pilot_gm_progressive_v1.yaml`
  - Run roots:
    - `results/v2_pilot_parallel/pilot_oracle_v1_session_20260223_210845/patch_runs/20260223_210845/`
    - `results/v2_pilot_parallel/pilot_bm25_v1_session_20260223_210845/patch_runs/20260223_210845/`
    - `results/v2_pilot_parallel/pilot_gm_progressive_v1_session_20260223_210845/patch_runs/20260223_210845/`
  - Final pilot metrics (psf/requests, n=8 each):
    - oracle: patched `8/8`, resolved `4/8` (`50.0%`), total cost `61,490`, CPR `15,372.5`
    - bm25: patched `7/8`, resolved `4/8` (`50.0%`), total cost `289,433`, CPR `72,358.25`
    - gm_progressive: patched `7/8`, resolved `5/8` (`62.5%`), total cost `366,129`, CPR `73,225.8`
  - Harness mode: `--evaluate --modal` confirmed (all 3 runs entered SWE-bench harness path).
  - Pilot summary artifact added:
    - `docs/V2_PILOT_RESULTS_2026-02-24.md`
- IN PROGRESS Step 5: Adversarial audit + full run kickoff
  - ✓ Added missing-base-commit checkout recovery in `run_patch.py`:
    when `git checkout <base_commit>` fails with `reference is not a tree`,
    runner now fetches (`origin <commit>` fallback to `--all --tags --prune`) and retries.
  - ✓ Added regression tests:
    `CommitCheckoutSelectionTests.test_checkout_issue_commit_fetches_missing_commit_then_retries`
    and `...raises_on_non_missing_ref_errors`.
  - ✓ Full unit suite green after change: 206 tests passing.
  - ✓ Modal Stage1+2 smoke validated on real patch generation (non-dry-run):
    - manifest: `/tmp/v2_modal_smoke_1instance.yaml` (1 instance from pilot oracle)
    - run: `results/v2_smoke/patch_runs/20260223_222230/`
    - outcome: patched `1/1`, resolved `1/1`, harness via `--modal` confirmed.
  - ✓ Full V2 run launched (Verified test split, 48 manifests):
    - manifest list: `logs/v2_full_manifests_20260223_222457.txt`
    - runner script: `/tmp/v2_full_runner_20260223_222457.sh`
    - runner log: `logs/v2_full_run_20260223_222457.log`
    - kickoff metadata: `logs/v2_full_kickoff_20260223_222457.txt`
    - results root: `results/v2_full_runs/`
  - ✓ Full-run restart with watchdog after first-launch stall on manifest #1:
    - old runner (`20260223_222457`) hung on first manifest for >8h with no progress.
    - new watchdog runner launched:
      - script: `/tmp/v2_full_runner_watchdog_20260223_223555.sh`
      - log: `logs/v2_full_run_20260223_223555.log`
      - failure log: `logs/v2_full_failures_20260223_223555.log`
      - kickoff: `logs/v2_full_kickoff_20260223_223555.txt`
    - guardrails added at launcher level: unbuffered Python logs, per-manifest timeout (4200s), continue-on-failure.
  - ✓ Added repo-safe parallel manifest pool launcher and activated it for remaining repos:
    - script: `tools/run_manifest_pool.py`
    - policy: parallel across repos, serialized within each repo (avoids git checkout contention).
    - launched with `--max-parallel-repos 3`, then raised to `--max-parallel-repos 8` per researcher request.
    - active 8-way pool (astropy excluded while watchdog run is active):
      - pool log: `logs/v2_repo_pool_20260223_225727.log`
      - pool failures: `logs/v2_repo_pool_failures_20260223_225727.log`
  - ✓ Concurrency safety fix for 8-way launch:
    - hardened `_allocate_run_output_dir` against concurrent mkdir races (`FileExistsError` retry loop).
    - added race regression test:
      `RunOutputDirAllocationTests.test_allocate_run_output_dir_retries_when_mkdir_races`.
  - ✓ Dashboard launched for live tracking:
    - URL: `http://127.0.0.1:5051`
    - API: `http://127.0.0.1:5051/api/status`
    - log: `logs/patch_dashboard_5051_20260223_222457.log`

**Next action for Step 5 (researcher):**
1. Let the active full run proceed; monitor `logs/v2_full_run_20260223_222457.log` and dashboard `/api/status`.
2. If first failing manifest appears, resume from same manifest list after fix (runner already skips completed manifests by manifest path).
3. After completion, aggregate patch summaries into a V2 full-run scorecard (resolved rate + cost-per-resolved per method).

Pilot validation gates (all must pass before full run):
1. Oracle resolved rate ≥ 25%
2. BM25 + GM generate non-empty patches (resolved ≥ 0%)
3. predictions_partial.jsonl written for all instances
4. No apply_failed rate > 80%
5. Token costs in expected range (oracle ~30K-80K, GM ~50K-150K, BM25 ~5K-20K/instance)

**Phase 4 — Audit before full runs:** (folded into Phase 3 step 5)

- 2026-02-24: First-pass repository analysis artifact generated (code/docs/manifests/state audit):
  - `docs/FIRST_PASS_REPOSITORY_ANALYSIS_2026-02-24.md`
  - Includes severity-ranked findings, evidence references, and P0/P1/P2 remediation backlog.
- 2026-02-24: V2 run blueprint + remediation sequencing doc added:
  - `docs/V2_RUN_DESIGN_2026-02-24.md`
- 2026-02-24: Baseline rebuild design for `repomap_like` + `agentless_like_localization` added:
  - `docs/V2_BASELINE_REBUILD_DESIGN_2026-02-24.md`
  - Decision: proceed with L1 component-equated baselines now; defer L2 full-system reproduction.
  - Fidelity refinements applied: explicit RepoMap-like edge schema/weights, symbol->file projection note,
    constrained Agentless-like Stage 1 candidate selection, and strict Stage 3 span I/O contract.
- 2026-02-24: New baseline hardening patch applied (retrieval rigor + reproducibility):
  - `src/agentless_like_localization.py`: Stage 3 now uses stable SHA256-based sampling seed
    (no Python hash randomization drift across processes), enforces `stage3_max_tokens_per_file`,
    and reports `stage3_context_tokens_per_file` in method metadata.
  - Added tests in `tests/test_agentless_like_localization.py` for per-file Stage-3 token cap and
    deterministic span stability.
  - Full suite pass after patch: `./.venv/bin/python -m unittest discover -s tests -v` (`242` tests, all pass).
  - Live V2 pool snapshot (dashboard API, 2026-02-24): planned `96` manifests (`4000` instances);
    started `84` (`58 complete`, `6 running`, `20 stalled`), started-progress `1499/2267` completed,
    `926` patched.
- 2026-02-24: Data-completeness safeguard added for the active 8-method full run:
  - Verified non-rerun behavior on completed manifests (`tools/run_manifest_pool.py` emits `SKIP completed ...` by manifest path).
  - Launched detached mop-up supervisor (`setsid`) to prevent missing data on failed/stalled manifests:
    - script: `/tmp/v2_full_mopup_loop.sh`
    - pid: `10035`
    - log: `logs/v2_full_mopup_supervisor_20260224_142123.log`
  - Supervisor policy:
    - waits for current primary pool to exit,
    - runs additional passes with `--resume-incomplete`,
    - never reruns manifests with existing `patch_summary.json` (completed manifests are skipped).

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
