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
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from src.deterministic_config import load_deterministic_config
from src.run_ids import build_suite_id

ALL_METHODS = [
    "gm_deterministic",
    "gm_progressive",
    "gm_baseline",
    "rag_progressive",
    "rag_baseline",
    "raw_rag_function",
    "raw_rag_fixed",
]


def _bootstrap_ci_95_mean(values: list[float], n_bootstrap: int = 2000, seed: int = 17) -> tuple[float, float]:
    """Compute deterministic bootstrap 95% CI for the sample mean."""
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    sample_means = []
    n = len(values)
    for _ in range(n_bootstrap):
        draw = [values[rng.randrange(0, n)] for _ in range(n)]
        sample_means.append(statistics.fmean(draw))
    sample_means.sort()
    lo_idx = int(0.025 * (len(sample_means) - 1))
    hi_idx = int(0.975 * (len(sample_means) - 1))
    return (sample_means[lo_idx], sample_means[hi_idx])


def _compute_pairwise_deltas_with_ci(
    summaries: list[dict],
    metric_key: str = "mean_f1",
) -> dict:
    pairwise = {}
    for left_method in ALL_METHODS:
        for right_method in ALL_METHODS:
            if left_method == right_method:
                continue
            deltas = []
            for summary in summaries:
                left = summary.get(left_method, {}).get(metric_key)
                right = summary.get(right_method, {}).get(metric_key)
                if left is None or right is None:
                    continue
                deltas.append(float(left) - float(right))
            if not deltas:
                continue
            ci_low, ci_high = _bootstrap_ci_95_mean(deltas)
            key = f"{left_method}__minus__{right_method}__{metric_key}"
            pairwise[key] = {
                "n_runs": len(deltas),
                "mean_delta": statistics.fmean(deltas),
                "bootstrap_ci_95": [ci_low, ci_high],
            }
    return pairwise


def _aggregate_amortization(summaries: list[dict]) -> dict:
    """Aggregate amortization metadata across repeated runs."""
    blocks = [
        summary.get("_amortization", {})
        for summary in summaries
        if isinstance(summary, dict) and isinstance(summary.get("_amortization"), dict)
    ]
    if not blocks:
        return {}

    def _float_values(key: str) -> list[float]:
        values = []
        for block in blocks:
            if block.get(key) is None:
                continue
            values.append(float(block.get(key)))
        return values

    track_names = sorted(
        {
            str(block.get("track_name"))
            for block in blocks
            if block.get("track_name")
        }
    )
    n_issues_values = [int(block.get("n_issues", 0) or 0) for block in blocks]
    n_unique_values = [int(block.get("n_unique_commits", 0) or 0) for block in blocks]
    repeat_values = _float_values("commit_repeat_ratio")
    cache_values = _float_values("cache_hit_rate")

    return {
        "track_name": track_names[0] if len(track_names) == 1 else "mixed",
        "n_issues": max(n_issues_values) if n_issues_values else 0,
        "n_unique_commits": round(statistics.fmean(n_unique_values)) if n_unique_values else 0,
        "commit_repeat_ratio": statistics.fmean(repeat_values) if repeat_values else 0.0,
        "cache_hit_rate": statistics.fmean(cache_values) if cache_values else 0.0,
    }


def aggregate_repeat_summaries(summaries: list[dict]) -> dict:
    """Aggregate multiple run summaries into mean/std statistics."""
    metric_keys = [
        "mean_precision",
        "mean_recall",
        "mean_f1",
        "n_errors",
        "error_rate",
        "total_llm_tokens",
        "total_query_embedding_tokens",
        "avg_llm_tokens_per_issue",
        "avg_query_embedding_tokens_per_issue",
        "setup_embedding_tokens",
        "total_cost_tokens",
    ]
    aggregated = {}

    for method in ALL_METHODS:
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

    pairwise_deltas = _compute_pairwise_deltas_with_ci(
        summaries=summaries,
        metric_key="mean_f1",
    )
    amortization = _aggregate_amortization(summaries)

    payload = {
        "n_runs": len(summaries),
        "run_ids": [rid for rid in run_ids if rid],
        "methods": aggregated,
        "pairwise_deltas": pairwise_deltas,
        "gates": {
            "min_repeats_met": len(summaries) >= 3,
            "pairwise_bootstrap_available": bool(pairwise_deltas),
            "ci_ready": len(summaries) >= 3 and bool(pairwise_deltas),
        },
    }
    if amortization:
        payload["_amortization"] = amortization
    return payload


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
    parser.add_argument(
        "--no-redact-issue-paths",
        action="store_true",
        help="Disable path redaction in issue text before retrieval (default: redaction enabled)",
    )
    parser.add_argument(
        "--evaluation-track",
        type=str,
        default="strict_commit_fidelity",
        choices=["strict_commit_fidelity", "same_snapshot_amortized"],
        help="Evaluation track (default: strict_commit_fidelity)",
    )
    parser.add_argument(
        "--snapshot-commit",
        type=str,
        default=None,
        help="Optional fixed snapshot commit for same_snapshot_amortized track.",
    )
    parser.add_argument(
        "--instance-id",
        action="append",
        default=None,
        help="Optional manifest-pinned issue instance ID (repeatable).",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="",
        help="Optional domain label for matrix reporting (e.g., web_framework, library).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional reproducibility seed recorded in metadata.",
    )
    parser.add_argument(
        "--deterministic-seed-k",
        type=int,
        default=8,
        help="Deterministic retriever seed node count (default: 8).",
    )
    parser.add_argument(
        "--deterministic-depth",
        type=int,
        default=2,
        help="Deterministic retriever BFS depth cap (default: 2).",
    )
    parser.add_argument(
        "--deterministic-neighbor-cap",
        type=int,
        default=12,
        help="Deterministic retriever per-node neighbor cap (default: 12).",
    )
    parser.add_argument(
        "--deterministic-min-return-files",
        type=int,
        default=1,
        help="Minimum files returned by deterministic retriever (default: 1).",
    )
    parser.add_argument(
        "--deterministic-score-ratio-cutoff",
        type=float,
        default=0.70,
        help="Keep files with score >= cutoff * top score (default: 0.70).",
    )
    parser.add_argument(
        "--deterministic-min-score-cutoff",
        type=float,
        default=0.0,
        help="Absolute minimum score cutoff for deterministic retrieval (default: 0.0).",
    )
    parser.add_argument(
        "--deterministic-hub-degree-threshold",
        type=int,
        default=20,
        help="Degree threshold where hub penalty starts applying (default: 20).",
    )
    parser.add_argument(
        "--deterministic-hub-penalty-scale",
        type=float,
        default=0.35,
        help="Scale for hub-file penalty contribution (default: 0.35).",
    )
    parser.add_argument(
        "--deterministic-w-sem",
        type=float,
        default=0.35,
        help="Deterministic retriever semantic evidence weight (default: 0.35).",
    )
    parser.add_argument(
        "--deterministic-w-graph",
        type=float,
        default=0.30,
        help="Deterministic retriever graph evidence weight (default: 0.30).",
    )
    parser.add_argument(
        "--deterministic-w-conf",
        type=float,
        default=0.20,
        help="Deterministic retriever confidence evidence weight (default: 0.20).",
    )
    parser.add_argument(
        "--deterministic-w-hint",
        type=float,
        default=0.10,
        help="Deterministic retriever path hint weight (default: 0.10).",
    )
    parser.add_argument(
        "--deterministic-w-pen",
        type=float,
        default=0.05,
        help="Deterministic retriever low-confidence penalty weight (default: 0.05).",
    )
    parser.add_argument(
        "--deterministic-config-path",
        type=str,
        default=None,
        help=(
            "Optional JSON/YAML file with deterministic retrieval tuning parameters. "
            "Values in this file override CLI deterministic_* flags."
        ),
    )
    parser.add_argument(
        "--methods",
        type=str,
        default=None,
        help=(
            "Optional comma-separated subset of methods to execute. "
            f"Allowed: {', '.join(ALL_METHODS)}"
        ),
    )
    args = parser.parse_args()

    if args.deterministic_config_path:
        deterministic_overrides = load_deterministic_config(args.deterministic_config_path)
        for key, value in deterministic_overrides.items():
            setattr(args, key, value)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        print("Please set it in your .env file or as an environment variable.")
        print("  cp .env.example .env")
        print("  # Then edit .env and add your key")
        sys.exit(1)

    from src.evaluation import run_experiment

    source_prefixes = args.source_prefix if args.source_prefix else None
    manifest_instance_ids = tuple(dict.fromkeys(args.instance_id)) if args.instance_id else None
    requested_n_issues = len(manifest_instance_ids) if manifest_instance_ids else args.n_issues
    manager_max_turns = args.manager_max_turns if args.manager_max_turns is not None else args.max_turns
    rag_max_turns = args.rag_max_turns if args.rag_max_turns is not None else args.max_turns
    enabled_methods = tuple(
        method.strip()
        for method in (args.methods or "").split(",")
        if method.strip()
    ) if args.methods else tuple(ALL_METHODS)
    unknown_methods = sorted(set(enabled_methods) - set(ALL_METHODS))
    if unknown_methods:
        print(f"ERROR: unknown methods in --methods: {', '.join(unknown_methods)}")
        sys.exit(1)

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
            n_issues_requested=requested_n_issues,
            source_prefixes=tuple(dict.fromkeys(source_prefixes)) if source_prefixes else (),
            manager_max_turns=manager_max_turns,
            rag_max_turns=rag_max_turns,
            evaluation_track=args.evaluation_track,
            snapshot_commit=args.snapshot_commit,
            seed=args.seed,
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
            task_family=args.task_family,
            dataset_name=args.dataset_name,
            repo_name=args.repo_name,
            issue_set_id=issue_set_id,
            suite_id=suite_id,
            repeat_count=args.repeats,
            repeat_index=i + 1,
            experiment_notes=args.notes,
            redact_paths_in_issue_text=not args.no_redact_issue_paths,
            evaluation_track=args.evaluation_track,
            snapshot_commit=args.snapshot_commit,
            instance_ids=manifest_instance_ids,
            domain=args.domain,
            seed=args.seed,
            deterministic_seed_k=args.deterministic_seed_k,
            deterministic_depth=args.deterministic_depth,
            deterministic_neighbor_cap=args.deterministic_neighbor_cap,
            deterministic_min_return_files=args.deterministic_min_return_files,
            deterministic_score_ratio_cutoff=args.deterministic_score_ratio_cutoff,
            deterministic_min_score_cutoff=args.deterministic_min_score_cutoff,
            deterministic_hub_degree_threshold=args.deterministic_hub_degree_threshold,
            deterministic_hub_penalty_scale=args.deterministic_hub_penalty_scale,
            deterministic_w_sem=args.deterministic_w_sem,
            deterministic_w_graph=args.deterministic_w_graph,
            deterministic_w_conf=args.deterministic_w_conf,
            deterministic_w_hint=args.deterministic_w_hint,
            deterministic_w_pen=args.deterministic_w_pen,
            methods=enabled_methods,
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
            "n_issues": requested_n_issues,
            "n_issues_requested": requested_n_issues,
            "n_issues_evaluated": inferred_n_eval,
            "source_prefixes": list(dict.fromkeys(source_prefixes)) if source_prefixes else [],
            "manager_max_turns": manager_max_turns,
            "rag_max_turns": rag_max_turns,
            "repeats": args.repeats,
            "task_family": args.task_family,
            "dataset_name": args.dataset_name,
            "repo_name": args.repo_name,
            "issue_set_id": issue_set_id or first_meta.get("issue_set_id", "unknown"),
            "suite_id": suite_id or first_meta.get("suite_id", "unknown"),
            "notes": args.notes,
            "domain": args.domain,
            "evaluation_track": args.evaluation_track,
            "snapshot_commit": args.snapshot_commit,
            "seed": args.seed,
            "enabled_methods": list(enabled_methods),
            "manifest_instance_ids": list(manifest_instance_ids or []),
            "deterministic_retrieval": {
                "config_path": args.deterministic_config_path,
                "seed_k": args.deterministic_seed_k,
                "depth": args.deterministic_depth,
                "neighbor_cap": args.deterministic_neighbor_cap,
                "min_return_files": args.deterministic_min_return_files,
                "score_ratio_cutoff": args.deterministic_score_ratio_cutoff,
                "min_score_cutoff": args.deterministic_min_score_cutoff,
                "hub_degree_threshold": args.deterministic_hub_degree_threshold,
                "hub_penalty_scale": args.deterministic_hub_penalty_scale,
                "w_sem": args.deterministic_w_sem,
                "w_graph": args.deterministic_w_graph,
                "w_conf": args.deterministic_w_conf,
                "w_hint": args.deterministic_w_hint,
                "w_pen": args.deterministic_w_pen,
            },
        }

        repeat_sets_dir = Path(args.results_dir) / "repeat_sets"
        repeat_sets_dir.mkdir(parents=True, exist_ok=True)
        repeat_id = time.strftime("%Y%m%d_%H%M%S")
        output_path = repeat_sets_dir / f"{repeat_id}.json"
        output_path.write_text(json.dumps(aggregate, indent=2))

        print(f"\nRepeat aggregate saved to {output_path}")
        print("Summary (mean ± std F1):")
        for method in ALL_METHODS:
            f1 = aggregate.get("methods", {}).get(method, {}).get("mean_f1", {})
            if not f1:
                continue
            print(
                f"  {method:<18} {f1.get('mean', 0):.3f} ± {f1.get('std', 0):.3f} "
                f"(min={f1.get('min', 0):.3f}, max={f1.get('max', 0):.3f})"
            )


if __name__ == "__main__":
    main()
