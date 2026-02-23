"""Helpers for deterministic SWE-bench Verified patch-study split generation."""

from __future__ import annotations

import random


def allocate_verified_split(
    *,
    available_ids_by_repo: dict[str, list[str]],
    anchor_repos: list[str],
    capped_repos: dict[str, int],
    seed: int,
    target_n: int,
) -> dict[str, list[str]]:
    """
    Allocate a deterministic split with anchor continuity and capped extras.

    - Anchor repos include all available IDs.
    - Capped repos include up to `cap` IDs sampled deterministically.
    - Raises ValueError when the assembled split does not match target_n.
    """
    rng = random.Random(seed)
    selected: dict[str, list[str]] = {}

    for repo in anchor_repos:
        ids = sorted(dict.fromkeys(available_ids_by_repo.get(repo, [])))
        if not ids:
            raise ValueError(f"Anchor repo has no available IDs: {repo}")
        selected[repo] = ids

    for repo, cap in capped_repos.items():
        if cap <= 0:
            continue
        ids = sorted(dict.fromkeys(available_ids_by_repo.get(repo, [])))
        if not ids:
            raise ValueError(f"Capped repo has no available IDs: {repo}")
        if len(ids) <= cap:
            selected[repo] = ids
            continue
        chosen = sorted(rng.sample(ids, cap))
        selected[repo] = chosen

    total = sum(len(ids) for ids in selected.values())
    if total != int(target_n):
        raise ValueError(f"Target N mismatch: expected {target_n}, got {total}")
    return selected


def flatten_split(selected_ids_by_repo: dict[str, list[str]]) -> list[str]:
    """Flatten a repo-keyed split into sorted unique instance IDs."""
    flattened = []
    for repo in sorted(selected_ids_by_repo):
        for iid in sorted(dict.fromkeys(selected_ids_by_repo[repo])):
            flattened.append(iid)
    return flattened

