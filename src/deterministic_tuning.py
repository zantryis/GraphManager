"""Sampling and selection utilities for gm_deterministic tuning."""

from __future__ import annotations

import random


def _sample_weights(rng: random.Random) -> dict[str, float]:
    """Sample deterministic weights constrained to sum to 1 and each <= 0.7."""
    keys = ["deterministic_w_sem", "deterministic_w_graph", "deterministic_w_conf", "deterministic_w_hint", "deterministic_w_pen"]
    for _ in range(10_000):
        raw = [rng.random() + 1e-6 for _ in range(5)]
        total = sum(raw)
        weights = [value / total for value in raw]
        if all(value <= 0.7 for value in weights):
            rounded = [round(value, 6) for value in weights]
            # Repair rounding drift deterministically.
            delta = 1.0 - sum(rounded)
            rounded[-1] = round(rounded[-1] + delta, 6)
            return dict(zip(keys, rounded))
    raise RuntimeError("Failed to sample valid deterministic weights")


def sample_candidate_configs(n_candidates: int, seed: int) -> list[dict]:
    """Sample deterministic retrieval candidate configurations."""
    rng = random.Random(seed)
    candidates = []
    for idx in range(max(int(n_candidates), 0)):
        cfg = {
            "config_id": f"cfg-{idx + 1:04d}",
            "deterministic_seed_k": rng.choice([6, 8, 10]),
            "deterministic_depth": rng.choice([1, 2, 3]),
            "deterministic_neighbor_cap": rng.choice([8, 12, 16]),
            "deterministic_min_return_files": 1,
            "deterministic_score_ratio_cutoff": round(rng.uniform(0.55, 0.85), 6),
            "deterministic_min_score_cutoff": round(rng.uniform(0.0, 0.15), 6),
            "deterministic_hub_degree_threshold": rng.choice([12, 16, 20, 24, 30]),
            "deterministic_hub_penalty_scale": round(rng.uniform(0.1, 0.6), 6),
        }
        cfg.update(_sample_weights(rng))
        candidates.append(cfg)
    return candidates


def passes_stability_guard(
    *,
    holdout_scores: dict[str, float],
    baseline_scores: dict[str, float],
    max_drop: float,
) -> bool:
    for repo, baseline in baseline_scores.items():
        if repo not in holdout_scores:
            return False
        if holdout_scores[repo] < (baseline - max_drop):
            return False
    return True


def _selection_sort_key(row: dict) -> tuple[float, float, float, str]:
    return (
        -float(row.get("train_mean_f1", 0.0)),
        float(row.get("train_f1_std", 0.0)),
        float(row.get("train_runtime_tokens", 0.0)),
        str(row.get("config_id", "")),
    )


def compute_holdout_deltas(
    *,
    holdout_scores: dict[str, float],
    baseline_scores: dict[str, float],
) -> dict[str, float]:
    """Compute holdout deltas vs baseline by repo (candidate - baseline)."""
    deltas = {}
    for repo, baseline in baseline_scores.items():
        if repo in holdout_scores:
            deltas[repo] = float(holdout_scores[repo]) - float(baseline)
    return deltas


def build_candidate_leaderboard(
    *,
    candidate_results: list[dict],
    baseline_scores: dict[str, float],
    max_drop: float,
) -> list[dict]:
    """
    Build a sorted candidate leaderboard with guard outcomes.

    The returned leaderboard is sorted using the exact selection ordering.
    """
    enriched = []
    for row in candidate_results:
        holdout_scores = dict(row.get("holdout_scores", {}))
        enriched_row = {
            **row,
            "passes_stability_guard": passes_stability_guard(
                holdout_scores=holdout_scores,
                baseline_scores=baseline_scores,
                max_drop=max_drop,
            ),
            "holdout_deltas": compute_holdout_deltas(
                holdout_scores=holdout_scores,
                baseline_scores=baseline_scores,
            ),
        }
        enriched.append(enriched_row)

    return sorted(enriched, key=_selection_sort_key)


def build_selection_artifact(
    *,
    candidate_results: list[dict],
    baseline_scores: dict[str, float],
    max_drop: float = 0.03,
) -> dict:
    """
    Build a locked tuning artifact with selected config + full leaderboard.
    """
    leaderboard = build_candidate_leaderboard(
        candidate_results=candidate_results,
        baseline_scores=baseline_scores,
        max_drop=max_drop,
    )
    passing = [row for row in leaderboard if row.get("passes_stability_guard")]
    if not passing:
        raise ValueError("No candidates passed stability guard")

    selected = passing[0]
    return {
        "protocol_version": "gm_deterministic_tuning_v1",
        "selection_rule": (
            "highest train_mean_f1 among guard-passing candidates; "
            "tie-break by lower train_f1_std, then lower train_runtime_tokens, then config_id"
        ),
        "max_drop": float(max_drop),
        "baseline_scores": dict(baseline_scores),
        "n_candidates": len(candidate_results),
        "n_guard_passing": len(passing),
        "selected": selected,
        "leaderboard": leaderboard,
    }


def select_best_candidate(
    *,
    candidate_results: list[dict],
    baseline_scores: dict[str, float],
    max_drop: float = 0.03,
) -> dict:
    """Select the best candidate passing stability guard with tie-breakers."""
    passing = [
        row
        for row in candidate_results
        if passes_stability_guard(
            holdout_scores=row.get("holdout_scores", {}),
            baseline_scores=baseline_scores,
            max_drop=max_drop,
        )
    ]
    if not passing:
        raise ValueError("No candidates passed stability guard")
    return sorted(passing, key=_selection_sort_key)[0]
