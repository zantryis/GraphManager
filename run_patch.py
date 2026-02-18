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
    patch_max_output_tokens: 4096
    patch_max_file_chars: 8000
"""

import argparse
import httpx
import json
import os
import random
import subprocess
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
    retry_feedback: str | None = None,
) -> tuple[list[str], dict]:
    """Run one retrieval method for one issue."""
    from src.evaluation import normalize_file_paths, prepare_issue_text
    from src.path_resolution import canonicalize_file_paths

    query = prepare_issue_text(
        issue.get("problem_statement", ""),
        redact_paths=redact_paths,
    )
    if retry_feedback:
        query = f"{query}\n\n## Retrieval Retry Feedback\n{retry_feedback}"

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


def _tokenish_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _merge_token_usages(usages: list[dict]) -> dict:
    """Merge token usage maps by summing numeric fields."""
    if not usages:
        return {}

    merged: dict = {}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, dict):
                existing = merged.get(key, {})
                if isinstance(existing, dict):
                    nested = dict(existing)
                else:
                    nested = {}
                for sub_key, sub_val in value.items():
                    if _tokenish_number(sub_val):
                        nested[sub_key] = nested.get(sub_key, 0) + sub_val
                    else:
                        nested[sub_key] = sub_val
                merged[key] = nested
            elif _tokenish_number(value):
                merged[key] = merged.get(key, 0) + value
            else:
                merged[key] = value

    last = usages[-1]
    if isinstance(last, dict) and "stop_reason" in last:
        merged["stop_reason"] = last["stop_reason"]
    return merged


def _compute_patch_robustness_metrics(per_instance_results: list[dict]) -> dict:
    """Compute run-level patch applicability metrics."""
    n_apply_ok = sum(1 for r in per_instance_results if r.get("patch_status") == "patched")
    n_apply_failed = sum(1 for r in per_instance_results if r.get("patch_status") == "apply_failed")
    denominator = max(1, n_apply_ok + n_apply_failed)
    return {
        "n_apply_ok": n_apply_ok,
        "n_apply_failed": n_apply_failed,
        "apply_success_rate": n_apply_ok / denominator,
    }


def _git_apply_check(repo_dir: str, patch_text: str) -> tuple[bool, str]:
    """Validate a patch against a checked-out repo context."""
    result = subprocess.run(
        ["git", "apply", "--check", "--verbose", "-"],
        cwd=repo_dir,
        input=patch_text,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True, ""
    details = "\n".join(
        part.strip()
        for part in (result.stderr or "", result.stdout or "")
        if part and part.strip()
    ).strip()
    return False, details


def _is_cannot_patch(patch_text: str | None, patch_tokens: dict | None) -> bool:
    if patch_text:
        return False
    tokens = patch_tokens or {}
    if bool(tokens.get("cannot_patch")):
        return True
    stop_reason = str(tokens.get("stop_reason", "")).lower()
    error_text = str(tokens.get("error", "")).lower()
    return "cannot_patch" in stop_reason or "cannot_patch" in error_text


def _build_apply_failure_correction_context(apply_stderr: str) -> str:
    return (
        "Your previous diff failed to apply with git apply --check.\n"
        f"Error:\n{apply_stderr}\n\n"
        "Common causes: wrong hunk context, wrong file path, or malformed unified diff.\n"
        "Regenerate a complete, valid unified diff."
    )


def _build_retrieval_retry_feedback(previous_files: list[str], failure_hint: str) -> str:
    file_lines = "\n".join(f"- {path}" for path in previous_files) if previous_files else "- (none)"
    return (
        "The previous retrieval context was insufficient to produce an applicable patch.\n"
        f"Tried files:\n{file_lines}\n\n"
        f"Failure hint:\n{failure_hint}\n\n"
        "Search for additional or alternative files needed to fix the issue."
    )


def _generate_patch_with_retries(
    *,
    issue_text: str,
    initial_retrieved_files: list[str],
    patch_generate_fn,
    apply_check_fn,
    retrieval_retry_fn,
    max_repair_retries: int = 2,
    max_retrieval_retries: int = 1,
) -> dict:
    """
    Generate patch with bounded apply-repair and retrieval-retry loops.

    patch_generate_fn signature:
      fn(retrieved_files=[...], correction_context=str|None) -> (patch_text|None, patch_tokens:dict)
    apply_check_fn signature:
      fn(patch_text:str) -> (ok:bool, stderr:str)
    retrieval_retry_fn signature:
      fn(previous_files=[...], failure_hint:str) -> (retrieved_files:[...], retrieval_tokens:dict)
    """
    retrieved_files = list(initial_retrieved_files)
    patch_tokens_history: list[dict] = []
    retrieval_retry_history: list[dict] = []
    repair_retries_used = 0
    retrieval_retries_used = 0
    apply_failures = 0

    final_patch_text = None
    final_status = "no_patch"
    failure_hint = ""

    while True:
        correction_context = None
        current_cannot_patch = False
        for repair_idx in range(max_repair_retries + 1):
            patch_text, patch_tokens = patch_generate_fn(
                retrieved_files=list(retrieved_files),
                correction_context=correction_context,
            )
            patch_tokens = patch_tokens or {}
            patch_tokens_history.append(patch_tokens)
            current_cannot_patch = _is_cannot_patch(patch_text, patch_tokens)

            if not patch_text:
                final_patch_text = None
                final_status = "no_patch"
                if current_cannot_patch:
                    failure_hint = "Patch agent returned CANNOT_PATCH."
                else:
                    failure_hint = "Patch agent did not return a valid diff."
                break

            apply_ok, apply_stderr = apply_check_fn(patch_text)
            if apply_ok:
                final_patch_text = patch_text
                final_status = "patched"
                failure_hint = ""
                break

            final_patch_text = patch_text
            final_status = "apply_failed"
            apply_failures += 1
            failure_hint = apply_stderr or "git apply --check failed."

            if repair_idx >= max_repair_retries:
                break

            repair_retries_used += 1
            correction_context = _build_apply_failure_correction_context(failure_hint)

        if final_status == "patched":
            break

        should_retry_retrieval = retrieval_retries_used < max_retrieval_retries and (
            current_cannot_patch or final_status == "apply_failed"
        )
        if not should_retry_retrieval:
            break

        retrieval_feedback = _build_retrieval_retry_feedback(retrieved_files, failure_hint)
        new_files, retry_tokens = retrieval_retry_fn(
            previous_files=list(retrieved_files),
            failure_hint=retrieval_feedback,
        )
        retrieved_files = list(new_files)
        retrieval_retries_used += 1
        retrieval_retry_history.append({
            "retrieved_files": list(retrieved_files),
            "retrieval_tokens": retry_tokens or {},
            "feedback": retrieval_feedback,
        })

    return {
        "patch_text": final_patch_text,
        "patch_status": final_status,
        "retrieved_files": list(retrieved_files),
        "patch_tokens_history": patch_tokens_history,
        "retrieval_retry_history": retrieval_retry_history,
        "repair_retries_used": repair_retries_used,
        "retrieval_retries_used": retrieval_retries_used,
        "apply_failures": apply_failures,
    }


def _extract_harness_results_from_payload(payload: dict, *, n_total: int) -> dict | None:
    """Parse SWE-bench report payloads across known schema variants."""
    if not isinstance(payload, dict):
        return None

    resolved_ids = payload.get("resolved_ids")
    if isinstance(resolved_ids, list):
        resolved_instances = sorted(str(i) for i in resolved_ids)
        n_resolved = len(resolved_instances)
        return {
            "n_resolved": n_resolved,
            "resolved_rate": round(n_resolved / n_total, 4) if n_total else 0.0,
            "resolved_instances": resolved_instances,
        }

    # Per-instance dict: {instance_id: {"resolved": bool, ...}, ...}
    resolved_instances = sorted(
        str(iid)
        for iid, result in payload.items()
        if isinstance(result, dict) and bool(result.get("resolved"))
    )
    per_instance_like = bool(payload) and all(isinstance(v, dict) for v in payload.values())
    if resolved_instances or per_instance_like:
        n_resolved = len(resolved_instances)
        return {
            "n_resolved": n_resolved,
            "resolved_rate": round(n_resolved / n_total, 4) if n_total else 0.0,
            "resolved_instances": resolved_instances,
        }

    if "resolved_instances" in payload and _tokenish_number(payload.get("resolved_instances")):
        n_resolved = int(payload.get("resolved_instances", 0))
        return {
            "n_resolved": n_resolved,
            "resolved_rate": round(n_resolved / n_total, 4) if n_total else 0.0,
            "resolved_instances": [],
        }
    return None


def _discover_harness_report_path(
    *,
    harness_run_id: str,
    retrieval_method: str,
    harness_report_dir: Path,
) -> Path | None:
    """Find the SWE-bench aggregate report across known output locations."""
    candidates = [
        harness_report_dir / f"{harness_run_id}.json",
        Path.cwd() / f"graphmanager-{retrieval_method}.{harness_run_id}.json",
    ]
    candidates.extend(sorted(harness_report_dir.glob(f"*.{harness_run_id}.json")))
    candidates.extend(sorted(Path.cwd().glob(f"*.{harness_run_id}.json")))

    seen = set()
    for candidate in candidates:
        normalized = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return candidate
    return None


def _extract_harness_results_from_instance_reports(*, harness_run_id: str, n_total: int) -> dict | None:
    """Fallback parser when only per-instance report.json files are available."""
    run_dir = Path("logs") / "run_evaluation" / harness_run_id
    if not run_dir.exists():
        return None

    resolved_instances = set()
    for report_path in run_dir.glob("*/*/report.json"):
        try:
            payload = json.loads(report_path.read_text())
        except Exception:
            continue
        for iid, result in payload.items():
            if isinstance(result, dict) and bool(result.get("resolved")):
                resolved_instances.add(str(iid))

    if not resolved_instances and not list(run_dir.glob("*/*/report.json")):
        return None

    resolved = sorted(resolved_instances)
    n_resolved = len(resolved)
    return {
        "n_resolved": n_resolved,
        "resolved_rate": round(n_resolved / n_total, 4) if n_total else 0.0,
        "resolved_instances": resolved,
        "report_path": str(run_dir),
    }


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
    patch_max_output_tokens = int(manifest.get("patch_max_output_tokens", 4096))
    patch_max_file_chars = int(manifest.get("patch_max_file_chars", 8000))
    patch_apply_repair_retries = min(2, max(0, int(manifest.get("patch_apply_repair_retries", 2))))
    patch_retrieval_retry_max = min(1, max(0, int(manifest.get("patch_retrieval_retry_max", 1))))
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
    api_timeout_s = int(manifest.get("api_timeout_s", 120))
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
    print(f"Manager max turns: {manager_max_turns}")
    print(f"Patch max output tokens: {patch_max_output_tokens}")
    print(f"Patch max file chars: {patch_max_file_chars}")
    print(f"API timeout (s): {api_timeout_s}")
    print(f"Results dir: {results_path}")

    from google import genai
    from google.genai import types as genai_types
    from src.evaluation import (
        clone_repo,
        load_issues,
        prepare_issue_text,
        validate_commit_context,
    )
    from src.graph_builder import GraphBuilder, GraphIndex
    from src.patch_agent import PatchAgent
    from src.rag_baseline import RAGIndex

    httpx_client = httpx.Client(timeout=api_timeout_s)
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(httpx_client=httpx_client),
    )

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

        patch_agent = PatchAgent(
            repo_dir,
            client,
            model=patch_model,
            max_file_chars=patch_max_file_chars,
            max_output_tokens=patch_max_output_tokens,
        )
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
            retrieval_token_steps = [retrieval_tokens]

            # --- Patch generation ---
            t1 = time.time()
            flow_result = None
            if dry_run:
                patch_text = None
                patch_tokens = {"total_tokens": 0, "stop_reason": "dry_run"}
                status = "no_patch"
            elif retrieval_error is not None:
                patch_text = None
                patch_tokens = {
                    "prompt_tokens": 0,
                    "candidate_tokens": 0,
                    "total_tokens": 0,
                    "tool_calls": 0,
                    "stop_reason": "skipped_due_to_retrieval_error",
                }
                status = "no_patch"
            else:
                issue_text = prepare_issue_text(issue.get("problem_statement", ""))

                def patch_generate_fn(*, retrieved_files: list[str], correction_context: str | None):
                    return _run_with_rate_limit_backoff(
                        lambda: patch_agent.generate_patch(
                            issue_text,
                            retrieved_files,
                            max_turns=patch_max_turns,
                            correction_context=correction_context,
                        ),
                        label=f"patch[{iid}]",
                        max_retries=rate_limit_max_retries,
                        initial_delay_s=rate_limit_initial_delay_s,
                        backoff_multiplier=rate_limit_backoff_multiplier,
                        max_delay_s=rate_limit_max_delay_s,
                        jitter_s=rate_limit_jitter_s,
                    )

                def apply_check_fn(patch_candidate: str):
                    return _git_apply_check(repo_dir, patch_candidate)

                def retrieval_retry_fn(*, previous_files: list[str], failure_hint: str):
                    return _run_with_rate_limit_backoff(
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
                            retry_feedback=failure_hint,
                        ),
                        label=f"retrieval_retry[{iid}]",
                        max_retries=rate_limit_max_retries,
                        initial_delay_s=rate_limit_initial_delay_s,
                        backoff_multiplier=rate_limit_backoff_multiplier,
                        max_delay_s=rate_limit_max_delay_s,
                        jitter_s=rate_limit_jitter_s,
                    )

                try:
                    flow_result = _generate_patch_with_retries(
                        issue_text=issue_text,
                        initial_retrieved_files=retrieved_files,
                        patch_generate_fn=patch_generate_fn,
                        apply_check_fn=apply_check_fn,
                        retrieval_retry_fn=retrieval_retry_fn,
                        max_repair_retries=patch_apply_repair_retries,
                        max_retrieval_retries=patch_retrieval_retry_max,
                    )
                    patch_text = flow_result["patch_text"]
                    patch_tokens = _merge_token_usages(flow_result["patch_tokens_history"])
                    patch_tokens["attempts"] = len(flow_result["patch_tokens_history"])
                    patch_tokens["repair_retries_used"] = flow_result["repair_retries_used"]
                    patch_tokens["apply_failures"] = flow_result["apply_failures"]
                    status = flow_result["patch_status"]
                    retrieved_files = flow_result["retrieved_files"]

                    for retry_event in flow_result["retrieval_retry_history"]:
                        retrieval_token_steps.append(retry_event.get("retrieval_tokens", {}))
                    if len(retrieval_token_steps) > 1:
                        retrieval_tokens = _merge_token_usages(retrieval_token_steps)
                    retrieval_tokens["retrieval_retries_used"] = flow_result["retrieval_retries_used"]
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
                    status = "no_patch"
                    print(f"    Patch generation failed after retries: {type(exc).__name__}")
            patch_time = time.time() - t1

            print(f"    Patch status: {status}")

            if per_instance_cooldown_s > 0 and not dry_run:
                time.sleep(per_instance_cooldown_s)

            # Save patch to disk
            if patch_text and status in {"patched", "apply_failed"}:
                patch_file = patches_path / f"{iid}.patch"
                patch_file.write_text(patch_text)
            else:
                patch_file = None

            # Build SWE-bench prediction entry
            swebench_predictions[iid] = {
                "instance_id": iid,
                "model_name_or_path": f"graphmanager-{retrieval_method}",
                "model_patch": patch_text if status == "patched" else "",
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
                "repair_retries_used": int((flow_result or {}).get("repair_retries_used", 0)),
                "retrieval_retries_used": int((flow_result or {}).get("retrieval_retries_used", 0)),
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

    robustness = _compute_patch_robustness_metrics(per_instance_results)
    n_patched = robustness["n_apply_ok"]
    n_total = len(per_instance_results)
    total_tokens = sum(r["total_tokens"] for r in per_instance_results)

    summary = {
        "run_id": run_id,
        "manifest": manifest_path,
        "dataset_name": dataset_name,
        "retrieval_method": retrieval_method,
        "n_instances": n_total,
        "n_patched": n_patched,
        "n_apply_ok": robustness["n_apply_ok"],
        "n_apply_failed": robustness["n_apply_failed"],
        "apply_success_rate": robustness["apply_success_rate"],
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
                harness_report_dir = results_path / "harness_reports"
                harness_report_dir.mkdir(exist_ok=True)

                eval_report_path = swebench_eval(
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
                    report_dir=str(harness_report_dir),
                )

                # Parse results
                report_path = None
                if eval_report_path is not None:
                    candidate = Path(str(eval_report_path))
                    if candidate.exists():
                        report_path = candidate
                if report_path is None:
                    report_path = _discover_harness_report_path(
                        harness_run_id=harness_run_id,
                        retrieval_method=retrieval_method,
                        harness_report_dir=harness_report_dir,
                    )

                if report_path and report_path.exists():
                    payload = json.loads(report_path.read_text())
                    parsed = _extract_harness_results_from_payload(payload, n_total=n_total)
                    if parsed:
                        parsed["report_path"] = str(report_path)
                        summary["harness_results"] = parsed

                if summary.get("harness_results") is None:
                    fallback = _extract_harness_results_from_instance_reports(
                        harness_run_id=harness_run_id,
                        n_total=n_total,
                    )
                    if fallback:
                        summary["harness_results"] = fallback

                if summary.get("harness_results"):
                    hr = summary["harness_results"]
                    print(f"  Resolved: {hr['n_resolved']}/{n_total} ({hr['resolved_rate']:.1%})")
                else:
                    expected = harness_report_dir / f"{harness_run_id}.json"
                    print(f"  WARNING: harness report not found at expected location {expected}")
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

    try:
        httpx_client.close()
    except Exception:
        pass

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
