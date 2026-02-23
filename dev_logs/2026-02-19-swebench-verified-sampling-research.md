# 2026-02-19 - SWE-bench Verified Sampling Reality Check

## Context

- The prior planning thread asked whether 100-300 patching instances are feasible
  on SWE-bench Verified using only `psf/requests`, `pallets/flask`, and
  `pytest-dev/pytest`.
- Existing plans and notes assumed `10/repo` for these three repos and contained
  one stale claim that Flask had 11 Verified instances.
- A concrete dataset-level count check was needed before planning larger runs.

## Decision

- Treat SWE-bench Verified counts as the planning authority for Verified-scope
  experiments.
- Record that `requests/flask/pytest` provide only 28 total Verified instances,
  which is below the requested 50-300 range.
- Defer the scaling choice to researcher decision:
  - Keep Verified and add more repos, or
  - Use full SWE-bench for these three repos.

## Alternatives Considered

1. Keep using prior manifest assumptions (`10/repo`) without re-checking dataset
   availability.
   Tradeoff: faster planning, but invalid/unrunnable experiment design.
2. Count instances directly from HF datasets for both Verified and full SWE-bench.
   Tradeoff: small upfront work, but removes ambiguity and prevents invalid plans.
3. Infer counts from historical local manifests only.
   Tradeoff: no external dependency, but fragile and likely stale/incomplete.

## Evidence

- Verified split count and schema loaded from HF dataset:
  - Command: `./.venv/bin/python - <<'PY' ... load_dataset('SWE-bench/SWE-bench_Verified', split='test') ... PY`
  - Result: `n=500`, split `test` only.
- Repo-level counts (Verified):
  - `psf/requests=8`
  - `pallets/flask=1`
  - `pytest-dev/pytest=19`
- Repo-level counts (full SWE-bench test split):
  - `psf/requests=44`
  - `pallets/flask=11`
  - `pytest-dev/pytest=119`
- Verified instance IDs were enumerated for these repos to confirm manifestable IDs.

## Consequences

- The current patching-scale plan must be reframed before execution if it must
  remain in SWE-bench Verified and only these three repos.
- A 100-instance pilot is impossible under current repo constraints in Verified.
- Planning can proceed immediately once repo-scope vs benchmark-scope is chosen.

## Follow-up

1. Choose scope for scale runs:
   - Verified + more repos, or
   - Full SWE-bench with requests/flask/pytest.
2. Regenerate manifests to match chosen scope and target N.
3. Recompute expected confidence intervals and cost budget for the selected N.
