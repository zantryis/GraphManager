#!/usr/bin/env python3
"""Run Phase 1 gm_deterministic tuning (coarse + top-k + holdout guard)."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deterministic_tuning import build_selection_artifact
from src.evaluation import run_experiment


TARGET_REPOS = (
    "pallets/flask",
    "psf/requests",
    "pytest-dev/pytest",
)


def _shorten_config(config: dict) -> dict:
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
    shortened = {}
    for key, short in mapping.items():
        if key in config:
            shortened[short] = config[key]
    return shortened


def _load_strict_cells(matrix_path: Path) -> tuple[dict, dict[str, dict]]:
    payload = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    defaults = dict(payload.get("defaults", {}))
    experiments = payload.get("experiments", [])
    strict: dict[str, dict] = {}

    for exp in experiments:
        if not isinstance(exp, dict):
            continue
        if exp.get("evaluation_track") != "strict_commit_fidelity":
            continue
        repo = str(exp.get("repo", ""))
        if repo not in TARGET_REPOS or repo in strict:
            continue
        merged = dict(defaults)
        merged.update(exp)
        strict[repo] = merged

    missing = sorted(set(TARGET_REPOS) - set(strict))
    if missing:
        raise ValueError(f"Missing strict_commit_fidelity cells in matrix: {', '.join(missing)}")
    return defaults, strict


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_cell(
    *,
    api_key: str,
    cell: dict,
    deterministic_config: dict,
    results_dir: Path,
    note: str,
    seed: int,
) -> dict:
    summary = run_experiment(
        gemini_api_key=api_key,
        n_issues=int(cell.get("n_issues", len(cell.get("instance_ids", [])) or 10)),
        results_dir=str(results_dir),
        create_run_subdir=True,
        source_prefixes=tuple(cell.get("source_prefixes") or ()),
        manager_max_turns=int(cell.get("manager_max_turns", 4)),
        rag_max_turns=int(cell.get("rag_max_turns", 4)),
        task_family=str(cell.get("task_family", "swe-bench")),
        dataset_name=str(cell.get("dataset_name", "SWE-bench/SWE-bench")),
        repo_name=str(cell["repo"]),
        issue_set_id=str(cell.get("issue_set_id", "")) or None,
        suite_id=None,
        repeat_count=1,
        repeat_index=1,
        experiment_notes=note,
        redact_paths_in_issue_text=True,
        evaluation_track="strict_commit_fidelity",
        snapshot_commit=None,
        instance_ids=tuple(cell.get("instance_ids") or ()),
        domain=str(cell.get("domain", "")),
        seed=seed,
        deterministic_seed_k=int(deterministic_config.get("deterministic_seed_k", 8)),
        deterministic_depth=int(deterministic_config.get("deterministic_depth", 2)),
        deterministic_neighbor_cap=int(deterministic_config.get("deterministic_neighbor_cap", 12)),
        deterministic_min_return_files=int(deterministic_config.get("deterministic_min_return_files", 1)),
        deterministic_score_ratio_cutoff=float(
            deterministic_config.get("deterministic_score_ratio_cutoff", 0.70)
        ),
        deterministic_min_score_cutoff=float(
            deterministic_config.get("deterministic_min_score_cutoff", 0.0)
        ),
        deterministic_hub_degree_threshold=int(
            deterministic_config.get("deterministic_hub_degree_threshold", 20)
        ),
        deterministic_hub_penalty_scale=float(
            deterministic_config.get("deterministic_hub_penalty_scale", 0.35)
        ),
        deterministic_w_sem=float(deterministic_config.get("deterministic_w_sem", 0.35)),
        deterministic_w_graph=float(deterministic_config.get("deterministic_w_graph", 0.30)),
        deterministic_w_conf=float(deterministic_config.get("deterministic_w_conf", 0.20)),
        deterministic_w_hint=float(deterministic_config.get("deterministic_w_hint", 0.10)),
        deterministic_w_pen=float(deterministic_config.get("deterministic_w_pen", 0.05)),
        methods=("gm_deterministic",),
    )
    if not isinstance(summary, dict):
        raise RuntimeError("run_experiment returned no summary")
    return summary


def _extract_metrics(summary: dict) -> tuple[float, float, str]:
    gm_d = summary.get("gm_deterministic", {})
    mean_f1 = float(gm_d.get("mean_f1", 0.0) or 0.0)
    runtime_tokens = float(gm_d.get("avg_runtime_tokens_per_issue", 0.0) or 0.0)
    run_id = str(summary.get("_meta", {}).get("run_id", ""))
    return mean_f1, runtime_tokens, run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 gm_deterministic tuning protocol")
    parser.add_argument(
        "--candidates",
        default="results/gm_deterministic_tuning/candidates_v1.json",
        help="Candidate config JSON from tools/tune_gm_deterministic.py sample",
    )
    parser.add_argument(
        "--matrix",
        default="experiments_matrix_v2.yaml",
        help="Experiment matrix file containing strict-track cells",
    )
    parser.add_argument(
        "--results-root",
        default="results/gm_deterministic_tuning",
        help="Root directory for tuning outputs",
    )
    parser.add_argument("--seed", type=int, default=17, help="Base seed for run metadata")
    parser.add_argument("--coarse-limit", type=int, default=60, help="Number of coarse candidates")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k candidates to rerun")
    parser.add_argument("--max-drop", type=float, default=0.03, help="Holdout guard max allowed drop")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    results_root = Path(args.results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    run_outputs = results_root / "eval_runs"
    run_outputs.mkdir(parents=True, exist_ok=True)

    _, strict_cells = _load_strict_cells(Path(args.matrix))
    candidates_payload = _read_json(Path(args.candidates))
    if not isinstance(candidates_payload, dict):
        raise ValueError("Candidate payload must be a JSON object")
    candidates = list(candidates_payload.get("candidates", []))
    if not candidates:
        raise ValueError("No candidates found")
    candidates = candidates[: max(int(args.coarse_limit), 0)]

    coarse_path = results_root / "coarse_flask_v1.json"
    final_path = results_root / "final_candidates_v1.json"
    baseline_path = results_root / "baseline_holdout_v1.json"
    selection_path = results_root / "selection_v1.json"
    selected_config_path = Path("configs/gm_deterministic_selected_v1.json")

    # 1) Holdout baseline (default deterministic config)
    baseline_payload = _read_json(baseline_path)
    if isinstance(baseline_payload, dict) and "baseline_scores" in baseline_payload:
        baseline_scores = dict(baseline_payload["baseline_scores"])
    else:
        baseline_scores = {}
        for repo in ("psf/requests", "pytest-dev/pytest"):
            summary = _run_cell(
                api_key=api_key,
                cell=strict_cells[repo],
                deterministic_config={},
                results_dir=run_outputs,
                note=f"phase1-baseline-{repo}",
                seed=args.seed,
            )
            score, runtime, run_id = _extract_metrics(summary)
            baseline_scores[repo] = score
            baseline_payload = {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "baseline_scores": baseline_scores,
                "runs": baseline_payload.get("runs", {}) if isinstance(baseline_payload, dict) else {},
            }
            baseline_payload["runs"][repo] = {
                "run_id": run_id,
                "mean_f1": score,
                "avg_runtime_tokens_per_issue": runtime,
            }
            _write_json(baseline_path, baseline_payload)

    # 2) Coarse Flask runs
    coarse_payload = _read_json(coarse_path)
    if not isinstance(coarse_payload, dict):
        coarse_payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": []}
    coarse_rows = list(coarse_payload.get("rows", []))
    coarse_by_id = {row.get("config_id"): row for row in coarse_rows if isinstance(row, dict)}

    for idx, candidate in enumerate(candidates, start=1):
        config_id = str(candidate.get("config_id", f"cfg-{idx:04d}"))
        if config_id in coarse_by_id:
            continue
        summary = _run_cell(
            api_key=api_key,
            cell=strict_cells["pallets/flask"],
            deterministic_config=candidate,
            results_dir=run_outputs,
            note=f"phase1-coarse-{config_id}",
            seed=args.seed,
        )
        mean_f1, runtime, run_id = _extract_metrics(summary)
        row = {
            "config_id": config_id,
            "config": {k: v for k, v in candidate.items() if str(k).startswith("deterministic_")},
            "train_mean_f1": mean_f1,
            "train_f1_std": 0.0,
            "train_runtime_tokens": runtime,
            "holdout_scores": {},
            "runs": {"coarse_flask": [run_id]},
        }
        coarse_rows.append(row)
        coarse_by_id[config_id] = row
        coarse_payload["rows"] = sorted(
            coarse_rows,
            key=lambda r: (
                -float(r.get("train_mean_f1", 0.0)),
                float(r.get("train_runtime_tokens", 0.0)),
                str(r.get("config_id", "")),
            ),
        )
        _write_json(coarse_path, coarse_payload)

    ranked = sorted(
        coarse_payload["rows"],
        key=lambda r: (
            -float(r.get("train_mean_f1", 0.0)),
            float(r.get("train_runtime_tokens", 0.0)),
            str(r.get("config_id", "")),
        ),
    )
    top_rows = ranked[: max(int(args.top_k), 0)]
    top_ids = {str(row.get("config_id")) for row in top_rows}

    # 3) Top-k rerun (Flask x3) + holdout checks
    final_payload = _read_json(final_path)
    if not isinstance(final_payload, dict):
        final_payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": []}
    final_rows = [row for row in final_payload.get("rows", []) if isinstance(row, dict)]
    final_by_id = {str(row.get("config_id")): row for row in final_rows}

    for row in top_rows:
        config_id = str(row.get("config_id"))
        if config_id in final_by_id:
            continue
        config = dict(row.get("config", {}))
        repeat_f1 = []
        repeat_runtime = []
        repeat_run_ids = []
        for repeat_idx in range(3):
            summary = _run_cell(
                api_key=api_key,
                cell=strict_cells["pallets/flask"],
                deterministic_config=config,
                results_dir=run_outputs,
                note=f"phase1-topk-{config_id}-repeat-{repeat_idx + 1}",
                seed=args.seed + repeat_idx,
            )
            f1, runtime, run_id = _extract_metrics(summary)
            repeat_f1.append(f1)
            repeat_runtime.append(runtime)
            repeat_run_ids.append(run_id)

        holdout_scores = {}
        holdout_run_ids = {}
        for repo in ("psf/requests", "pytest-dev/pytest"):
            summary = _run_cell(
                api_key=api_key,
                cell=strict_cells[repo],
                deterministic_config=config,
                results_dir=run_outputs,
                note=f"phase1-holdout-{config_id}-{repo}",
                seed=args.seed,
            )
            f1, _, run_id = _extract_metrics(summary)
            holdout_scores[repo] = f1
            holdout_run_ids[repo] = run_id

        final_row = {
            "config_id": config_id,
            "config": config,
            "train_mean_f1": statistics.fmean(repeat_f1) if repeat_f1 else 0.0,
            "train_f1_std": statistics.pstdev(repeat_f1) if len(repeat_f1) > 1 else 0.0,
            "train_runtime_tokens": statistics.fmean(repeat_runtime) if repeat_runtime else 0.0,
            "holdout_scores": holdout_scores,
            "runs": {
                "coarse_flask": row.get("runs", {}).get("coarse_flask", []),
                "topk_flask_repeats": repeat_run_ids,
                "holdout": holdout_run_ids,
            },
        }
        final_rows.append(final_row)
        final_by_id[config_id] = final_row
        final_payload["rows"] = sorted(
            final_rows,
            key=lambda r: (
                -float(r.get("train_mean_f1", 0.0)),
                float(r.get("train_f1_std", 0.0)),
                float(r.get("train_runtime_tokens", 0.0)),
                str(r.get("config_id", "")),
            ),
        )
        _write_json(final_path, final_payload)

    selected_pool = [row for row in final_payload["rows"] if str(row.get("config_id")) in top_ids]
    artifact = build_selection_artifact(
        candidate_results=selected_pool,
        baseline_scores=baseline_scores,
        max_drop=args.max_drop,
    )
    selection_payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "phase": "phase1",
        "coarse_limit": int(args.coarse_limit),
        "top_k": int(args.top_k),
        "baseline_scores": baseline_scores,
        "coarse_results_path": str(coarse_path),
        "final_results_path": str(final_path),
        **artifact,
    }
    _write_json(selection_path, selection_payload)

    selected_config = dict(selection_payload.get("selected", {}).get("config", {}))
    selected_config_path.parent.mkdir(parents=True, exist_ok=True)
    selected_config_path.write_text(
        json.dumps(
            {"deterministic_retrieval": _shorten_config(selected_config)},
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Baseline scores: {baseline_scores}")
    print(f"Selected config id: {selection_payload['selected'].get('config_id')}")
    print(f"Selection artifact: {selection_path}")
    print(f"Selected config: {selected_config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
