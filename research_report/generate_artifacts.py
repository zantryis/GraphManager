#!/usr/bin/env python3
"""Generate frozen report artifacts from run summaries."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.report_artifacts import generate_report_artifacts


def _discover_default_runs(results_root: Path, limit: int) -> list[str]:
    runs_dir = results_root / "runs"
    run_paths = []
    if not runs_dir.exists():
        return run_paths
    for candidate in sorted(runs_dir.iterdir()):
        if not candidate.is_dir():
            continue
        summary_path = candidate / "summary.json"
        if summary_path.exists():
            run_paths.append(str(candidate))
    if limit > 0:
        run_paths = run_paths[-limit:]
    return run_paths


def main():
    parser = argparse.ArgumentParser(description="Generate report artifacts from frozen run summaries.")
    parser.add_argument(
        "--run",
        action="append",
        default=None,
        help="Run directory or summary.json path (repeatable). If omitted, auto-discovers latest runs.",
    )
    parser.add_argument(
        "--results-root",
        default="results",
        help="Results root used for run auto-discovery (default: results).",
    )
    parser.add_argument(
        "--latest-n",
        type=int,
        default=3,
        help="Number of latest runs to include when --run is omitted (default: 3).",
    )
    parser.add_argument(
        "--output-root",
        default="research_report/artifacts",
        help="Artifact output root (default: research_report/artifacts).",
    )
    parser.add_argument(
        "--artifact-id",
        default=None,
        help="Optional artifact directory name. Defaults to timestamp.",
    )
    args = parser.parse_args()

    run_paths = args.run or _discover_default_runs(Path(args.results_root), args.latest_n)
    if not run_paths:
        raise SystemExit("No run summaries found. Provide --run paths or generate experiment runs first.")

    artifact_dir = generate_report_artifacts(
        run_paths=run_paths,
        output_root=args.output_root,
        artifact_id=args.artifact_id,
    )
    print(f"Artifact bundle generated: {artifact_dir}")


if __name__ == "__main__":
    main()
