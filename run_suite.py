#!/usr/bin/env python3
"""
Run a suite of experiments defined in a YAML config file.

Usage:
    python run_suite.py experiments.yaml
    python run_suite.py experiments.yaml --dry-run
    python run_suite.py experiments.yaml --only 0,2,4   # run specific indices
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


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_experiment(exp: dict, defaults: dict) -> dict:
    """Merge experiment-specific config with suite defaults."""
    return {
        "repo": exp["repo"],
        "source_prefixes": exp.get("source_prefixes"),
        "n_issues": exp.get("n_issues", defaults.get("n_issues", 10)),
        "max_turns": exp.get("max_turns", defaults.get("max_turns", 6)),
        "manager_mode": exp.get("manager_mode", "progressive"),
        "rag_mode": exp.get("rag_mode", "progressive"),
    }


def run_single(exp: dict, api_key: str, results_dir: str) -> dict | None:
    """Run a single experiment and return the summary."""
    from src.evaluation import run_experiment

    source_prefixes = tuple(exp["source_prefixes"]) if exp["source_prefixes"] else None

    summary = run_experiment(
        gemini_api_key=api_key,
        n_issues=exp["n_issues"],
        results_dir=results_dir,
        create_run_subdir=True,
        source_prefixes=source_prefixes,
        manager_max_turns=exp["max_turns"],
        rag_max_turns=exp["max_turns"],
        manager_retrieval_mode=exp["manager_mode"],
        rag_retrieval_mode=exp["rag_mode"],
        repo_name=exp["repo"],
    )
    return summary


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run experiment suite from YAML config")
    parser.add_argument("config", help="Path to YAML config file")
    parser.add_argument("--results-dir", default="results", help="Results directory (default: results/)")
    parser.add_argument("--dry-run", action="store_true", help="Print experiment plan without running")
    parser.add_argument("--only", type=str, default=None, help="Comma-separated indices of experiments to run (e.g. 0,2,4)")
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
        print(f"  [{i}] {exp['repo']} | n={exp['n_issues']} | turns={exp['max_turns']} | "
              f"GM={exp['manager_mode']} RAG={exp['rag_mode']} | prefix={prefixes}")

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
    for idx, (i, exp) in enumerate(experiments_to_run):
        print(f"\n{'='*70}")
        print(f"EXPERIMENT {idx+1}/{len(experiments_to_run)}  [{i}] {exp['repo']} "
              f"GM={exp['manager_mode']} RAG={exp['rag_mode']}")
        print(f"{'='*70}")

        t0 = time.time()
        try:
            summary = run_single(exp, api_key, args.results_dir)
            elapsed = time.time() - t0
            if summary:
                summaries.append(summary)
                gm_f1 = summary.get("graph_manager", {}).get("mean_f1", 0)
                rag_f1 = summary.get("rag_agent", {}).get("mean_f1", 0)
                print(f"\n  Completed in {elapsed:.0f}s — GM F1={gm_f1:.3f}, RAG F1={rag_f1:.3f}")
            else:
                print(f"\n  Completed in {elapsed:.0f}s — no summary returned")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  FAILED after {elapsed:.0f}s: {e}")

    # Final summary
    print(f"\n{'='*70}")
    print("SUITE COMPLETE")
    print(f"{'='*70}")
    print(f"Ran {len(summaries)}/{len(experiments_to_run)} experiments successfully\n")

    print(f"{'Repo':<25} {'GM/RAG Mode':<25} {'GM F1':>8} {'RAG F1':>8} {'GM Tok/Iss':>12} {'RAG Tok/Iss':>12}")
    print("-" * 95)
    for s in summaries:
        meta = s.get("_meta", {})
        gm = s.get("graph_manager", {})
        ra = s.get("rag_agent", {})
        print(f"{meta.get('repo_name', '?'):<25} "
              f"{meta.get('manager_mode', '?')}/{meta.get('rag_mode', '?'):<20} "
              f"{gm.get('mean_f1', 0):>8.3f} {ra.get('mean_f1', 0):>8.3f} "
              f"{gm.get('avg_llm_tokens_per_issue', 0):>12,.0f} {ra.get('avg_llm_tokens_per_issue', 0):>12,.0f}")

    print(f"\nResults in: {args.results_dir}/runs/")
    print(f"Config saved to: {config_copy}")
    print(f"Visualize: python visualize_results.py")


if __name__ == "__main__":
    main()
