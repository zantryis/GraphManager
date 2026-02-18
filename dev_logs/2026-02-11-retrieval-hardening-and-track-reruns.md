# 2026-02-11 - Retrieval Hardening + Strict/Amortized Repeat Reruns

## Context

- `NEXT_AGENT_PROMPT.md` prioritized ranking/token-efficiency hardening and repeat-backed benchmark reruns.
- PolyBench pilot evidence showed high prompt cost and noisy retrieval behavior.
- Report sections and README still reflected older run snapshots.

Affected modules and artifacts:
- `src/evaluation.py`
- `src/manager_agent.py`
- `src/rag_baseline.py`
- `tests/test_agent_grounding.py`
- `tests/test_evaluation_logic.py`
- `results/repeat_sets/20260211_165946.json`
- `results/repeat_sets/20260211_170419.json`
- `results/repeat_sets/20260211_172738_polybench_partial.json`
- `research_report/artifacts/frozen-20260211-efficiency-hardening-v1/*`

## Decision

- Implemented retrieval hardening with strict TDD:
  - issue text preparation to strip template/log noise and reduce prompt payload,
  - compact progressive search payloads (drop verbose doc/snippet fields),
  - evidence-weighted file ranking and progressive confirmed-file gating.
- Re-ran primary SWE-bench requests tracks with fixed issue set IDs and 3 repeats each:
  - strict commit fidelity and same-snapshot amortized.
- Ran PolyBench strict repeats on yt-dlp; only 2 repeats completed reliably in this session, so frozen artifacts mark PolyBench as partial.
- Updated report sections and README to cite only frozen artifact-backed numbers.

Scope boundary:
- No MAS/productization work.
- No changes to resolver/plumbing architecture beyond retrieval policy behavior.

## Alternatives Considered

1. Keep retrieval logic unchanged and only rerun benchmarks.
Tradeoff: lower implementation risk, but would not address known ranking/payload inefficiency.

2. Perform broad prompt/system redesign for agents.
Tradeoff: potentially higher upside, but too much churn and weakly auditable against current roadmap.

3. Apply targeted hardening in existing policy surface (chosen).
Tradeoff: modest scope with strong testability and direct link to observed inefficiency.

## Evidence

Tests (red then green):
- `tests/test_agent_grounding.py`
  - ranking by file score,
  - progressive confirmed-file gating,
  - compact payload field reduction.
- `tests/test_evaluation_logic.py`
  - issue-template/code-fence stripping,
  - truncation behavior,
  - path redaction integration.

Full suite:
- `./.venv/bin/python -m unittest discover -s tests -v`
- Result: 51/51 passing.

Experiment artifacts:
- SWE-bench strict repeats: `results/repeat_sets/20260211_165946.json` (`ci_ready=true`)
- SWE-bench same-snapshot repeats: `results/repeat_sets/20260211_170419.json` (`ci_ready=true`)
- SWE-PolyBench strict partial repeats: `results/repeat_sets/20260211_172738_polybench_partial.json` (`n_runs=2`, `ci_ready=false`)
- Frozen bundle: `research_report/artifacts/frozen-20260211-efficiency-hardening-v1/manifest.json`

## Consequences

Expected benefits:
- Lower LLM context bloat in progressive loops.
- More deterministic grounded file ordering from accumulated tool evidence.
- Stronger strict-vs-amortized empirical separation with repeat-backed CI on primary SWE-bench track.

Known risks:
- PolyBench repeat completeness remains unresolved due API instability.
- Current repeated manifests remain small (`n=3`) and are not publication-final.

Monitoring signals:
- `tool_response_chars` and total LLM-token trends in future runs.
- Repeat gates (`min_repeats_met`, `ci_ready`) for PolyBench.
- Stability of paired delta CI as manifest size increases.

## Follow-up

1. Complete a CI-ready (`n_runs>=3`) strict PolyBench repeat set, then add same-snapshot PolyBench track.
2. Expand fixed manifests (`n>=10`) for SWE-bench strict and same-snapshot tracks.
3. Add SWE-bench Verified execution-anchor artifacts with the same frozen-report workflow.
