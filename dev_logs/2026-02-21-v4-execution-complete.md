# 2026-02-21 - v4 Execution Complete (Phase 1/3/4 complete, Phase 2 live)

## Context

- Executed approved v4 handoff plan in `CURRENT_STATE.md` / `dev_logs/handoff-2026-02-21.md`.
- Scope touched:
  - Workstream B code: `run_patch.py`, `tests/test_patch_runner.py`
  - Workstream B analysis tooling: `tools/analyze_v4_handoff.py`
  - Workstream C claim-lock enforcement: `research_report/sections/05_results.tex`, `research_report/sections/08_conclusion.tex`
- Hard constraints honored:
  - no edits to `RESEARCH_INTENT.md`
  - no reruns of frozen oracle/gm_progressive/rag_progressive N=100 artifacts
  - no duplicate `none` starts; live state observed from process/log/filesystem

## Decision

- Complete v4 Phase 1 with strict TDD and backward-compatible schema extension.
- Implement and execute Phase 3 single-script artifact generation while Phase 2 `none` completion is in flight.
- Apply Phase 4 as comment-only enforcement (`% CLAIMS_LOCK: ...`) at non-compliant wording hotspots.
- Keep Phase 2 marked in progress until all 9 `none` summaries satisfy completion criterion.

## Alternatives Considered

1. Wait for all `none` runs before writing analysis tooling.
Main tradeoff: blocks productive work and delays rerun-gate visibility.

2. Start manual parallel `none` runs immediately.
Main tradeoff: higher duplicate-run risk while unattended supervisor is active.

3. Build analysis tooling now and monitor live `none` progression (chosen).
Main tradeoff: produces provisional tables for `none`, but keeps momentum and avoids duplicate launches.

## Evidence

- Phase 1 TDD:
  - added failing tests first in `tests/test_patch_runner.py`
  - initial fail observed (`ImportError`/missing fields), then implementation in `run_patch.py`
  - target module pass: `./.venv/bin/python -m unittest tests.test_patch_runner -v`
  - full suite pass: `./.venv/bin/python -m unittest discover -s tests -v` (`Ran 139 tests ... OK`)
- Phase 1 implementation:
  - method-scoped setup builder in `run_patch.py` (`_build_method_scoped_commit_context`)
  - RAG canonicalization no longer requires graph object in `_run_retrieval`
  - new cost fields in `_compute_cost_summary_fields`:
    - `setup_tokens_graph_built`
    - `setup_tokens_rag_built`
    - `setup_tokens_method_accounted`
  - backward compatibility preserved for:
    - `retrieval_setup_tokens`
    - `total_cost_tokens`
- Phase 3 outputs:
  - script: `tools/analyze_v4_handoff.py`
  - artifacts:
    - `results/analysis_v4_handoff/resolved_rate_4method_table.csv`
    - `results/analysis_v4_handoff/pooled_cpr_table.csv`
    - `results/analysis_v4_handoff/dual_accounting_table.csv`
    - `results/analysis_v4_handoff/timeout_sensitivity_table.csv`
    - `results/analysis_v4_handoff/mcnemar_gm_vs_rag.json`
    - `results/analysis_v4_handoff/discordant_instances.csv`
    - `results/analysis_v4_handoff/rerun_gate_decision.md`
- Rerun gate (current snapshot):
  - Criterion 1: NO
  - Criterion 2: YES (GM-RAG gap shift `5.6667pp` > `5pp`)
  - Criterion 3: YES (timeout-confounded discordant majority `17/23`)
  - Decision: **Trigger targeted rerun = YES** (`sympy/sympy`, `sphinx-doc/sphinx`, `matplotlib/matplotlib` for GM+RAG)
- Phase 2 live state at log time:
  - `none` completion: `1/9` (`astropy` complete)
  - active run process: `run_patch.py --manifest patch_manifests/n100_verified/matplotlib_matplotlib_none_v1.yaml --evaluate`
  - unattended supervisor process alive: `/tmp/n100_unattended_runner.sh` (pid `74036`)

## Consequences

- B10 confound is fixed for all future runs; new summaries expose split setup components directly.
- Phase 3 analysis is reproducible from one script with explicit dual-accounting approximation for frozen dual-build runs.
- Paper claim language now has explicit lock comments at identified risk points.
- Remaining risk: final 4-method completion and final handoff pack still depend on Phase 2 `none` completion.

## Follow-up

1. Continue monitoring Phase 2 until all 9 `none` cells are complete by criterion (`harness_results.n_resolved` OR `harness_error` OR `harness_skipped_reason`).
2. Re-run `./.venv/bin/python tools/analyze_v4_handoff.py` after `none=9/9`.
3. Execute gate-triggered targeted reruns (GM+RAG on `sympy/sympy`, `sphinx-doc/sphinx`, `matplotlib/matplotlib`) unless protocol is revised by researcher.
