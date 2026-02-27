"""Helpers for GraphManager patch-run dashboard status collection."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import yaml

def _load_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_partial_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    rows.append(entry)
    except Exception:
        return []
    return rows


def _extract_method_from_partial(rows: list[dict]) -> str | None:
    for row in rows:
        pred = row.get("prediction")
        if not isinstance(pred, dict):
            continue
        model_name = pred.get("model_name_or_path")
        if isinstance(model_name, str) and model_name:
            if model_name.startswith("graphmanager-"):
                return model_name[len("graphmanager-") :]
            return model_name
    return None


def _latest_mtime_seconds(paths: list[Path]) -> float | None:
    mtimes = []
    for path in paths:
        if path.exists():
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    return max(mtimes) if mtimes else None


def _checkpoint_paths(run_dir: Path) -> list[Path]:
    run_dir = Path(run_dir)
    paths = sorted(run_dir.glob("predictions_worker_*.jsonl"))
    partial = run_dir / "predictions_partial.jsonl"
    if partial.exists():
        paths.append(partial)
    return paths


def _manifest_name_from_path(manifest_path: str | None) -> str | None:
    if not isinstance(manifest_path, str) or not manifest_path:
        return None
    return Path(manifest_path).name


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user.
        return True
    except OSError:
        return False
    return True


def _count_partial_stats(rows: list[dict]) -> tuple[int, int, int]:
    by_instance: dict[str, dict] = {}
    for row in rows:
        instance_id = row.get("instance_id")
        if not isinstance(instance_id, str):
            continue
        by_instance[instance_id] = row

    n_completed = len(by_instance)
    n_patched = 0
    n_apply_failed = 0
    for entry in by_instance.values():
        per_instance = entry.get("per_instance")
        if not isinstance(per_instance, dict):
            continue
        patch_status = per_instance.get("patch_status")
        if patch_status == "patched":
            n_patched += 1
        elif patch_status == "apply_failed":
            n_apply_failed += 1
    return n_completed, n_patched, n_apply_failed


def discover_run_dirs(results_root: Path) -> list[Path]:
    """Discover patch run directories beneath a results root."""
    root = Path(results_root)
    if not root.exists():
        return []

    found: list[Path] = []
    # Avoid recursive globbing into heavy run artifacts (e.g., _repos clones).
    # Walk once, prune aggressively, and only collect immediate children of
    # directories named "patch_runs".
    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)

        if current.name == "_repos":
            dirnames.clear()
            continue

        if current.name == "patch_runs":
            for child in current.iterdir():
                if child.is_dir():
                    found.append(child)
            # We already captured run dirs under this patch_runs root.
            dirnames.clear()
            continue

    # newest first
    found.sort(
        key=lambda p: _latest_mtime_seconds(
            [p / "patch_summary.json", p / "predictions.json", *_checkpoint_paths(p)]
        )
        or 0.0,
        reverse=True,
    )
    return found


def build_run_record(run_dir: Path, *, stale_after_minutes: float = 15.0, now_ts: float | None = None) -> dict:
    """Build a run status record for dashboard presentation."""
    run_dir = Path(run_dir)
    run_id = run_dir.name

    summary_path = run_dir / "patch_summary.json"
    run_meta_path = run_dir / "run_meta.json"
    predictions_path = run_dir / "predictions.json"
    checkpoint_paths = _checkpoint_paths(run_dir)
    summary = _load_json(summary_path) if summary_path.exists() else None
    run_meta = _load_json(run_meta_path) if run_meta_path.exists() else None
    partial_rows: list[dict] = []
    for checkpoint_path in checkpoint_paths:
        partial_rows.extend(_load_partial_entries(checkpoint_path))

    n_completed_partial, n_patched_partial, n_apply_failed_partial = _count_partial_stats(partial_rows)
    method_partial = _extract_method_from_partial(partial_rows)

    latest_mtime = _latest_mtime_seconds([summary_path, predictions_path, *checkpoint_paths])
    meta_mtime = _latest_mtime_seconds([run_meta_path])
    latest_seen_ts = _latest_mtime_seconds([summary_path, predictions_path, *checkpoint_paths, run_meta_path])
    now = float(now_ts if now_ts is not None else time.time())
    age_minutes = None if latest_mtime is None else round((now - latest_mtime) / 60.0, 1)
    seen_age_minutes = None if latest_seen_ts is None else round((now - latest_seen_ts) / 60.0, 1)
    meta_age_minutes = None if meta_mtime is None else round((now - meta_mtime) / 60.0, 1)
    meta_n_instances = int(run_meta.get("n_instances_planned") or 0) if run_meta else 0
    meta_retrieval_method = str(run_meta.get("retrieval_method") or "") if run_meta else ""
    meta_manifest = str(run_meta.get("manifest") or "") if run_meta else ""
    meta_repo_name = str(run_meta.get("repo_name") or "") if run_meta else ""
    raw_meta_pid = run_meta.get("pid") if run_meta else None
    meta_pid = int(raw_meta_pid) if isinstance(raw_meta_pid, int) else None
    meta_pid_alive = _is_pid_alive(meta_pid) if meta_pid is not None else None

    if summary:
        n_instances = int(summary.get("n_instances") or 0)
        n_completed = int(summary.get("n_instances") or len(summary.get("per_instance") or []))
        n_patched = int(summary.get("n_patched") or 0)
        n_apply_failed = int(summary.get("n_apply_failed") or 0)
        retrieval_method = str(summary.get("retrieval_method") or meta_retrieval_method or method_partial or "unknown")
        repo_name = str(summary.get("repo_name") or meta_repo_name or "")
        harness = summary.get("harness_results") or {}
        n_resolved = int(harness.get("n_resolved") or 0)
        resolved_rate = float(harness.get("resolved_rate") or 0.0)
        status = "complete"
        total_cost_tokens = summary.get("total_cost_tokens")
        cost_per_resolved_issue = summary.get("cost_per_resolved_issue")
        harness_run_id = summary.get("harness_run_id")
        manifest_path = str(summary.get("manifest") or meta_manifest or "")
    else:
        n_instances = meta_n_instances
        n_completed = n_completed_partial
        n_patched = n_patched_partial
        n_apply_failed = n_apply_failed_partial
        retrieval_method = meta_retrieval_method or method_partial or "unknown"
        n_resolved = None
        resolved_rate = None
        total_cost_tokens = None
        cost_per_resolved_issue = None
        harness_run_id = None
        manifest_path = meta_manifest
        repo_name = meta_repo_name
        if n_completed == 0:
            # Fresh run_meta without progress can be either setup/queued or an abandoned attempt.
            if meta_pid is not None and meta_pid_alive is False:
                status = "stalled"
            elif seen_age_minutes is not None and seen_age_minutes > stale_after_minutes:
                status = "stalled"
            else:
                status = "not_started"
        elif age_minutes is not None and age_minutes > stale_after_minutes:
            status = "stalled"
        elif meta_pid is not None and meta_pid_alive is False:
            status = "stalled"
        else:
            status = "running"

    progress_pct = round((n_completed / n_instances) * 100.0, 1) if n_instances > 0 else None
    manifest_name = _manifest_name_from_path(manifest_path)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "repo_name": repo_name or None,
        "retrieval_method": retrieval_method,
        "status": status,
        "n_instances": n_instances,
        "n_completed": n_completed,
        "n_patched": n_patched,
        "n_apply_failed": n_apply_failed,
        "n_resolved": n_resolved,
        "resolved_rate": resolved_rate,
        "progress_pct": progress_pct,
        "total_cost_tokens": total_cost_tokens,
        "cost_per_resolved_issue": cost_per_resolved_issue,
        "harness_run_id": harness_run_id,
        "updated_age_minutes": age_minutes,
        "seen_age_minutes": seen_age_minutes,
        "meta_age_minutes": meta_age_minutes,
        "summary_path": str(summary_path) if summary_path.exists() else None,
        "manifest_path": manifest_path or None,
        "manifest_name": manifest_name,
        "last_update_ts": latest_mtime,
        "last_seen_ts": latest_seen_ts,
        "meta_pid": meta_pid,
        "meta_pid_alive": meta_pid_alive,
    }


def collect_dashboard_status(
    results_root: Path,
    *,
    stale_after_minutes: float = 15.0,
    active_only: bool = False,
    include_complete: bool = True,
    include_stale: bool = True,
    pending_grace_minutes: float = 30.0,
) -> list[dict]:
    """Collect dashboard records for all discovered runs (newest first)."""
    runs = discover_run_dirs(results_root)
    now = time.time()
    records = [build_run_record(run_dir, stale_after_minutes=stale_after_minutes, now_ts=now) for run_dir in runs]

    # Deduplicate in-flight duplicate attempts for the same manifest (keep freshest).
    deduped: list[dict] = []
    by_manifest: dict[str, dict] = {}
    for record in records:
        manifest_path = record.get("manifest_path")
        if not isinstance(manifest_path, str) or not manifest_path:
            deduped.append(record)
            continue

        prior = by_manifest.get(manifest_path)
        if prior is None:
            by_manifest[manifest_path] = record
            continue

        prior_status = prior.get("status") or "stalled"
        record_status = record.get("status") or "stalled"

        # When one run is complete and the other is not, keep BOTH records.
        # This lets count_unique_manifests_complete see the completed run while
        # active-only views (include_complete=False) still surface the live attempt.
        # Without this, a newer partial/stalled dir silently hides the completed run
        # in the completion counter.
        if (prior_status == "complete") != (record_status == "complete"):
            deduped.append(record)  # add the non-winning record directly
            # prior stays in by_manifest unchanged; do not overwrite
            if record_status == "complete":
                by_manifest[manifest_path] = record
                # prior (non-complete) already appended above; done
            continue

        prior_ts = float(prior.get("last_seen_ts") or 0.0)
        record_ts = float(record.get("last_seen_ts") or 0.0)
        if record_ts >= prior_ts:
            by_manifest[manifest_path] = record

    deduped.extend(by_manifest.values())
    deduped.sort(key=lambda r: float(r.get("last_seen_ts") or 0.0), reverse=True)

    filtered: list[dict] = []
    for record in deduped:
        status = str(record.get("status") or "")
        seen_age = record.get("seen_age_minutes")
        seen_age_num = float(seen_age) if isinstance(seen_age, (int, float)) else None

        if active_only:
            if status == "running":
                filtered.append(record)
                continue
            if status == "not_started":
                # keep only newly created pending runs, hide orphaned/stale placeholders
                if seen_age_num is not None and seen_age_num <= pending_grace_minutes:
                    filtered.append(record)
                continue
            if status == "complete" and include_complete:
                filtered.append(record)
                continue
            if status == "stalled" and include_stale:
                filtered.append(record)
                continue
            continue

        if status == "complete" and not include_complete:
            continue
        if status == "stalled" and not include_stale:
            continue
        if status == "not_started" and not include_stale:
            if seen_age_num is None or seen_age_num > pending_grace_minutes:
                continue
        filtered.append(record)

    filtered.sort(key=lambda r: float(r.get("last_seen_ts") or 0.0), reverse=True)
    return filtered


def summarize_dashboard_runs(runs: list[dict]) -> dict:
    """Build aggregate counters for the current dashboard run set."""
    status_counts = {"running": 0, "not_started": 0, "complete": 0, "stalled": 0}
    n_instances_total = 0
    n_completed_total = 0
    n_patched_total = 0

    for run in runs:
        status = str(run.get("status") or "not_started")
        if status in status_counts:
            status_counts[status] += 1
        n_instances_total += int(run.get("n_instances") or 0)
        n_completed_total += int(run.get("n_completed") or 0)
        n_patched_total += int(run.get("n_patched") or 0)

    completed_rate_total = (
        float(n_completed_total) / float(n_instances_total) if n_instances_total > 0 else None
    )
    patched_rate_total = (
        float(n_patched_total) / float(n_instances_total) if n_instances_total > 0 else None
    )

    return {
        "run_count": len(runs),
        "status_counts": status_counts,
        "n_instances_total": n_instances_total,
        "n_completed_total": n_completed_total,
        "n_patched_total": n_patched_total,
        "completed_rate_total": completed_rate_total,
        "patched_rate_total": patched_rate_total,
    }


def count_unique_manifests_complete(runs: list[dict]) -> int:
    """Count distinct (repo_name, retrieval_method) pairs that have status='complete'.

    Deduplicates multiple run directories for the same manifest (e.g. from parallel
    pool race conditions) so the count reflects manifests, not run directories.
    """
    return len(
        {
            (r["repo_name"], r["retrieval_method"])
            for r in runs
            if r.get("status") == "complete" and r.get("repo_name")
        }
    )


def build_retrieval_status(
    results_root: Path,
    target_repos: list[str],
    target_methods: list[str],
) -> dict:
    """Build retrieval status grid for dashboard.

    Returns:
        {
          "grid": {repo: {method: {"status": "done|pending", "f1": float|None, "run_id": str|None}}},
          "repos": target_repos,
          "methods": target_methods,
          "summary": {"n_done": int, "n_total": int, "n_in_progress": int, "n_pending": int, "eta_seconds": None}
        }
    """
    root = Path(results_root)
    runs_dir = root / "runs"

    # Initialize grid: all pending
    grid: dict[str, dict[str, dict]] = {
        repo: {
            method: {"status": "pending", "f1": None, "run_id": None}
            for method in target_methods
        }
        for repo in target_repos
    }

    target_repos_set = set(target_repos)
    target_methods_set = set(target_methods)

    if runs_dir.exists():
        for summary_path in sorted(runs_dir.glob("*/summary.json")):
            data = _load_json(summary_path)
            if not data:
                continue
            meta = data.get("_meta", {})
            if not isinstance(meta, dict):
                continue
            repo_name = str(meta.get("repo_name") or "")
            if repo_name not in target_repos_set:
                continue
            enabled_methods = meta.get("enabled_methods") or []
            run_id = str(meta.get("run_id") or summary_path.parent.name)

            for method in enabled_methods:
                if method not in target_methods_set:
                    continue
                method_data = data.get(method)
                if not isinstance(method_data, dict):
                    continue
                if int(method_data.get("n_success", 0)) == 0:
                    continue
                f1 = method_data.get("mean_f1")
                current = grid[repo_name][method]
                # Keep latest run (run_id is YYYYMMDD_HHMMSS — lexicographic order works)
                if current["status"] == "done" and run_id <= (current.get("run_id") or ""):
                    continue
                grid[repo_name][method] = {
                    "status": "done",
                    "f1": float(f1) if f1 is not None else None,
                    "run_id": run_id,
                }

    # Count in-progress: run dirs with graph.json but no summary.json
    n_in_progress = 0
    if runs_dir.exists():
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            if (run_dir / "summary.json").exists():
                continue
            if (run_dir / "graph.json").exists():
                n_in_progress += 1

    n_total = len(target_repos) * len(target_methods)
    n_done = sum(
        1
        for repo in target_repos
        for method in target_methods
        if grid[repo][method]["status"] == "done"
    )

    return {
        "grid": grid,
        "repos": list(target_repos),
        "methods": list(target_methods),
        "summary": {
            "n_done": n_done,
            "n_total": n_total,
            "n_in_progress": n_in_progress,
            "n_pending": n_total - n_done,
            "eta_seconds": None,  # Computed by server layer from completion rate
        },
    }


def load_campaign_state(campaigns_dir: Path) -> list[dict]:
    """Load all campaign state files and return list of campaign dicts.

    Returns [{"campaign_name": str, "steps": [{"name", "description", "status", ...}]}]
    For running steps, elapsed_s is computed dynamically from started_at.
    """
    import datetime as _dt

    campaigns_dir = Path(campaigns_dir)
    if not campaigns_dir.exists():
        return []

    now = _dt.datetime.now()

    result: list[dict] = []
    for state_path in sorted(campaigns_dir.glob("*_state.json")):
        data = _load_json(state_path)
        if not data:
            continue
        campaign_name = str(data.get("campaign_name") or state_path.stem.replace("_state", ""))
        steps = data.get("steps")
        if not isinstance(steps, list):
            steps = []
        enriched = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            s = dict(s)  # copy to avoid mutating cached data
            # Compute elapsed_s dynamically for running steps
            if s.get("status") == "running" and s.get("started_at") and not s.get("elapsed_s"):
                try:
                    started = _dt.datetime.fromisoformat(s["started_at"])
                    s["elapsed_s"] = (now - started).total_seconds()
                except Exception:
                    pass
            enriched.append(s)
        result.append({
            "campaign_name": campaign_name,
            "updated_at": str(data.get("updated_at") or ""),
            "steps": enriched,
        })

    return result


def load_manifest_plan_summary(manifest_list_path: Path, *, root_dir: Path | None = None) -> dict:
    """Load planned manifest/instance totals from a manifest-list text file."""
    list_path = Path(manifest_list_path)
    if not list_path.exists():
        return {
            "manifest_list_path": str(list_path),
            "exists": False,
            "n_manifests_planned": 0,
            "n_instances_planned": 0,
            "n_load_failed": 0,
            "per_method": {},
        }

    root = Path(root_dir) if root_dir is not None else list_path.parent
    manifest_paths: list[Path] = []
    for raw in list_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        p = Path(line)
        if not p.is_absolute():
            p = (root / p).resolve()
        manifest_paths.append(p)

    n_instances_planned = 0
    n_load_failed = 0
    per_method: dict[str, dict[str, int]] = {}
    for manifest_path in manifest_paths:
        try:
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:
            n_load_failed += 1
            continue
        if not isinstance(payload, dict):
            n_load_failed += 1
            continue

        method = str(payload.get("retrieval_method") or "unknown")
        instance_ids = payload.get("instance_ids")
        if isinstance(instance_ids, list):
            n_manifest_instances = len(instance_ids)
        else:
            raw_n = payload.get("n_instances")
            n_manifest_instances = int(raw_n) if isinstance(raw_n, int) else 0

        n_instances_planned += n_manifest_instances
        method_summary = per_method.setdefault(method, {"n_manifests": 0, "n_instances": 0})
        method_summary["n_manifests"] += 1
        method_summary["n_instances"] += n_manifest_instances

    return {
        "manifest_list_path": str(list_path),
        "exists": True,
        "n_manifests_planned": len(manifest_paths),
        "n_instances_planned": n_instances_planned,
        "n_load_failed": n_load_failed,
        "per_method": per_method,
    }
