#!/usr/bin/env python3
"""Utilities for gm_deterministic coefficient tuning artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deterministic_tuning import (
    build_selection_artifact,
    sample_candidate_configs,
    select_best_candidate,
)


def _shorten_keys(config: dict) -> dict:
    mapping = {
        "deterministic_seed_k": "seed_k",
        "deterministic_depth": "depth",
        "deterministic_neighbor_cap": "neighbor_cap",
        "deterministic_min_return_files": "min_return_files",
        "deterministic_score_ratio_cutoff": "score_ratio_cutoff",
        "deterministic_min_score_cutoff": "min_score_cutoff",
        "deterministic_hub_degree_threshold": "hub_degree_threshold",
        "deterministic_hub_penalty_scale": "hub_penalty_scale",
        "deterministic_w_sem": "w_sem",
        "deterministic_w_graph": "w_graph",
        "deterministic_w_conf": "w_conf",
        "deterministic_w_hint": "w_hint",
        "deterministic_w_pen": "w_pen",
    }
    out = {}
    for key, short in mapping.items():
        if key in config:
            out[short] = config[key]
    return out


def _extract_config(row: dict) -> dict:
    if isinstance(row.get("config"), dict):
        return dict(row["config"])
    return {
        key: value
        for key, value in row.items()
        if key.startswith("deterministic_")
    }


def cmd_sample(args) -> int:
    candidates = sample_candidate_configs(args.n_candidates, seed=args.seed)
    payload = {
        "seed": args.seed,
        "n_candidates": args.n_candidates,
        "candidates": candidates,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(candidates)} candidates -> {output_path}")
    return 0


def cmd_select(args) -> int:
    rows = json.loads(Path(args.results_json).read_text(encoding="utf-8"))
    if isinstance(rows, dict) and "results" in rows:
        rows = rows["results"]
    if not isinstance(rows, list):
        raise ValueError("results-json must contain a list or {'results': [...]} payload")

    normalized = []
    for row in rows:
        config = _extract_config(row)
        normalized.append(
            {
                "config_id": row.get("config_id", ""),
                "config": config,
                "train_mean_f1": float(row.get("train_mean_f1", 0.0) or 0.0),
                "train_f1_std": float(row.get("train_f1_std", 0.0) or 0.0),
                "train_runtime_tokens": float(row.get("train_runtime_tokens", 0.0) or 0.0),
                "holdout_scores": dict(row.get("holdout_scores", {})),
            }
        )

    baseline_scores = {
        "psf/requests": args.baseline_requests,
        "pytest-dev/pytest": args.baseline_pytest,
    }

    selected = select_best_candidate(
        candidate_results=normalized,
        baseline_scores=baseline_scores,
        max_drop=args.max_drop,
    )
    selected_config = selected.get("config", {})

    output_config = Path(args.output_config)
    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(
        json.dumps(
            {"deterministic_retrieval": _shorten_keys(selected_config)},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote selected config -> {output_config}")

    if args.output_report:
        artifact = build_selection_artifact(
            candidate_results=normalized,
            baseline_scores=baseline_scores,
            max_drop=args.max_drop,
        )
        report = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            **artifact,
        }
        output_report = Path(args.output_report)
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote selection report -> {output_report}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="gm_deterministic tuning helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="Sample candidate gm_deterministic configs")
    p_sample.add_argument("--seed", type=int, default=17)
    p_sample.add_argument("--n-candidates", type=int, default=60)
    p_sample.add_argument(
        "--output",
        default="results/gm_deterministic_tuning/candidates_v1.json",
    )
    p_sample.set_defaults(func=cmd_sample)

    p_select = sub.add_parser("select", help="Select best candidate from evaluated results")
    p_select.add_argument("--results-json", required=True)
    p_select.add_argument("--baseline-requests", type=float, required=True)
    p_select.add_argument("--baseline-pytest", type=float, required=True)
    p_select.add_argument("--max-drop", type=float, default=0.03)
    p_select.add_argument(
        "--output-config",
        default="configs/gm_deterministic_selected_v1.json",
    )
    p_select.add_argument("--output-report", default="results/gm_deterministic_tuning/selection_v1.json")
    p_select.set_defaults(func=cmd_select)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
