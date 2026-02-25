# V2 Vulnerability Remediation and Run Design (2026-02-24)

## 1) Objective

Define a run-ready V2 protocol that:
- keeps the pilot study signal,
- fixes critical validity/safety issues,
- and supports a comparison framing across BM25, deterministic graph/RAG, progressive graph/RAG, agentic cold start, plus external Agentless/RepoMap benchmarks.

## 2) Immediate Remediation Status

Completed in code (this session):
- `agentic_cold_start` is now an implemented retrieval mode (not aliased to `none`).
- Patch-stage file reads now enforce repo-root containment.
- Oracle file lists are canonicalized against valid in-repo file sets.
- `run_experiment` now tolerates method subsets that do not produce `graph.json`.
- `rank_bm25` dependency is declared in `requirements.txt`.
- V2 handoff/manifest drift fixed (pilot names and request counts aligned).
- Added cross-method retrieval→patch fairness cap: `retrieval_max_files_for_patch` (default 6).

## 3) Remaining Risks Before Full V2

P0:
- Resolve and freeze one explicit policy for retrieval-vs-patching population comparability in V2 writeup.

P1:
- Add dataset adapter observability/fail-fast mode for split load failures.
- Complete real Stage-1 parallel worker execution for `--workers > 1` or keep hard-disabled.
- Tighten model provenance fields so run metadata always reflects actual configured models.

## 4) V2 Method Matrix

## Retrieval (internal runs)
- Tier 0 (deterministic / no query-time LLM):
  - `bm25`
  - `gm_deterministic`
  - `raw_rag_function` and/or `raw_rag_fixed` (deterministic dense baseline)
- Tier 1 (agentic retrieval):
  - `gm_progressive`
  - `rag_progressive` (with `rag_symmetric_tools: true`)
- Tier 2 (patch-only baseline context source):
  - `agentic_cold_start`

## External baselines (reported, not reimplemented)
- Agentless (published leaderboard numbers)
- RepoMap (published tool/benchmark numbers)

Rationale: preserves apples-to-apples internal pipeline comparisons while transparently positioning external systems as reference points.

## 5) Run Sequence

1. Pilot gate (psf/requests, 8 instances)
- `pilot_oracle_v1.yaml`
- `pilot_bm25_v1.yaml`
- `pilot_gm_progressive_v1.yaml`

2. Pilot pass criteria
- Oracle resolved rate >= 25%
- BM25 and GM generate non-empty patches
- `predictions_partial.jsonl` written for every instance
- `apply_failed` rate <= 80% per method
- token costs in expected ranges from `CURRENT_STATE.md`

3. Adversarial pre-full audit
- Verify `agentic_cold_start` emits grounded file choices (no path leakage / no hallucinated out-of-repo paths).
- Verify RAG symmetric-tool path containment remains enforced.
- Verify summary schemas include complete cost/accounting fields for all methods.

4. Full V2 patching runs
- Use `patch_manifests/v2_verified/*_{oracle,gm_progressive,bm25,agentic_cold_start}_v1.yaml`.
- Execute in deterministic repo order with checkpoint/resume enabled.

## 6) Paper Framing Update (V2)

Recommended framing:
- Primary claim: cost-efficient structural retrieval under operational budgets.
- Secondary claim: quality competitiveness by tier (deterministic and progressive).
- External comparison: Agentless/RepoMap numbers used as contextual anchors, not direct pipeline-equivalent claims.
- Pilot numbers retained as directional evidence; full V2 runs become the main empirical section.

## 7) Execution Checklist

- [x] P0 path-safety and baseline-semantics fixes merged locally.
- [x] Full unit suite green (`201` tests).
- [x] Run 3 pilot manifests and store run IDs.
- [x] Validate pilot gates and publish pass/fail memo.
- [ ] Launch full V2 run set only if all gates pass.

## 8) Speed and Monitoring Notes

Observed from pilot summaries (`psf/requests`, n=8/method):
- Patch generation dominates runtime. Mean per-instance wall-clock:
  - oracle: `219.6s`
  - bm25: `298.5s`
  - gm_progressive: `225.1s` (`~15.4s` retrieval + `~206.6s` patch)
- Long-tail latency comes mostly from patch-model calls/retries, not retrieval setup.

Immediate speed posture:
1. Keep cross-method concurrency at the process level (one manifest per process), each in isolated workdirs.
2. Keep Modal harness enabled (`--evaluate --modal`) for evaluation parallelism.
3. Keep `api_timeout_s` and retry knobs explicit in manifests; tune only with small ablation before full sweep.

Concurrency-safety updates now in code:
- Harness run IDs are method/path scoped (prevents cross-run report collisions when run timestamps match).
- Run output directories auto-suffix on same-second collisions under a shared `--results-dir`.

Dashboard reuse assessment (`../dag-lbmas/dashboard/server.py`):
- The existing dashboard is a good UI shell, but its backend is tightly coupled to LbMAS `results/raw/*.jsonl`
  schema (`condition_id`, `score`, `wall_clock_ms`, `cost_usd`).
- GraphManager patch runs emit `predictions_partial.jsonl` and `patch_summary.json` with different fields.
- Recommendation: reuse the front-end pattern (auto-refresh cards/charts), but replace `/api/status` with a
  GraphManager adapter over `results/**/patch_runs/*`.

Implemented monitor:
- `tools/patch_dashboard.py` (GraphManager-native run tracker)
- start command:
  - `./.venv/bin/python tools/patch_dashboard.py --port 5051 --results-root results`
