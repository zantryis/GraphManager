"""Generate frozen report artifacts from completed evaluation runs."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

DEFAULT_METHODS = [
    "gm_deterministic",
    "gm_progressive",
    "gm_baseline",
    "rag_progressive",
    "rag_baseline",
    "raw_rag_function",
    "raw_rag_fixed",
]


def _resolve_summary_path(run_path: str | Path) -> Path:
    path = Path(run_path)
    if path.is_file() and path.name == "summary.json":
        return path
    return path / "summary.json"


def _load_summary(run_path: str | Path) -> tuple[dict, Path]:
    summary_path = _resolve_summary_path(run_path)
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary not found: {summary_path}")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return payload, summary_path


def _build_rows(summaries: list[dict], methods: list[str]) -> list[dict]:
    rows = []
    for summary in summaries:
        meta = summary.get("_meta", {})
        run_id = str(meta.get("run_id", "unknown"))
        repo_name = str(meta.get("repo_name", "unknown"))
        for method in methods:
            data = summary.get(method, {}) or {}
            rows.append(
                {
                    "run_id": run_id,
                    "repo_name": repo_name,
                    "method": method,
                    "mean_f1": data.get("mean_f1", 0.0),
                    "total_cost_tokens": data.get("total_cost_tokens", 0),
                }
            )
    rows.sort(key=lambda row: (row["run_id"], row["method"]))
    return rows


def _write_csv(rows: list[dict], csv_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["run_id", "repo_name", "method", "mean_f1", "total_cost_tokens"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_latex_table(rows: list[dict], tex_path: Path):
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "\\begin{tabular}{llllr}",
        "\\hline",
        "Run ID & Repo & Method & Mean F1 & Total Cost Tokens \\\\",
        "\\hline",
    ]
    for row in rows:
        lines.append(
            f"{row['run_id']} & {row['repo_name']} & {row['method']} & "
            f"{float(row['mean_f1']):.3f} & {int(row['total_cost_tokens'])} \\\\"
        )
    lines.extend(["\\hline", "\\end{tabular}", ""])
    tex_path.write_text("\n".join(lines), encoding="utf-8")


def generate_report_artifacts(
    *,
    run_paths: list[str],
    output_root: str = "research_report/artifacts",
    artifact_id: str | None = None,
    methods: list[str] | None = None,
) -> Path:
    if not run_paths:
        raise ValueError("run_paths must not be empty")

    selected_methods = list(methods or DEFAULT_METHODS)
    artifact_name = artifact_id or time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / artifact_name
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    manifest_runs = []
    for run_path in run_paths:
        summary, summary_path = _load_summary(run_path)
        summaries.append(summary)
        meta = summary.get("_meta", {})
        manifest_runs.append(
            {
                "run_id": str(meta.get("run_id", summary_path.parent.name)),
                "repo_name": str(meta.get("repo_name", "unknown")),
                "summary_path": str(summary_path),
            }
        )

    rows = _build_rows(summaries, selected_methods)
    _write_csv(rows, output_dir / "tables" / "method_comparison.csv")
    _write_latex_table(rows, output_dir / "tables" / "method_comparison.tex")

    (output_dir / "summary_bundle.json").write_text(
        json.dumps({"summaries": summaries}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_id": artifact_name,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "methods": selected_methods,
                "runs": manifest_runs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_dir
