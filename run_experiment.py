#!/usr/bin/env python3
"""
Graph-Augmented Manager — MVP Experiment Runner

Compares graph-based file retrieval vs RAG baselines on Flask issues from SWE-bench.

Usage:
    1. Copy .env.example to .env and add your Gemini API key
    2. pip install -r requirements.txt
    3. python run_experiment.py [--n-issues 10]
"""

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def build_suite_id(
    *,
    task_family: str,
    dataset_name: str,
    repo_name: str,
    issue_set_id: str,
    n_issues: int,
    source_prefixes: list[str],
    manager_max_turns: int,
    rag_max_turns: int,
) -> str:
    """Build a stable suite identifier for grouping comparable runs."""
    key_obj = {
        "task_family": task_family,
        "dataset_name": dataset_name,
        "repo_name": repo_name,
        "issue_set_id": issue_set_id,
        "n_issues": n_issues,
        "source_prefixes": source_prefixes,
        "manager_max_turns": manager_max_turns,
        "rag_max_turns": rag_max_turns,
    }
    digest = hashlib.sha1(json.dumps(key_obj, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"suite_{digest}"


def aggregate_repeat_summaries(summaries: list[dict]) -> dict:
    """Aggregate multiple run summaries into mean/std statistics."""
    methods = ["graph_manager", "rag_agent", "raw_rag_function", "raw_rag_fixed"]
    metric_keys = [
        "mean_precision",
        "mean_recall",
        "mean_f1",
        "total_llm_tokens",
        "avg_llm_tokens_per_issue",
        "setup_embedding_tokens",
        "total_cost_tokens",
    ]
    aggregated = {}

    for method in methods:
        method_metrics = {}
        for key in metric_keys:
            values = [
                float(summary.get(method, {}).get(key, 0.0))
                for summary in summaries
                if method in summary
            ]
            if not values:
                continue
            method_metrics[key] = {
                "mean": statistics.fmean(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0.0,
                "min": min(values),
                "max": max(values),
            }
        aggregated[method] = method_metrics

    run_ids = [
        summary.get("_meta", {}).get("run_id", "")
        for summary in summaries
        if isinstance(summary, dict)
    ]

    return {
        "n_runs": len(summaries),
        "run_ids": [rid for rid in run_ids if rid],
        "methods": aggregated,
    }


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run the Graph-Manager vs RAG comparison experiment"
    )
    parser.add_argument(
        "--n-issues",
        type=int,
        default=10,
        help="Number of issues to evaluate (default: 10)",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="results",
        help="Directory to save results (default: results/)",
    )
    parser.add_argument(
        "--flat-results",
        action="store_true",
        help="Write outputs directly into --results-dir instead of results/runs/<timestamp>/",
    )
    parser.add_argument(
        "--source-prefix",
        action="append",
        default=None,
        help="Restrict indexed files to these repo-relative prefixes (repeatable). Default: index all .py files",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=6,
        help="Default max tool-calling turns for both agents (default: 6)",
    )
    parser.add_argument(
        "--manager-max-turns",
        type=int,
        default=None,
        help="Override max tool-calling turns for Graph-Manager (default: --max-turns)",
    )
    parser.add_argument(
        "--rag-max-turns",
        type=int,
        default=None,
        help="Override max tool-calling turns for RAG-Agent (default: --max-turns)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repeated runs with identical settings (default: 1)",
    )
    parser.add_argument(
        "--manager-mode",
        type=str,
        choices=["baseline", "progressive"],
        default="progressive",
        help="Retrieval mode for Graph-Manager (default: progressive)",
    )
    parser.add_argument(
        "--rag-mode",
        type=str,
        choices=["baseline", "progressive"],
        default="progressive",
        help="Retrieval mode for RAG-Agent (default: progressive)",
    )
    parser.add_argument(
        "--task-family",
        type=str,
        default="swe-bench",
        help="High-level task family label in metadata (default: swe-bench)",
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default="SWE-bench/SWE-bench",
        help="Dataset label in metadata (default: SWE-bench/SWE-bench)",
    )
    parser.add_argument(
        "--repo-name",
        type=str,
        default="pallets/flask",
        help="Repository label in metadata (default: pallets/flask)",
    )
    parser.add_argument(
        "--issue-set-id",
        type=str,
        default=None,
        help="Optional issue set identifier. If omitted, a stable ID is inferred from selected instances.",
    )
    parser.add_argument(
        "--suite-id",
        type=str,
        default=None,
        help="Optional suite identifier for grouping runs. If omitted, a stable ID is inferred.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Optional free-form notes stored in run metadata",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        print("Please set it in your .env file or as an environment variable.")
        print("  cp .env.example .env")
        print("  # Then edit .env and add your key")
        sys.exit(1)

    from src.evaluation import run_experiment

    source_prefixes = args.source_prefix if args.source_prefix else None
    manager_max_turns = args.manager_max_turns if args.manager_max_turns is not None else args.max_turns
    rag_max_turns = args.rag_max_turns if args.rag_max_turns is not None else args.max_turns

    if args.repeats < 1:
        print("ERROR: --repeats must be >= 1")
        sys.exit(1)
    if args.repeats > 1 and args.flat_results:
        print("ERROR: --flat-results cannot be used with --repeats > 1 (results would overwrite).")
        sys.exit(1)

    issue_set_id = args.issue_set_id
    suite_id = args.suite_id
    if suite_id is None and issue_set_id is not None:
        suite_id = build_suite_id(
            task_family=args.task_family,
            dataset_name=args.dataset_name,
            repo_name=args.repo_name,
            issue_set_id=issue_set_id,
            n_issues=args.n_issues,
            source_prefixes=list(dict.fromkeys(source_prefixes)) if source_prefixes else [],
            manager_max_turns=manager_max_turns,
            rag_max_turns=rag_max_turns,
        )

    summaries = []
    for i in range(args.repeats):
        if args.repeats > 1:
            print(f"\n########## REPEAT {i + 1}/{args.repeats} ##########\n")
        summary = run_experiment(
            gemini_api_key=api_key,
            n_issues=args.n_issues,
            results_dir=args.results_dir,
            create_run_subdir=not args.flat_results,
            source_prefixes=tuple(dict.fromkeys(source_prefixes)) if source_prefixes else None,
            manager_max_turns=manager_max_turns,
            rag_max_turns=rag_max_turns,
            manager_retrieval_mode=args.manager_mode,
            rag_retrieval_mode=args.rag_mode,
            task_family=args.task_family,
            dataset_name=args.dataset_name,
            repo_name=args.repo_name,
            issue_set_id=issue_set_id,
            suite_id=suite_id,
            repeat_count=args.repeats,
            repeat_index=i + 1,
            experiment_notes=args.notes,
        )
        if isinstance(summary, dict):
            summaries.append(summary)
            meta = summary.get("_meta", {})
            if issue_set_id is None:
                issue_set_id = meta.get("issue_set_id")
            if suite_id is None:
                suite_id = meta.get("suite_id")

    if args.repeats > 1 and summaries:
        aggregate = aggregate_repeat_summaries(summaries)
        evaluated_counts = [
            int(summary.get("_meta", {}).get("n_issues_evaluated", 0))
            for summary in summaries
            if isinstance(summary, dict)
        ]
        inferred_n_eval = max(evaluated_counts) if evaluated_counts else args.n_issues
        first_meta = summaries[0].get("_meta", {}) if summaries else {}
        aggregate["_meta"] = {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_issues": args.n_issues,
            "n_issues_requested": args.n_issues,
            "n_issues_evaluated": inferred_n_eval,
            "source_prefixes": list(dict.fromkeys(source_prefixes)) if source_prefixes else [],
            "manager_max_turns": manager_max_turns,
            "rag_max_turns": rag_max_turns,
            "manager_mode": args.manager_mode,
            "rag_mode": args.rag_mode,
            "repeats": args.repeats,
            "task_family": args.task_family,
            "dataset_name": args.dataset_name,
            "repo_name": args.repo_name,
            "issue_set_id": issue_set_id or first_meta.get("issue_set_id", "unknown"),
            "suite_id": suite_id or first_meta.get("suite_id", "unknown"),
            "notes": args.notes,
        }

        repeat_sets_dir = Path(args.results_dir) / "repeat_sets"
        repeat_sets_dir.mkdir(parents=True, exist_ok=True)
        repeat_id = time.strftime("%Y%m%d_%H%M%S")
        output_path = repeat_sets_dir / f"{repeat_id}.json"
        output_path.write_text(json.dumps(aggregate, indent=2))

        print(f"\nRepeat aggregate saved to {output_path}")
        print("Summary (mean ± std F1):")
        for method in ["graph_manager", "rag_agent", "raw_rag_function", "raw_rag_fixed"]:
            f1 = aggregate.get("methods", {}).get(method, {}).get("mean_f1", {})
            if not f1:
                continue
            print(
                f"  {method:<18} {f1.get('mean', 0):.3f} ± {f1.get('std', 0):.3f} "
                f"(min={f1.get('min', 0):.3f}, max={f1.get('max', 0):.3f})"
            )


if __name__ == "__main__":
    main()
