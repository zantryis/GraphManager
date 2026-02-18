"""Stable ID helpers for experiment grouping."""

from __future__ import annotations

import hashlib
import json


def build_issue_set_id(repo_name: str, instance_ids: list[str]) -> str:
    """Create a stable identifier for an evaluated issue set."""
    normalized = sorted([iid for iid in instance_ids if iid])
    key = f"{repo_name}|" + "|".join(normalized)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"issues_{digest}"


def build_suite_id(
    *,
    task_family: str,
    dataset_name: str,
    repo_name: str,
    issue_set_id: str,
    n_issues_requested: int,
    source_prefixes: tuple[str, ...],
    manager_max_turns: int,
    rag_max_turns: int,
    evaluation_track: str | None = None,
    snapshot_commit: str | None = None,
    seed: int | None = None,
) -> str:
    """Create a stable suite identifier for grouping comparable runs."""
    key_obj = {
        "task_family": task_family,
        "dataset_name": dataset_name,
        "repo_name": repo_name,
        "issue_set_id": issue_set_id,
        "n_issues_requested": n_issues_requested,
        "source_prefixes": list(source_prefixes) if source_prefixes else [],
        "manager_max_turns": manager_max_turns,
        "rag_max_turns": rag_max_turns,
        "evaluation_track": evaluation_track or "",
        "snapshot_commit": snapshot_commit or "",
        "seed": seed,
    }
    digest = hashlib.sha1(json.dumps(key_obj, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"suite_{digest}"
