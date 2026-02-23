#!/usr/bin/env python3
"""
Run a suite of experiments defined in a YAML config file.

Usage:
    python run_suite.py experiments.yaml
    python run_suite.py experiments.yaml --dry-run
    python run_suite.py experiments.yaml --only 0,2   # run specific indices
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
import os
from src.deterministic_config import load_deterministic_config


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_experiment(exp: dict, defaults: dict) -> dict:
    """Merge experiment-specific config with suite defaults."""
    default_max_turns = defaults.get("max_turns", 6)
    resolved_max_turns = exp.get("max_turns", default_max_turns)
    resolved = {
        "repo": exp["repo"],
        "source_prefixes": exp.get("source_prefixes"),
        "n_issues": exp.get("n_issues", defaults.get("n_issues", 10)),
        "task_family": exp.get(
            "task_family",
            defaults.get("task_family", "swe-bench"),
        ),
        "dataset_name": exp.get(
            "dataset_name",
            defaults.get("dataset_name", "SWE-bench/SWE-bench"),
        ),
        "manager_max_turns": exp.get(
            "manager_max_turns",
            exp.get("max_turns", defaults.get("manager_max_turns", resolved_max_turns)),
        ),
        "rag_max_turns": exp.get(
            "rag_max_turns",
            exp.get("max_turns", defaults.get("rag_max_turns", resolved_max_turns)),
        ),
        "redact_paths_in_issue_text": exp.get(
            "redact_paths_in_issue_text",
            defaults.get("redact_paths_in_issue_text", True),
        ),
        "evaluation_track": exp.get(
            "evaluation_track",
            defaults.get("evaluation_track", "strict_commit_fidelity"),
        ),
        "snapshot_commit": exp.get(
            "snapshot_commit",
            defaults.get("snapshot_commit"),
        ),
        "issue_set_id": exp.get("issue_set_id", defaults.get("issue_set_id")),
        "suite_id": exp.get("suite_id", defaults.get("suite_id")),
        "instance_ids": exp.get("instance_ids", defaults.get("instance_ids")),
        "repeats": int(exp.get("repeats", defaults.get("repeats", 1))),
        "notes": exp.get("notes", defaults.get("notes", "")),
        "seed": exp.get("seed", defaults.get("seed")),
        "domain": exp.get("domain", defaults.get("domain", "")),
        "deterministic_seed_k": int(
            exp.get("deterministic_seed_k", defaults.get("deterministic_seed_k", 8))
        ),
        "deterministic_depth": int(
            exp.get("deterministic_depth", defaults.get("deterministic_depth", 2))
        ),
        "deterministic_neighbor_cap": int(
            exp.get("deterministic_neighbor_cap", defaults.get("deterministic_neighbor_cap", 12))
        ),
        "deterministic_min_return_files": int(
            exp.get("deterministic_min_return_files", defaults.get("deterministic_min_return_files", 1))
        ),
        "deterministic_score_ratio_cutoff": float(
            exp.get("deterministic_score_ratio_cutoff", defaults.get("deterministic_score_ratio_cutoff", 0.70))
        ),
        "deterministic_min_score_cutoff": float(
            exp.get("deterministic_min_score_cutoff", defaults.get("deterministic_min_score_cutoff", 0.0))
        ),
        "deterministic_hub_degree_threshold": int(
            exp.get("deterministic_hub_degree_threshold", defaults.get("deterministic_hub_degree_threshold", 20))
        ),
        "deterministic_hub_penalty_scale": float(
            exp.get("deterministic_hub_penalty_scale", defaults.get("deterministic_hub_penalty_scale", 0.35))
        ),
        "deterministic_w_sem": float(
            exp.get("deterministic_w_sem", defaults.get("deterministic_w_sem", 0.35))
        ),
        "deterministic_w_graph": float(
            exp.get("deterministic_w_graph", defaults.get("deterministic_w_graph", 0.30))
        ),
        "deterministic_w_conf": float(
            exp.get("deterministic_w_conf", defaults.get("deterministic_w_conf", 0.20))
        ),
        "deterministic_w_hint": float(
            exp.get("deterministic_w_hint", defaults.get("deterministic_w_hint", 0.10))
        ),
        "deterministic_w_pen": float(
            exp.get("deterministic_w_pen", defaults.get("deterministic_w_pen", 0.05))
        ),
        "deterministic_config_path": exp.get(
            "deterministic_config_path",
            defaults.get("deterministic_config_path"),
        ),
    }
    if resolved.get("deterministic_config_path"):
        overrides = load_deterministic_config(resolved["deterministic_config_path"])
        resolved.update(overrides)
    return resolved


def run_single(
    exp: dict,
    api_key: str,
    results_dir: str,
    *,
    repeat_count: int,
    repeat_index: int,
) -> dict | None:
    """Run a single experiment and return the summary."""
    from src.evaluation import run_experiment

    source_prefixes = tuple(exp["source_prefixes"]) if exp["source_prefixes"] else None
    instance_ids = tuple(exp["instance_ids"]) if exp.get("instance_ids") else None

    summary = run_experiment(
        gemini_api_key=api_key,
        n_issues=exp["n_issues"],
        results_dir=results_dir,
        create_run_subdir=True,
        source_prefixes=source_prefixes,
        manager_max_turns=exp["manager_max_turns"],
        rag_max_turns=exp["rag_max_turns"],
        task_family=exp["task_family"],
        dataset_name=exp["dataset_name"],
        repo_name=exp["repo"],
        redact_paths_in_issue_text=exp["redact_paths_in_issue_text"],
        evaluation_track=exp["evaluation_track"],
        snapshot_commit=exp["snapshot_commit"],
        issue_set_id=exp["issue_set_id"],
        suite_id=exp["suite_id"],
        repeat_count=repeat_count,
        repeat_index=repeat_index,
        experiment_notes=exp.get("notes", ""),
        instance_ids=instance_ids,
        domain=exp.get("domain", ""),
        seed=exp.get("seed"),
        deterministic_seed_k=exp.get("deterministic_seed_k", 8),
        deterministic_depth=exp.get("deterministic_depth", 2),
        deterministic_neighbor_cap=exp.get("deterministic_neighbor_cap", 12),
        deterministic_min_return_files=exp.get("deterministic_min_return_files", 1),
        deterministic_score_ratio_cutoff=exp.get("deterministic_score_ratio_cutoff", 0.70),
        deterministic_min_score_cutoff=exp.get("deterministic_min_score_cutoff", 0.0),
        deterministic_hub_degree_threshold=exp.get("deterministic_hub_degree_threshold", 20),
        deterministic_hub_penalty_scale=exp.get("deterministic_hub_penalty_scale", 0.35),
        deterministic_w_sem=exp.get("deterministic_w_sem", 0.35),
        deterministic_w_graph=exp.get("deterministic_w_graph", 0.30),
        deterministic_w_conf=exp.get("deterministic_w_conf", 0.20),
        deterministic_w_hint=exp.get("deterministic_w_hint", 0.10),
        deterministic_w_pen=exp.get("deterministic_w_pen", 0.05),
    )
    return summary


def _safe_slug(text: str) -> str:
    chars = []
    for ch in str(text or ""):
        if ch.isalnum():
            chars.append(ch.lower())
        elif ch in {"/", "-", "_"}:
            chars.append("_")
    return "".join(chars).strip("_") or "exp"


def _write_repeat_aggregate(
    summaries: list[dict],
    exp: dict,
    *,
    results_dir: Path,
) -> Path | None:
    if len(summaries) < 2:
        return None
    from run_experiment import aggregate_repeat_summaries

    aggregate = aggregate_repeat_summaries(summaries)
    evaluated_counts = [
        int(summary.get("_meta", {}).get("n_issues_evaluated", 0))
        for summary in summaries
        if isinstance(summary, dict)
    ]
    inferred_n_eval = max(evaluated_counts) if evaluated_counts else exp["n_issues"]
    first_meta = summaries[0].get("_meta", {}) if summaries else {}
    aggregate["_meta"] = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_issues": exp["n_issues"],
        "n_issues_requested": exp["n_issues"],
        "n_issues_evaluated": inferred_n_eval,
        "source_prefixes": list(exp.get("source_prefixes") or []),
        "manager_max_turns": exp["manager_max_turns"],
        "rag_max_turns": exp["rag_max_turns"],
        "repeats": exp["repeats"],
        "task_family": exp["task_family"],
        "dataset_name": exp["dataset_name"],
        "repo_name": exp["repo"],
        "issue_set_id": exp.get("issue_set_id") or first_meta.get("issue_set_id", "unknown"),
        "suite_id": exp.get("suite_id") or first_meta.get("suite_id", "unknown"),
        "notes": exp.get("notes", ""),
        "domain": exp.get("domain", ""),
        "seed": exp.get("seed"),
        "evaluation_track": exp["evaluation_track"],
        "snapshot_commit": exp.get("snapshot_commit"),
        "manifest_instance_ids": list(exp.get("instance_ids") or []),
        "deterministic_retrieval": {
            "config_path": exp.get("deterministic_config_path"),
            "seed_k": exp.get("deterministic_seed_k", 8),
            "depth": exp.get("deterministic_depth", 2),
            "neighbor_cap": exp.get("deterministic_neighbor_cap", 12),
            "min_return_files": exp.get("deterministic_min_return_files", 1),
            "score_ratio_cutoff": exp.get("deterministic_score_ratio_cutoff", 0.70),
            "min_score_cutoff": exp.get("deterministic_min_score_cutoff", 0.0),
            "hub_degree_threshold": exp.get("deterministic_hub_degree_threshold", 20),
            "hub_penalty_scale": exp.get("deterministic_hub_penalty_scale", 0.35),
            "w_sem": exp.get("deterministic_w_sem", 0.35),
            "w_graph": exp.get("deterministic_w_graph", 0.30),
            "w_conf": exp.get("deterministic_w_conf", 0.20),
            "w_hint": exp.get("deterministic_w_hint", 0.10),
            "w_pen": exp.get("deterministic_w_pen", 0.05),
        },
    }

    repeat_dir = results_dir / "repeat_sets"
    repeat_dir.mkdir(parents=True, exist_ok=True)
    repeat_id = time.strftime("%Y%m%d_%H%M%S")
    slug = _safe_slug(
        f"{exp['task_family']}_{exp['repo']}_{exp['evaluation_track']}_{exp.get('issue_set_id', '')}"
    )
    output_path = repeat_dir / f"{repeat_id}_{slug}.json"
    output_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    return output_path


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run experiment suite from YAML config")
    parser.add_argument("config", help="Path to YAML config file")
    parser.add_argument("--results-dir", default="results", help="Results directory (default: results/)")
    parser.add_argument("--dry-run", action="store_true", help="Print experiment plan without running")
    parser.add_argument("--only", type=str, default=None, help="Comma-separated indices of experiments to run (e.g. 0,2)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: GEMINI_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    config = load_config(args.config)
    defaults = config.get("defaults", {})
    experiments = [resolve_experiment(e, defaults) for e in config.get("experiments", [])]

    # Filter to specific indices if requested
    if args.only:
        indices = [int(i.strip()) for i in args.only.split(",")]
        experiments_to_run = [(i, experiments[i]) for i in indices if i < len(experiments)]
    else:
        experiments_to_run = list(enumerate(experiments))

    # Print plan
    suite_name = config.get("suite", "unnamed")
    print(f"Suite: {suite_name}")
    print(f"Description: {config.get('description', '').strip()}")
    print(f"Total experiments: {len(experiments_to_run)}\n")

    for i, exp in experiments_to_run:
        prefixes = ", ".join(exp["source_prefixes"]) if exp["source_prefixes"] else "(all)"
        repeats = exp.get("repeats", 1)
        domain = exp.get("domain", "") or "-"
        issue_set = exp.get("issue_set_id", "") or "auto"
        print(
            f"  [{i}] {exp['repo']} | n={exp['n_issues']} | "
            f"mgr_turns={exp['manager_max_turns']} rag_turns={exp['rag_max_turns']} | "
            f"dataset={exp['dataset_name']} | "
            f"track={exp['evaluation_track']} | "
            f"domain={domain} | repeats={repeats} | issue_set={issue_set} | "
            f"prefix={prefixes} | redact_paths={exp['redact_paths_in_issue_text']}"
        )

    if args.dry_run:
        print("\n(dry run — nothing executed)")
        return

    # Save config alongside results
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    config_copy = results_dir / "experiment_config.yaml"
    shutil.copy2(args.config, config_copy)

    # Run experiments
    print(f"\n{'='*70}")
    summaries = []
    total_attempted_runs = 0
    successful_runs = 0
    successful_experiments = 0
    for idx, (i, exp) in enumerate(experiments_to_run):
        print(f"\n{'='*70}")
        print(f"EXPERIMENT {idx+1}/{len(experiments_to_run)}  [{i}] {exp['repo']}")
        print(f"{'='*70}")

        repeats = max(int(exp.get("repeats", 1) or 1), 1)
        repeat_summaries: list[dict] = []
        for repeat_idx in range(repeats):
            total_attempted_runs += 1
            if repeats > 1:
                print(f"\n  Repeat {repeat_idx + 1}/{repeats}")
            t0 = time.time()
            try:
                summary = run_single(
                    exp,
                    api_key,
                    args.results_dir,
                    repeat_count=repeats,
                    repeat_index=repeat_idx + 1,
                )
                elapsed = time.time() - t0
                if summary:
                    summaries.append(summary)
                    successful_runs += 1
                    repeat_summaries.append(summary)
                    gm_d = summary.get("gm_deterministic", {}).get("mean_f1", 0)
                    gm_p = summary.get("gm_progressive", {}).get("mean_f1", 0)
                    gm_b = summary.get("gm_baseline", {}).get("mean_f1", 0)
                    rag_p = summary.get("rag_progressive", {}).get("mean_f1", 0)
                    rag_b = summary.get("rag_baseline", {}).get("mean_f1", 0)
                    print(
                        f"    Completed in {elapsed:.0f}s — "
                        f"GM(d)={gm_d:.3f} GM(p)={gm_p:.3f} GM(b)={gm_b:.3f} "
                        f"RAG(p)={rag_p:.3f} RAG(b)={rag_b:.3f}"
                    )
                else:
                    print(f"    Completed in {elapsed:.0f}s — no summary returned")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"    FAILED after {elapsed:.0f}s: {e}")

        if repeats > 1 and repeat_summaries:
            repeat_path = _write_repeat_aggregate(
                repeat_summaries,
                exp,
                results_dir=results_dir,
            )
            if repeat_path:
                print(f"  Repeat aggregate: {repeat_path}")
        if repeat_summaries:
            successful_experiments += 1

    # Final summary
    print(f"\n{'='*70}")
    print("SUITE COMPLETE")
    print(f"{'='*70}")
    print(
        f"Experiments with >=1 successful repeat: "
        f"{successful_experiments}/{len(experiments_to_run)}"
    )
    print(f"Successful runs: {successful_runs}/{total_attempted_runs}\n")

    print(
        f"{'Repo':<25} {'GM(d)':>8} {'GM(p)':>8} {'GM(b)':>8} "
        f"{'RAG(p)':>8} {'RAG(b)':>8} {'Raw-F':>8} {'Raw-X':>8}"
    )
    print("-" * 94)
    for s in summaries:
        meta = s.get("_meta", {})
        print(f"{meta.get('repo_name', '?'):<25} "
              f"{s.get('gm_deterministic', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('gm_progressive', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('gm_baseline', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('rag_progressive', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('rag_baseline', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('raw_rag_function', {}).get('mean_f1', 0):>8.3f} "
              f"{s.get('raw_rag_fixed', {}).get('mean_f1', 0):>8.3f}")

    print(f"\nResults in: {args.results_dir}/runs/")
    print(f"Config saved to: {config_copy}")
    print(f"Visualize: python visualize_results.py")


if __name__ == "__main__":
    main()
