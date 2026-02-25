# 2026-02-24 - V2 New Baselines Implementation (`repomap_like`, `agentless_like_localization`)

## Context

- User requested direct implementation of the proposed new baselines with rigorous ablation controls and safety.
- Existing runtime lacked `repomap_like` / `agentless_like_localization`; only design docs existed.
- Needed to integrate both methods without regressing existing patch/retrieval pipelines.

## Decision

- Implement both methods as first-class retrieval backends in code.
- Add method-specific manifest knobs for clean ablations.
- Keep active full-run queue stable (no forced method-matrix expansion in the running campaign); provide a dedicated ablation manifest generator for targeted experiments.

Scope boundary:
- This change does not claim full external system reproduction.
- This change does not automatically inject new methods into the currently running full 8-method campaign.

## Alternatives Considered

1. Keep methods as design-only and defer implementation.
- Tradeoff: no executable baselines, no ablation evidence.

2. Implement only in `run_patch.py` (skip retrieval eval integration).
- Tradeoff: quicker, but incomplete scientific instrumentation and weaker repeatability.

3. Implement runtime + retrieval-eval catalogs + ablation manifest tooling. (chosen)
- Tradeoff: broader code surface, but complete and reproducible experimental workflow.

## Evidence

Key files changed:
- `src/repomap_like.py`
- `src/agentless_like_localization.py`
- `run_patch.py`
- `src/evaluation.py`
- `run_experiment.py`
- `tools/generate_v2_baseline_ablation_manifests.py`
- `docs/V2_NEW_BASELINES_IMPLEMENTATION_2026-02-24.md`

Tests added/updated:
- `tests/test_repomap_like.py`
- `tests/test_agentless_like_localization.py`
- `tests/test_generate_v2_baseline_ablation_manifests.py`
- `tests/test_patch_runner.py` (dispatch + context build coverage)
- `tests/test_evaluation_logic.py` (method catalog/validation updates)

Validation output:
- `./.venv/bin/python -m unittest discover -s tests -v`
- Result: 240 passing tests.

## Consequences

- Benefits:
  - New baselines are executable and constrained (candidate-only selection guards).
  - Ablations are manifest-driven and reproducible.
  - Existing pipelines remain backward-compatible with prior methods.
- Risks:
  - New methods add LLM/API branches that can increase runtime variance/cost.
  - Agentless-like stage behavior is an approximation under this fixed-context patch pipeline.
- Monitoring signals:
  - `invalid_path_selection_rate` and `out_of_candidate_rejection_count` in method metadata.
  - stage3 schema-violation counters for agentless-like spans.

## Follow-up

1. Generate ablation manifests for target repos with `tools/generate_v2_baseline_ablation_manifests.py`.
2. Run retrieval-only smoke (`run_experiment.py --methods repomap_like,agentless_like_localization`) on Flask/Requests/Pytest.
3. Run bounded patch pilots for selected ablation profiles before deciding full-campaign inclusion.
