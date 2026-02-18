#!/usr/bin/env python3
"""
GraphManager Patch Runner

End-to-end pipeline: retrieval → patch generation → (optional) SWE-bench evaluation.

Usage:
    # Generate patches from a manifest, save to disk (no Docker needed):
    ./.venv/bin/python run_patch.py \
        --manifest patch_manifests/swebench_verified_30.yaml \
        --results-dir results/patch_runs

    # Generate patches AND run SWE-bench harness evaluation (requires Docker):
    ./.venv/bin/python run_patch.py \
        --manifest patch_manifests/swebench_verified_30.yaml \
        --evaluate \
        --results-dir results/patch_runs

Manifest format (YAML):
    dataset_name: SWE-bench/SWE-bench_Verified
    split: test
    instance_ids:
      - pallets__flask-4045
      - psf__requests-1713
    retrieval_method: gm_progressive   # or gm_deterministic
    manager_max_turns: 4
    patch_max_turns: 3
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_MANAGER_MODEL = "gemini-3-flash-preview"
DEFAULT_PATCH_MODEL = "gemini-2.5-pro"


def _check_docker() -> bool:
    """Return True if Docker daemon is reachable."""
    import subprocess
    result = subprocess.run(
        ["docker", "ps"],
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


def _resolve_model_config(manifest: dict) -> tuple[str, str]:
    """Resolve retrieval and patch model names from manifest defaults/overrides."""
    manager_model = str(manifest.get("manager_model") or DEFAULT_MANAGER_MODEL)
    patch_model = str(manifest.get("patch_model") or DEFAULT_PATCH_MODEL)
    return manager_model, patch_model


def _is_transient_api_error(exc: Exception) -> bool:
    """Return True when an API exception looks retryable."""
    msg = str(exc).upper()
    return any(
        token in msg
        for token in (
            "429",
            "RESOURCE_EXHAUSTED",
            "RATE_LIMIT",
            "503",
            "UNAVAILABLE",
            "DEADLINE_EXCEEDED",
            "TIMEOUT",
        )
    )


def _run_with_rate_limit_backoff(
    callable_fn,
    *,
    label: str,
    max_retries: int = 6,
    initial_delay_s: float = 6.0,
    backoff_multiplier: float = 2.0,
    max_delay_s: float = 120.0,
    jitter_s: float = 1.0,
):
    """
    Run callable with retries on transient API limits/failures.

    max_retries counts retry attempts after the initial call.
    """
    delay_s = max(initial_delay_s, 0.0)
    for attempt in range(max_retries + 1):
        try:
            return callable_fn()
        except Exception as exc:
            should_retry = _is_transient_api_error(exc) and attempt < max_retries
            if not should_retry:
                raise
            sleep_s = min(delay_s, max_delay_s) + max(0.0, random.uniform(0.0, max(0.0, jitter_s)))
            print(
                f"    {label} transient API error "
                f"(attempt {attempt + 1}/{max_retries + 1}): {type(exc).__name__}; "
                f"retrying in {sleep_s:.1f}s"
            )
            time.sleep(sleep_s)
            delay_s = min(max_delay_s, max(delay_s * max(backoff_multiplier, 1.0), delay_s + 1.0))


def _run_retrieval(
    issue: dict,
    *,
    graph,
    graph_index,
    rag_index,
    client,
    method: str,
    manager_model: str,
    manager_max_turns: int,
    deterministic_config: dict,
    redact_paths: bool = True,
) -> tuple[list[str], dict]:
    """Run one retrieval method for one issue."""
    from src.evaluation import normalize_file_paths, prepare_issue_text
    from src.path_resolution import canonicalize_file_paths

    query = prepare_issue_text(
        issue.get("problem_statement", ""),
        redact_paths=redact_paths,
    )

    if method == "gm_progressive":
        from src.manager_agent import ManagerAgent
        agent = ManagerAgent(
            graph,
            graph_index,
            client,
            model=manager_model,
            retrieval_mode="progressive",
        )
        files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)

    elif method == "gm_deterministic":
        from src.deterministic_retrieval import DeterministicGraphRetriever
        agent = DeterministicGraphRetriever(
            graph, graph_index,
            **deterministic_config,
        )
        files, tokens = agent.find_relevant_files(query)

    elif method == "rag_progressive":
        from src.rag_baseline import RAGAgent
        agent = RAGAgent(
            rag_index,
            client,
            model=manager_model,
            retrieval_mode="progressive",
        )
        files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)

    else:
        raise ValueError(f"Unsupported retrieval method: {method}")

    graph_file_paths = {
        str(node_id)
        for node_id, node_data in graph.nodes(data=True)
        if node_data.get("type") == "file" and str(node_id).endswith(".py")
    }
    normalized = normalize_file_paths(files)
    canonical = canonicalize_file_paths(normalized, graph_file_paths)
    return canonical, tokens


def run_patch_pipeline(
    manifest_path: str,
    results_dir: str,
    *,
    evaluate: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Run retrieval → patch generation → optional evaluation for all instances in a manifest.

    Returns summary dict with per-instance results and aggregate metrics.
    """
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment / .env")
        sys.exit(1)

    manifest = yaml.safe_load(Path(manifest_path).read_text())
    dataset_name = manifest.get("dataset_name", "SWE-bench/SWE-bench_Verified")
    split = manifest.get("split", "test")
    instance_ids = list(dict.fromkeys(manifest.get("instance_ids", [])))
    retrieval_method = manifest.get("retrieval_method", "gm_progressive")
    manager_max_turns = int(manifest.get("manager_max_turns", 4))
    patch_max_turns = int(manifest.get("patch_max_turns", 3))
    manager_model, patch_model = _resolve_model_config(manifest)
    source_prefixes = manifest.get("source_prefixes") or None
    repo_name = manifest.get("repo_name", "")
    snapshot_commit = manifest.get("snapshot_commit") or None
    rate_limit_max_retries = int(manifest.get("rate_limit_max_retries", 6))
    rate_limit_initial_delay_s = float(manifest.get("rate_limit_initial_delay_s", 6.0))
    rate_limit_backoff_multiplier = float(manifest.get("rate_limit_backoff_multiplier", 2.0))
    rate_limit_max_delay_s = float(manifest.get("rate_limit_max_delay_s", 120.0))
    rate_limit_jitter_s = float(manifest.get("rate_limit_jitter_s", 1.0))
    per_instance_cooldown_s = float(manifest.get("per_instance_cooldown_s", 0.0))
    run_id = time.strftime("%Y%m%d_%H%M%S")

    results_path = Path(results_dir) / "patch_runs" / run_id
    results_path.mkdir(parents=True, exist_ok=True)
    patches_path = results_path / "patches"
    patches_path.mkdir(exist_ok=True)

    print(f"Run ID: {run_id}")
    print(f"Dataset: {dataset_name} ({split})")
    print(f"Instances: {len(instance_ids)}")
    print(f"Retrieval method: {retrieval_method}")
    print(f"Manager model: {manager_model}")
    print(f"Patch model: {patch_model}")
    print(f"Results dir: {results_path}")

    from google import genai
    from src.evaluation import (
        clone_repo,
        load_issues,
        prepare_issue_text,
        validate_commit_context,
    )
    from src.graph_builder import GraphBuilder, GraphIndex
    from src.patch_agent import PatchAgent
    from src.rag_baseline import RAGIndex

    client = genai.Client(api_key=api_key)

    # Load issues
    task_family = "swe-polybench" if "polybench" in dataset_name.lower() else "swe-bench"
    issues = load_issues(
        repo=repo_name,
        n=len(instance_ids),
        task_family=task_family,
        dataset_name=dataset_name,
        instance_ids=instance_ids,
    )
    if not issues:
        print("ERROR: No issues loaded. Aborting.")
        sys.exit(1)

    # Group by repo (issues could be from different repos in a manifest)
    from collections import defaultdict
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        by_repo[issue.get("repo", repo_name)].append(issue)

    per_instance_results = []
    swebench_predictions = {}  # for harness: {instance_id: {...}}

    for repo, repo_issues in by_repo.items():
        print(f"\n=== Repo: {repo} ({len(repo_issues)} issues) ===")
        repo_short = repo.split("/")[-1]
        repo_dir = str(Path.cwd() / f"{repo_short}_repo")
        clone_repo(repo, repo_dir)

        import git as _git
        repo_git = _git.Repo(repo_dir)
        commit = snapshot_commit or repo_issues[0].get("base_commit")
        if commit:
            print(f"  Checking out {commit[:12]}...")
            repo_git.git.checkout(commit, force=True)

        # Build indices
        print("  Building graph and RAG indices...")
        prefixes = tuple(dict.fromkeys(source_prefixes)) if source_prefixes else None
        builder = GraphBuilder(repo_dir, include_prefixes=prefixes)
        graph = builder.build()
        print(f"    Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

        graph_index = GraphIndex(graph, client)
        graph_index.build()

        rag_index = RAGIndex(repo_dir, client, chunk_strategy="function", include_prefixes=prefixes)
        rag_index.build()

        # Validate (raises if empty)
        from src.evaluation import NO_BASE_COMMIT
        setup_costs = {
            "gm_progressive": {"embedding_tokens": int(graph_index.embedding_tokens_estimate)},
            "gm_deterministic": {"embedding_tokens": int(graph_index.embedding_tokens_estimate)},
            "gm_baseline": {"embedding_tokens": int(graph_index.embedding_tokens_estimate)},
            "rag_progressive": {"embedding_tokens": int(rag_index.embedding_tokens_estimate)},
            "rag_baseline": {"embedding_tokens": int(rag_index.embedding_tokens_estimate)},
            "raw_rag_function": {"embedding_tokens": int(rag_index.embedding_tokens_estimate)},
            "raw_rag_fixed": {"embedding_tokens": int(rag_index.embedding_tokens_estimate)},
        }
        validate_commit_context({"graph_file_paths": set(), "setup_costs": setup_costs})

        patch_agent = PatchAgent(repo_dir, client, model=patch_model)
        det_cfg = {
            "seed_k": manifest.get("deterministic_seed_k", 8),
            "depth": manifest.get("deterministic_depth", 2),
            "neighbor_cap": manifest.get("deterministic_neighbor_cap", 12),
        }

        for issue in repo_issues:
            iid = issue["instance_id"]
            print(f"\n  [{iid}]")

            # --- Retrieval ---
            t0 = time.time()
            retrieval_error = None
            if dry_run:
                retrieved_files = issue.get("gold_files", [])[:2]
                retrieval_tokens = {"total_tokens": 0, "stop_reason": "dry_run"}
            else:
                try:
                    retrieved_files, retrieval_tokens = _run_with_rate_limit_backoff(
                        lambda: _run_retrieval(
                            issue,
                            graph=graph,
                            graph_index=graph_index,
                            rag_index=rag_index,
                            client=client,
                            method=retrieval_method,
                            manager_model=manager_model,
                            manager_max_turns=manager_max_turns,
                            deterministic_config=det_cfg,
                        ),
                        label=f"retrieval[{iid}]",
                        max_retries=rate_limit_max_retries,
                        initial_delay_s=rate_limit_initial_delay_s,
                        backoff_multiplier=rate_limit_backoff_multiplier,
                        max_delay_s=rate_limit_max_delay_s,
                        jitter_s=rate_limit_jitter_s,
                    )
                except Exception as exc:
                    retrieval_error = exc
                    retrieved_files = []
                    retrieval_tokens = {
                        "prompt_tokens": 0,
                        "candidate_tokens": 0,
                        "total_tokens": 0,
                        "tool_calls": 0,
                        "stop_reason": f"retrieval_error:{type(exc).__name__}",
                        "error": str(exc),
                    }
                    print(f"    Retrieval failed after retries: {type(exc).__name__}")
            retrieval_time = time.time() - t0
            print(f"    Retrieved: {retrieved_files}")

            # --- Patch generation ---
            t1 = time.time()
            if dry_run:
                patch_text = None
                patch_tokens = {"total_tokens": 0, "stop_reason": "dry_run"}
            elif retrieval_error is not None:
                patch_text = None
                patch_tokens = {
                    "prompt_tokens": 0,
                    "candidate_tokens": 0,
                    "total_tokens": 0,
                    "tool_calls": 0,
                    "stop_reason": "skipped_due_to_retrieval_error",
                }
            else:
                try:
                    patch_text, patch_tokens = _run_with_rate_limit_backoff(
                        lambda: patch_agent.generate_patch(
                            prepare_issue_text(issue.get("problem_statement", "")),
                            retrieved_files,
                            max_turns=patch_max_turns,
                        ),
                        label=f"patch[{iid}]",
                        max_retries=rate_limit_max_retries,
                        initial_delay_s=rate_limit_initial_delay_s,
                        backoff_multiplier=rate_limit_backoff_multiplier,
                        max_delay_s=rate_limit_max_delay_s,
                        jitter_s=rate_limit_jitter_s,
                    )
                except Exception as exc:
                    patch_text = None
                    patch_tokens = {
                        "prompt_tokens": 0,
                        "candidate_tokens": 0,
                        "total_tokens": 0,
                        "tool_calls": 0,
                        "stop_reason": f"patch_error:{type(exc).__name__}",
                        "error": str(exc),
                    }
                    print(f"    Patch generation failed after retries: {type(exc).__name__}")
            patch_time = time.time() - t1

            status = "patched" if patch_text else "no_patch"
            print(f"    Patch status: {status}")

            if per_instance_cooldown_s > 0 and not dry_run:
                time.sleep(per_instance_cooldown_s)

            # Save patch to disk
            if patch_text:
                patch_file = patches_path / f"{iid}.patch"
                patch_file.write_text(patch_text)
            else:
                patch_file = None

            # Build SWE-bench prediction entry
            swebench_predictions[iid] = {
                "instance_id": iid,
                "model_name_or_path": f"graphmanager-{retrieval_method}",
                "model_patch": patch_text or "",
            }

            per_instance_results.append({
                "instance_id": iid,
                "repo": repo,
                "gold_files": issue.get("gold_files", []),
                "retrieved_files": retrieved_files,
                "patch_status": status,
                "patch_file": str(patch_file) if patch_file else None,
                "retrieval_tokens": retrieval_tokens,
                "patch_tokens": patch_tokens,
                "total_tokens": (
                    int(retrieval_tokens.get("total_tokens", 0) or 0)
                    + int(patch_tokens.get("total_tokens", 0) or 0)
                ),
                "retrieval_time_s": round(retrieval_time, 2),
                "patch_time_s": round(patch_time, 2),
            })

    # Save predictions file for SWE-bench harness
    predictions_path = results_path / "predictions.json"
    predictions_path.write_text(json.dumps(swebench_predictions, indent=2))
    print(f"\nPredictions saved: {predictions_path}")

    n_patched = sum(1 for r in per_instance_results if r["patch_status"] == "patched")
    n_total = len(per_instance_results)
    total_tokens = sum(r["total_tokens"] for r in per_instance_results)

    summary = {
        "run_id": run_id,
        "manifest": manifest_path,
        "dataset_name": dataset_name,
        "retrieval_method": retrieval_method,
        "n_instances": n_total,
        "n_patched": n_patched,
        "patch_rate": round(n_patched / n_total, 4) if n_total else 0.0,
        "total_tokens": total_tokens,
        "avg_tokens_per_instance": round(total_tokens / n_total, 1) if n_total else 0.0,
        "predictions_path": str(predictions_path),
        "harness_results": None,
        "per_instance": per_instance_results,
    }

    # --- SWE-bench harness evaluation ---
    if evaluate:
        docker_ok = _check_docker()
        if not docker_ok:
            print("\nWARNING: Docker daemon not reachable. Skipping harness evaluation.")
            print("  Start Docker and rerun with: python run_patch.py --evaluate-only")
            summary["harness_skipped_reason"] = "docker_not_available"
        else:
            print("\n=== Running SWE-bench harness evaluation ===")
            try:
                from swebench.harness.run_evaluation import main as swebench_eval
                harness_run_id = f"graphmanager_{run_id}"
                harness_report_dir = str(results_path / "harness_reports")
                Path(harness_report_dir).mkdir(exist_ok=True)

                swebench_eval(
                    dataset_name=dataset_name,
                    split=split,
                    instance_ids=instance_ids,
                    predictions_path=str(predictions_path),
                    max_workers=2,
                    force_rebuild=False,
                    cache_level="env",
                    clean=False,
                    open_file_limit=4096,
                    run_id=harness_run_id,
                    timeout=300,
                    namespace=None,
                    rewrite_reports=False,
                    modal=False,
                    report_dir=harness_report_dir,
                )

                # Parse results
                report_path = Path(harness_report_dir) / f"{harness_run_id}.json"
                if report_path.exists():
                    harness_results = json.loads(report_path.read_text())
                    resolved = [
                        iid for iid, r in harness_results.items()
                        if isinstance(r, dict) and r.get("resolved")
                    ]
                    summary["harness_results"] = {
                        "report_path": str(report_path),
                        "n_resolved": len(resolved),
                        "resolved_rate": round(len(resolved) / n_total, 4) if n_total else 0.0,
                        "resolved_instances": resolved,
                    }
                    print(f"  Resolved: {len(resolved)}/{n_total} ({summary['harness_results']['resolved_rate']:.1%})")
                else:
                    print(f"  WARNING: harness report not found at {report_path}")
            except Exception as e:
                print(f"  ERROR during harness evaluation: {e}")
                summary["harness_error"] = str(e)

    # Save summary
    summary_path = results_path / "patch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*60}")
    print(f"PATCH RUN COMPLETE")
    print(f"  Instances: {n_total}")
    print(f"  Patched:   {n_patched}/{n_total} ({n_patched/n_total:.1%})" if n_total else "  Patched: 0/0")
    print(f"  Tokens:    {total_tokens:,} total ({summary['avg_tokens_per_instance']:,.0f} avg/instance)")
    if summary.get("harness_results"):
        r = summary["harness_results"]
        print(f"  Resolved:  {r['n_resolved']}/{n_total} ({r['resolved_rate']:.1%})")
    print(f"  Summary:   {summary_path}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="GraphManager patch runner: retrieval + patch generation + optional evaluation"
    )
    parser.add_argument("--manifest", required=True, help="Path to patch manifest YAML")
    parser.add_argument("--results-dir", default="results", help="Results root directory")
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run SWE-bench harness after patch generation (requires Docker)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls; use gold files as retrieved, skip patch generation",
    )
    args = parser.parse_args()

    run_patch_pipeline(
        manifest_path=args.manifest,
        results_dir=args.results_dir,
        evaluate=args.evaluate,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
