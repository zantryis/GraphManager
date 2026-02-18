# 2026-02-11 - Frozen Run Artifact Pipeline For Research Report (Workstream C)

## Context

- Workstream C requires report artifacts generated from frozen runs, with explicit manifests and table paths.
- Existing report scaffold existed (`research_report/`), but artifact extraction from `results/runs/*/summary.json` was manual.

## Decision

- Added `src/report_artifacts.py` with reproducible artifact generation:
  - loads frozen run summaries,
  - writes `manifest.json`,
  - writes `summary_bundle.json`,
  - writes `tables/method_comparison.csv`,
  - writes `tables/method_comparison.tex`.
- Added CLI wrapper:
  - `research_report/generate_artifacts.py`
  - supports explicit `--run` inputs or latest run auto-discovery.
- Updated `research_report/README.md` with artifact generation usage.
- Validated end-to-end by generating:
  - `research_report/artifacts/frozen-20260211-latest3/`

## Alternatives Considered

1. Keep manual copy/paste for report tables.
Tradeoff: low code effort, high reproducibility risk.
2. Integrate artifact generation into LaTeX build (`make pdf`) directly.
Tradeoff: convenient but tightly couples heavy data processing with document build.
3. Generate only CSV (no LaTeX table).
Tradeoff: simpler output, but less direct compatibility with manuscript workflow.

## Evidence

- Added unit test:
  - `tests/test_report_artifacts.py`
  - validates manifest and table outputs.
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 32 tests passing.
- End-to-end run:
  - `./.venv/bin/python research_report/generate_artifacts.py --latest-n 3 --artifact-id frozen-20260211-latest3`
  - Artifact bundle created successfully.

## Consequences

- Expected benefits:
  - report inputs are now frozen and auditable by manifest.
  - manuscript table updates can be regenerated from exact run paths.
- Known risks:
  - current table focuses on method-level summary metrics only.
  - no figure generation in this step yet.
- Monitoring signals:
  - manifest completeness (`run_id`, `repo_name`, source summary path),
  - consistency between generated tables and source summaries.

## Follow-up

1. Add figure generation scripts (cost-quality scatter, amortization plots) into artifact bundle.
2. Generate manuscript-ready tables for strict vs same-snapshot tracks separately.
3. Wire artifact bundle references into `research_report/sections/04_experimental_setup.tex` and `sections/05_results.tex`.
