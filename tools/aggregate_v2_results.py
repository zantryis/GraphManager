#!/usr/bin/env python3
"""Aggregate V2 retrieval and patching results into a scorecard.

Reads all results from results/runs/ (retrieval) and results/v2_full_runs/patch_runs/
(patching), then outputs:
  - retrieval.csv
  - patching.csv
  - retrieval_table.tex
  - patching_table.tex
  - mcnemar.txt

Usage:
    python tools/aggregate_v2_results.py --results-root results --output-dir results/v2_scorecard
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

# Canonical V2 populations
V2_TARGET_REPOS = [
    "astropy/astropy",
    "django/django",
    "matplotlib/matplotlib",
    "mwaskom/seaborn",
    "pallets/flask",
    "psf/requests",
    "pydata/xarray",
    "pylint-dev/pylint",
    "pytest-dev/pytest",
    "scikit-learn/scikit-learn",
    "sphinx-doc/sphinx",
    "sympy/sympy",
]

V2_RETRIEVAL_METHODS = [
    "gm_deterministic",
    "gm_progressive",
    "gm_baseline",
    "rag_progressive",
    "rag_baseline",
    "raw_rag_function",
    "raw_rag_fixed",
    "bm25",
    "repomap_like",
    "agentless_like_localization",
    "agentic_cold_start",
]

V2_PATCHING_METHODS = [
    "oracle",
    "gm_progressive",
    "gm_deterministic",
    "rag_progressive",
    "raw_rag_function",
    "raw_rag_fixed",
    "bm25",
    "agentic_cold_start",
    "repomap_like",
    "agentless_like_localization",
]

_RETRIEVAL_METHOD_ABBREV = {
    "gm_deterministic": "GM-D",
    "gm_progressive": "GM-P",
    "gm_baseline": "GM-B",
    "rag_progressive": "RAG-P",
    "rag_baseline": "RAG-B",
    "raw_rag_function": "RRF",
    "raw_rag_fixed": "RRX",
    "bm25": "BM25",
    "repomap_like": "RPM",
    "agentless_like_localization": "AGL",
    "agentic_cold_start": "ACS",
}

_PATCHING_METHOD_ABBREV = {
    "oracle": "Oracle",
    "gm_progressive": "GM-P",
    "gm_deterministic": "GM-D",
    "rag_progressive": "RAG-P",
    "raw_rag_function": "RRF",
    "raw_rag_fixed": "RRX",
    "bm25": "BM25",
    "agentic_cold_start": "ACS",
    "repomap_like": "RPM",
    "agentless_like_localization": "AGL",
}


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def collect_retrieval_results(results_root: Path) -> dict[str, dict[str, dict]]:
    """Scan results/runs/*/summary.json and return {repo: {method: method_data}}.

    For each (repo, method) pair, keeps the latest run (by run_id timestamp).
    """
    runs_dir = Path(results_root) / "runs"
    target_repos = set(V2_TARGET_REPOS)
    target_methods = set(V2_RETRIEVAL_METHODS)

    # best[(repo, method)] = (run_id, method_data)
    best: dict[tuple[str, str], tuple[str, dict]] = {}

    if not runs_dir.exists():
        return {}

    for summary_path in runs_dir.glob("*/summary.json"):
        data = _load_json(summary_path)
        if not data:
            continue
        meta = data.get("_meta", {})
        if not isinstance(meta, dict):
            continue
        repo = str(meta.get("repo_name") or "")
        if repo not in target_repos:
            continue
        run_id = str(meta.get("run_id") or summary_path.parent.name)
        for method in (meta.get("enabled_methods") or []):
            if method not in target_methods:
                continue
            method_data = data.get(method)
            if not isinstance(method_data, dict):
                continue
            if int(method_data.get("n_success", 0)) == 0:
                continue
            key = (repo, method)
            prev = best.get(key)
            if prev is None or run_id > prev[0]:
                best[key] = (run_id, method_data)

    result: dict[str, dict[str, dict]] = {}
    for (repo, method), (_, method_data) in best.items():
        result.setdefault(repo, {})[method] = method_data
    return result


def collect_patching_results(results_root: Path) -> dict[str, dict[str, dict]]:
    """Scan results/v2_full_runs/patch_runs/*/patch_summary.json and return {repo: {method: summary}}.

    For each (repo, method) pair, keeps the latest completed run (by directory name).
    """
    patch_runs = Path(results_root) / "v2_full_runs" / "patch_runs"
    best: dict[tuple[str, str], tuple[str, dict]] = {}

    if not patch_runs.exists():
        return {}

    for summary_path in patch_runs.glob("*/patch_summary.json"):
        data = _load_json(summary_path)
        if not data:
            continue
        repo = str(data.get("repo_name") or "")
        method = str(data.get("retrieval_method") or "")
        run_id = summary_path.parent.name
        if not repo or not method:
            continue
        key = (repo, method)
        prev = best.get(key)
        if prev is None or run_id > prev[0]:
            best[key] = (run_id, data)

    result: dict[str, dict[str, dict]] = {}
    for (repo, method), (_, data) in best.items():
        result.setdefault(repo, {})[method] = data
    return result


def write_retrieval_csv(retrieval: dict, output_path: Path) -> None:
    fieldnames = [
        "repo", "method", "mean_f1", "mean_precision", "mean_recall",
        "runtime_tokens_per_issue", "setup_tokens", "total_tokens_per_issue", "n_issues",
    ]
    rows = []
    for repo in V2_TARGET_REPOS:
        for method in V2_RETRIEVAL_METHODS:
            data = retrieval.get(repo, {}).get(method)
            if data:
                rows.append({
                    "repo": repo,
                    "method": method,
                    "mean_f1": round(float(data.get("mean_f1") or 0), 3),
                    "mean_precision": round(float(data.get("mean_precision") or 0), 3),
                    "mean_recall": round(float(data.get("mean_recall") or 0), 3),
                    "runtime_tokens_per_issue": round(float(data.get("avg_runtime_tokens_per_issue") or 0), 0),
                    "setup_tokens": round(float(data.get("setup_embedding_tokens") or 0), 0),
                    "total_tokens_per_issue": round(float(data.get("avg_total_cost_tokens_per_issue") or 0), 0),
                    "n_issues": int(data.get("n_issues") or data.get("n_success") or 0),
                })
            else:
                rows.append({f: "" for f in fieldnames} | {"repo": repo, "method": method})

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_patching_csv(patching: dict, output_path: Path) -> None:
    fieldnames = [
        "repo", "method", "n_instances", "n_resolved",
        "resolve_rate", "CPR_method_accounted", "CPR_as_run",
    ]
    rows = []
    for repo in V2_TARGET_REPOS:
        for method in V2_PATCHING_METHODS:
            data = patching.get(repo, {}).get(method)
            if data:
                n_instances = int(data.get("n_instances") or 0)
                harness = data.get("harness_results") or {}
                n_resolved = int(harness.get("n_resolved") or 0)
                resolve_rate = float(harness.get("resolved_rate") or 0.0)
                cpr_as_run = data.get("cost_per_resolved_issue")
                cpr_method = data.get("cpr_method_accounted") or cpr_as_run
                rows.append({
                    "repo": repo,
                    "method": method,
                    "n_instances": n_instances,
                    "n_resolved": n_resolved,
                    "resolve_rate": round(resolve_rate, 3),
                    "CPR_method_accounted": int(cpr_method) if cpr_method is not None else "",
                    "CPR_as_run": int(cpr_as_run) if cpr_as_run is not None else "",
                })
            else:
                rows.append({f: "" for f in fieldnames} | {"repo": repo, "method": method})

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _tex_escape(s: str) -> str:
    return s.replace("_", r"\_")


def write_retrieval_latex(retrieval: dict, output_path: Path) -> None:
    n_methods = len(V2_RETRIEVAL_METHODS)
    col_spec = "l" + "r" * n_methods
    header_cells = " & ".join(
        _RETRIEVAL_METHOD_ABBREV.get(m, m) for m in V2_RETRIEVAL_METHODS
    )

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Retrieval F1 by repository and method (V2, strict\_commit\_fidelity track). "
        r"\textbf{Bold} = best per row.}",
        r"\label{tab:v2_retrieval_main}",
        r"\footnotesize",
        rf"\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        f"Repo & {header_cells} \\\\",
        r"\midrule",
    ]

    for repo in V2_TARGET_REPOS:
        row_data = retrieval.get(repo, {})
        f1_vals = [
            float(row_data[m].get("mean_f1") or 0) if m in row_data else None
            for m in V2_RETRIEVAL_METHODS
        ]
        best_f1 = max((v for v in f1_vals if v is not None), default=None)
        short = repo.split("/")[-1]
        cells = []
        for v in f1_vals:
            if v is None:
                cells.append(r"\textemdash")
            elif best_f1 is not None and abs(v - best_f1) < 1e-4:
                cells.append(r"\textbf{" + f"{v:.3f}" + "}")
            else:
                cells.append(f"{v:.3f}")
        lines.append(f"{_tex_escape(short)} & {' & '.join(cells)} \\\\")

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_patching_latex(patching: dict, output_path: Path) -> None:
    n_methods = len(V2_PATCHING_METHODS)
    col_spec = "l" + "r" * n_methods
    header_cells = " & ".join(
        _PATCHING_METHOD_ABBREV.get(m, m) for m in V2_PATCHING_METHODS
    )

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Issue resolution rate by repository and method (V2, SWE-bench Verified, single run).}",
        r"\label{tab:v2_patching_main}",
        r"\footnotesize",
        rf"\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        f"Repo & {header_cells} \\\\",
        r"\midrule",
    ]

    for repo in V2_TARGET_REPOS:
        row_data = patching.get(repo, {})
        short = repo.split("/")[-1]
        cells = []
        for method in V2_PATCHING_METHODS:
            data = row_data.get(method)
            if not data:
                cells.append(r"\textemdash")
            else:
                harness = data.get("harness_results") or {}
                rate = float(harness.get("resolved_rate") or 0.0)
                cells.append(f"{rate:.2f}")
        lines.append(f"{_tex_escape(short)} & {' & '.join(cells)} \\\\")

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_mcnemar(patching: dict, output_path: Path) -> None:
    """Write pairwise McNemar test results.

    Requires instance-level predictions.json files for each run to build
    per-instance resolved vectors. If data is unavailable, writes p=null notes.
    """
    reference = "gm_progressive"
    comparisons = [
        "rag_progressive", "bm25", "repomap_like",
        "agentless_like_localization", "agentic_cold_start",
    ]

    lines = [
        "# McNemar pairwise tests: gm_progressive vs baselines",
        "# Generated by tools/aggregate_v2_results.py",
        "# Note: instance-level predictions.json required for full computation.",
        "",
    ]

    try:
        from scipy.stats import mcnemar as _mcnemar  # noqa: F401
        have_scipy = True
    except ImportError:
        have_scipy = False

    if not have_scipy:
        lines.append("# scipy not available — pip install scipy for McNemar computation")
        for comp in comparisons:
            lines.append(f"{reference} vs {comp}: p=null (scipy unavailable)")
    else:
        lines.append("# Aggregate patch_summary.json does not contain instance-level resolved flags.")
        lines.append("# Re-run after T2 with instance-level predictions to compute exact p-values.")
        for comp in comparisons:
            lines.append(f"{reference} vs {comp}: p=null (insufficient instance-level data)")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate V2 retrieval and patching results")
    parser.add_argument("--results-root", default="results", help="Results root directory")
    parser.add_argument("--output-dir", default="results/v2_scorecard", help="Output directory")
    args = parser.parse_args()

    results_root = Path(args.results_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting retrieval results...")
    retrieval = collect_retrieval_results(results_root)
    n_r = sum(len(v) for v in retrieval.values())
    print(f"  {n_r} cells across {len(retrieval)} repos")

    print("Collecting patching results...")
    patching = collect_patching_results(results_root)
    n_p = sum(len(v) for v in patching.values())
    print(f"  {n_p} cells across {len(patching)} repos")

    print("Writing retrieval.csv ...")
    write_retrieval_csv(retrieval, output_dir / "retrieval.csv")

    print("Writing patching.csv ...")
    write_patching_csv(patching, output_dir / "patching.csv")

    print("Writing retrieval_table.tex ...")
    write_retrieval_latex(retrieval, output_dir / "retrieval_table.tex")

    print("Writing patching_table.tex ...")
    write_patching_latex(patching, output_dir / "patching_table.tex")

    print("Writing mcnemar.txt ...")
    compute_mcnemar(patching, output_dir / "mcnemar.txt")

    # Report missing data
    n_total_r = len(V2_TARGET_REPOS) * len(V2_RETRIEVAL_METHODS)
    if n_r < n_total_r:
        print(f"\nWARNING: {n_total_r - n_r}/{n_total_r} retrieval cells missing data")
    n_total_p = len(V2_TARGET_REPOS) * len(V2_PATCHING_METHODS)
    if n_p < n_total_p:
        print(f"WARNING: {n_total_p - n_p}/{n_total_p} patching cells missing data")

    print(f"\nScorecard written to: {output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
