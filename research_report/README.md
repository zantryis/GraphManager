# Research Report Scaffold

This folder is a paper-oriented LaTeX scaffold for GraphManager.

## Files

- `main.tex`: primary manuscript entrypoint.
- `sections/`: section files for iterative writing.
- `references.bib`: bibliography seed.
- `Makefile`: local build commands.

## Build

```bash
cd research_report
make pdf
```

If `latexmk` is unavailable, install TeX tooling or use your preferred editor build.

## Writing Workflow

1. Freeze evaluation artifacts for a run set.
2. Fill `sections/04_experimental_setup.tex` from exact configs/manifests.
3. Fill `sections/05_results.tex` from frozen tables/plots only.
4. Add/update citations in `references.bib`.
5. Record major manuscript decisions in `../dev_logs/`.

## Frozen Artifact Generation

Generate report tables/manifests from frozen run summaries:

```bash
./.venv/bin/python research_report/generate_artifacts.py --latest-n 3
```

Outputs are written to `research_report/artifacts/<artifact-id>/` including:
- `manifest.json`
- `summary_bundle.json`
- `tables/method_comparison.csv`
- `tables/method_comparison.tex`
