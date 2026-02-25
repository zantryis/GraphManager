#!/usr/bin/env python3
"""Parallel manifest runner (repo-safe).

Runs multiple manifests concurrently across repos, while ensuring only one
manifest per repo is active at a time to avoid git checkout contention.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import yaml


def _abs(path: str | Path) -> str:
    return str(Path(path).resolve())


def _is_manifest_completed(manifest_path: Path, results_dir: Path) -> bool:
    target = _abs(manifest_path)
    patch_runs = results_dir / "patch_runs"
    if not patch_runs.exists():
        return False
    for summary_path in patch_runs.glob("*/patch_summary.json"):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        manifest = payload.get("manifest")
        if not isinstance(manifest, str):
            continue
        if _abs(manifest) == target:
            return True
    return False


def _load_manifest_meta(path: Path) -> tuple[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repo = str(data.get("repo_name") or "unknown")
    method = str(data.get("retrieval_method") or "unknown")
    return repo, method


def _latest_run_activity_ts(run_dir: Path) -> float:
    ts = 0.0
    paths = [run_dir / "run_meta.json", run_dir / "predictions_partial.jsonl", run_dir / "predictions.json"]
    paths.extend(sorted(run_dir.glob("predictions_worker_*.jsonl")))
    for path in paths:
        if not path.exists():
            continue
        try:
            ts = max(ts, path.stat().st_mtime)
        except OSError:
            continue
    return ts


def _find_latest_incomplete_run_dir(manifest_path: Path, results_dir: Path) -> Path | None:
    target = _abs(manifest_path)
    patch_runs = results_dir / "patch_runs"
    if not patch_runs.exists():
        return None

    candidates: list[tuple[float, Path]] = []
    for run_dir in patch_runs.iterdir():
        if not run_dir.is_dir():
            continue
        if (run_dir / "patch_summary.json").exists():
            continue
        run_meta = run_dir / "run_meta.json"
        if not run_meta.exists():
            continue
        try:
            payload = json.loads(run_meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        manifest = payload.get("manifest")
        if not isinstance(manifest, str):
            continue
        if _abs(manifest) != target:
            continue
        candidates.append((_latest_run_activity_ts(run_dir), run_dir))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _build_run_patch_cmd(
    *,
    root: Path,
    manifest: Path,
    results_dir: Path,
    manifest_timeout_s: int,
    resume_run_dir: Path | None,
    execution_mode: str,
    evaluate_mode: str,
    run_workers: int,
) -> list[str]:
    cmd = [
        "env",
        "PYTHONUNBUFFERED=1",
        str(root / ".venv/bin/python"),
        "-u",
        str(root / "run_patch.py"),
        "--manifest",
        str(manifest),
        "--results-dir",
        str(results_dir),
    ]
    if evaluate_mode == "stage12":
        cmd.append("--evaluate")
    if evaluate_mode == "stage12" and execution_mode == "modal":
        cmd.append("--modal")
    if resume_run_dir is not None:
        cmd.extend(
            [
                "--resume",
                "--run-dir",
                str(resume_run_dir),
            ]
        )
    if int(run_workers) > 1:
        cmd.extend(["--workers", str(int(run_workers))])

    if manifest_timeout_s > 0:
        return [
            "timeout",
            "--signal=TERM",
            "--kill-after=30s",
            f"{manifest_timeout_s}s",
            *cmd,
        ]
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run patch manifests in parallel across repos")
    parser.add_argument("--manifest-list", required=True, help="Path to text file with one manifest path per line")
    parser.add_argument("--results-dir", default="results/v2_full_runs", help="Results root passed to run_patch.py")
    parser.add_argument("--max-parallel-repos", type=int, default=3, help="Number of repos to run concurrently")
    parser.add_argument(
        "--manifest-timeout-s",
        type=int,
        default=0,
        help="Per-manifest timeout in seconds (<=0 disables manifest timeout).",
    )
    parser.add_argument(
        "--resume-incomplete",
        action="store_true",
        help="Resume latest incomplete run_dir per manifest when available.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["modal", "local"],
        default="modal",
        help="Harness execution mode passed to run_patch.py (default: modal).",
    )
    parser.add_argument(
        "--evaluate-mode",
        choices=["stage12", "stage1_only"],
        default="stage12",
        help="Run both patch+evaluate (`stage12`) or generate patches only (`stage1_only`).",
    )
    parser.add_argument(
        "--run-workers",
        type=int,
        default=1,
        help="Issue-level worker count passed to each run_patch.py invocation.",
    )
    parser.add_argument("--log", default=None, help="Global runner log path")
    parser.add_argument("--failure-log", default=None, help="Failure log path")
    parser.add_argument("--exclude-repo", action="append", default=[], help="Repo name(s) to exclude")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    results_dir = (root / args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = Path(args.log) if args.log else (root / f"logs/v2_repo_pool_{ts}.log")
    failure_log_path = Path(args.failure_log) if args.failure_log else (root / f"logs/v2_repo_pool_failures_{ts}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lock = threading.Lock()

    def log(msg: str, *, also_fail: bool = False) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {msg}\n"
        with lock:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            if also_fail:
                with failure_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line)

    manifests: list[Path] = []
    for raw in Path(args.manifest_list).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        manifests.append(path)

    queues: dict[str, deque[tuple[Path, Path | None]]] = defaultdict(deque)
    skipped = 0
    for manifest in manifests:
        repo, method = _load_manifest_meta(manifest)
        if repo in set(args.exclude_repo):
            skipped += 1
            log(f"SKIP excluded repo={repo}: {manifest}")
            continue
        if _is_manifest_completed(manifest, results_dir):
            skipped += 1
            log(f"SKIP completed repo={repo} method={method}: {manifest}")
            continue
        resume_run_dir: Path | None = None
        if args.resume_incomplete:
            resume_run_dir = _find_latest_incomplete_run_dir(manifest, results_dir)
            if resume_run_dir is not None:
                log(
                    f"RESUME candidate repo={repo} method={method} "
                    f"manifest={manifest} run_dir={resume_run_dir}"
                )
        queues[repo].append((manifest, resume_run_dir))

    available_repos: deque[str] = deque([repo for repo, q in queues.items() if q])
    total_pending = sum(len(q) for q in queues.values())
    log(
        "RUNNER START "
        f"manifests_total={len(manifests)} pending={total_pending} skipped={skipped} "
        f"repos={len(available_repos)} max_parallel_repos={args.max_parallel_repos} "
        f"manifest_timeout_s={args.manifest_timeout_s} execution_mode={args.execution_mode} "
        f"evaluate_mode={args.evaluate_mode} run_workers={max(1, int(args.run_workers))}"
    )

    stats = {"ok": 0, "fail": 0, "timeout": 0}

    def worker(worker_id: int) -> None:
        nonlocal available_repos
        while True:
            with lock:
                repo = available_repos.popleft() if available_repos else None
            if repo is None:
                return

            manifest, resume_run_dir = queues[repo].popleft()
            repo_name, method = _load_manifest_meta(manifest)
            run_mode = "resume" if resume_run_dir is not None else "fresh"
            log(
                f"W{worker_id} START repo={repo_name} method={method} "
                f"mode={run_mode} manifest={manifest}"
            )

            cmd = _build_run_patch_cmd(
                root=root,
                manifest=manifest,
                results_dir=results_dir,
                manifest_timeout_s=args.manifest_timeout_s,
                resume_run_dir=resume_run_dir,
                execution_mode=args.execution_mode,
                evaluate_mode=args.evaluate_mode,
                run_workers=max(1, int(args.run_workers)),
            )

            proc = subprocess.run(
                cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            with lock:
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(proc.stdout)

            timed_out = args.manifest_timeout_s > 0 and proc.returncode == 124
            if proc.returncode == 0:
                stats["ok"] += 1
                log(f"W{worker_id} DONE repo={repo_name} method={method} manifest={manifest}")
            elif timed_out:
                stats["timeout"] += 1
                log(
                    f"W{worker_id} TIMEOUT repo={repo_name} method={method} rc=124 manifest={manifest}",
                    also_fail=True,
                )
            else:
                stats["fail"] += 1
                log(
                    f"W{worker_id} FAIL repo={repo_name} method={method} rc={proc.returncode} manifest={manifest}",
                    also_fail=True,
                )

            with lock:
                if queues[repo]:
                    available_repos.append(repo)

    n_workers = max(1, args.max_parallel_repos)
    threads = [threading.Thread(target=worker, args=(i + 1,), daemon=True) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log(
        "RUNNER COMPLETE "
        f"ok={stats['ok']} timeout={stats['timeout']} fail={stats['fail']} "
        f"skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
