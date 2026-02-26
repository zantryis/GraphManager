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
    retrieval_method: gm_progressive   # gm_deterministic | rag_progressive | raw_rag_function | raw_rag_fixed | bm25 | oracle | none | agentic_cold_start | repomap_like | agentless_like_localization
    manager_max_turns: 4
    retrieval_max_files_for_patch: 6  # post-retrieval cap before patching (set null to disable)
    patch_max_turns: 3
    patch_max_output_tokens: 4096
    patch_max_file_chars: 8000
"""

import argparse
import concurrent.futures
import hashlib
import httpx
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_MANAGER_MODEL = "gemini-3-flash-preview"
DEFAULT_PATCH_MODEL = "gemini-3-flash-preview"


def _capture_provenance(manifest_path: str) -> dict:
    """Capture reproducibility metadata: git SHA, manifest hash, python/dep versions."""
    provenance: dict = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Git SHA of the repo running the pipeline (NOT the target repo)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).parent),
        )
        provenance["pipeline_git_sha"] = result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        provenance["pipeline_git_sha"] = "unknown"
    # Check for uncommitted changes
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).parent),
        )
        provenance["pipeline_dirty"] = bool(result.stdout.strip()) if result.returncode == 0 else None
    except Exception:
        provenance["pipeline_dirty"] = None
    # Manifest content hash
    try:
        manifest_bytes = Path(manifest_path).read_bytes()
        provenance["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    except Exception:
        provenance["manifest_sha256"] = "unknown"
    # Key dependency versions
    dep_versions = {}
    for pkg in ("swebench", "google-genai", "rank_bm25", "tree_sitter", "networkx", "faiss"):
        try:
            import importlib.metadata
            dep_versions[pkg] = importlib.metadata.version(pkg.replace("_", "-").replace("_", "-"))
        except Exception:
            dep_versions[pkg] = "unknown"
    provenance["dependency_versions"] = dep_versions
    return provenance


def _checkout_issue_commit(
    *,
    repo_git,
    snapshot_commit: str | None,
    issue: dict,
    current_commit: str | None,
    issue_id: str | None = None,
) -> str | None:
    """Checkout the commit for this issue when needed and return current commit."""
    target_commit = snapshot_commit or issue.get("base_commit")
    if target_commit and target_commit != current_commit:
        if issue_id:
            print(f"    Checking out {target_commit[:12]} for {issue_id}...")
        else:
            print(f"    Checking out {target_commit[:12]}...")
        try:
            repo_git.git.checkout(target_commit, force=True)
        except Exception as exc:
            # Some local SWE-bench repo clones do not yet contain the issue's base commit.
            # Attempt a targeted fetch, then retry checkout once.
            if "reference is not a tree" not in str(exc).lower():
                raise
            print(f"    Missing commit locally; fetching {target_commit[:12]}...")
            fetch_error = None
            for fetch_args in (("origin", target_commit), ("--all", "--tags", "--prune")):
                try:
                    repo_git.git.fetch(*fetch_args)
                    fetch_error = None
                    break
                except Exception as fetch_exc:
                    fetch_error = fetch_exc
            if fetch_error is not None:
                raise fetch_error from exc
            repo_git.git.checkout(target_commit, force=True)
        return target_commit
    return current_commit


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


def _slugify_identifier(value: str) -> str:
    """Return a filesystem-safe lowercase identifier fragment."""
    lowered = (value or "").strip().lower()
    chars = [ch if ch.isalnum() else "-" for ch in lowered]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "unknown"


def _build_harness_run_id(
    *,
    run_id: str,
    retrieval_method: str,
    results_path: Path,
    existing_harness_run_id: str | None = None,
) -> str:
    """Build a collision-resistant harness run ID for concurrent runs."""
    if existing_harness_run_id:
        return str(existing_harness_run_id)

    method_slug = _slugify_identifier(retrieval_method)
    path_hash = hashlib.sha1(str(results_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"graphmanager_{run_id}_{method_slug}_{path_hash}"


def _allocate_run_output_dir(results_dir: str) -> tuple[str, Path]:
    """Allocate a unique run directory under <results_dir>/patch_runs."""
    patch_runs_root = Path(results_dir) / "patch_runs"
    patch_runs_root.mkdir(parents=True, exist_ok=True)

    base_run_id = time.strftime("%Y%m%d_%H%M%S")
    suffix = 0
    while True:
        run_id = base_run_id if suffix == 0 else f"{base_run_id}_{suffix:02d}"
        candidate = patch_runs_root / run_id
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return run_id, candidate
        except FileExistsError:
            # Handle concurrent allocators racing on the same timestamp/suffix.
            suffix += 1
        suffix += 1


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
    deadline_monotonic: float | None = None,
):
    """
    Run callable with retries on transient API limits/failures.

    max_retries counts retry attempts after the initial call.
    """
    delay_s = max(initial_delay_s, 0.0)
    for attempt in range(max_retries + 1):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise TimeoutError(f"{label} timed out due to instance wall-clock budget")
        try:
            if deadline_monotonic is None:
                return callable_fn()

            remaining_s = deadline_monotonic - time.monotonic()
            if remaining_s <= 0:
                raise TimeoutError(f"{label} timed out due to instance wall-clock budget")

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(callable_fn)
            try:
                return future.result(timeout=remaining_s)
            except concurrent.futures.TimeoutError as timeout_exc:
                future.cancel()
                raise TimeoutError(f"{label} timed out due to instance wall-clock budget") from timeout_exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            should_retry = _is_transient_api_error(exc) and attempt < max_retries
            if not should_retry:
                raise
            sleep_s = min(delay_s, max_delay_s) + max(0.0, random.uniform(0.0, max(0.0, jitter_s)))
            if deadline_monotonic is not None and (time.monotonic() + sleep_s) >= deadline_monotonic:
                raise TimeoutError(f"{label} timed out due to instance wall-clock budget") from exc
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
    bm25_index=None,
    rag_metadata_index=None,
    client,
    method: str,
    manager_model: str,
    manager_max_turns: int,
    deterministic_config: dict,
    redact_paths: bool = True,
    retry_feedback: str | None = None,
    rag_symmetric_tools: bool = False,
    repo_dir: str | None = None,
    include_prefixes: tuple[str, ...] | None = None,
    valid_file_paths: set[str] | None = None,
    patch_max_file_chars: int = 200_000,
    repomap_config: dict | None = None,
    agentless_like_config: dict | None = None,
) -> tuple[list[str], dict]:
    """Run one retrieval method for one issue."""
    from src.evaluation import normalize_file_paths, prepare_issue_text
    from src.path_resolution import canonicalize_file_paths

    if method == "none":
        return [], {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "tool_calls": 0,
            "stop_reason": "no_retrieval",
        }

    files: list[str]
    tokens: dict

    if method == "oracle":
        from src.datasets.adapters import extract_gold_files_from_patch

        oracle_files = extract_gold_files_from_patch(issue.get("patch", ""))
        if not oracle_files:
            oracle_files = issue.get("gold_files", [])
        files = normalize_file_paths(oracle_files)
        tokens = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "tool_calls": 0,
            "stop_reason": "oracle",
        }
    else:
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
                repo_dir=repo_dir,
                symmetric_tools=rag_symmetric_tools,
                max_file_chars=patch_max_file_chars,
            )
            files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)

        elif method in {"rag_baseline", "raw_rag_function", "raw_rag_fixed"}:
            if rag_index is None:
                raise ValueError(f"rag_index must be provided when method='{method}'")
            if method == "rag_baseline":
                from src.rag_baseline import RAGAgent
                agent = RAGAgent(
                    rag_index,
                    client,
                    model=manager_model,
                    retrieval_mode="baseline",
                    repo_dir=repo_dir,
                    symmetric_tools=False,
                    max_file_chars=patch_max_file_chars,
                )
                files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)
            else:
                from src.rag_baseline import RawRAG
                agent = RawRAG(rag_index)
                files, tokens = agent.find_relevant_files(query, top_k=20)

        elif method == "agentic_cold_start":
            from src.agentic_cold_start import AgenticColdStartAgent
            if not repo_dir:
                raise ValueError("repo_dir must be provided when method='agentic_cold_start'")
            agent = AgenticColdStartAgent(
                repo_dir=repo_dir,
                client=client,
                model=manager_model,
                include_prefixes=include_prefixes,
                max_file_chars=patch_max_file_chars,
            )
            files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)

        elif method == "bm25":
            if bm25_index is None:
                raise ValueError("bm25_index must be provided when method='bm25'")
            files, tokens = bm25_index.find_relevant_files(query)

        elif method == "rag_metadata":
            if rag_metadata_index is None:
                raise ValueError("rag_metadata_index must be provided when method='rag_metadata'")
            from src.rag_baseline import RawRAG
            agent = RawRAG(rag_metadata_index)
            files, tokens = agent.find_relevant_files(query)

        elif method == "repomap_like":
            if graph is None:
                raise ValueError("graph must be provided when method='repomap_like'")
            from src.repomap_like import RepoMapLikeRetriever

            cfg = dict(repomap_config or {})
            agent = RepoMapLikeRetriever(
                graph=graph,
                client=client if bool(cfg.get("use_llm_selector", False)) else None,
                model=manager_model,
                top_k_files=int(cfg.get("top_k_files", 10) or 10),
                map_tokens=int(cfg.get("map_tokens", 1000) or 1000),
                use_llm_selector=bool(cfg.get("use_llm_selector", False)),
                refresh_mode=str(cfg.get("refresh_mode", "static_per_issue") or "static_per_issue"),
                edge_weights=dict(cfg.get("edge_weights", {}) or {}),
                enable_same_module_edge=bool(cfg.get("enable_same_module_edge", False)),
                personalization_enabled=bool(cfg.get("personalization_enabled", True)),
            )
            files, tokens = agent.find_relevant_files(query)

        elif method == "agentless_like_localization":
            if rag_index is None:
                raise ValueError("rag_index must be provided when method='agentless_like_localization'")
            if graph is None:
                raise ValueError("graph must be provided when method='agentless_like_localization'")
            from src.agentless_like_localization import AgentlessLikeLocalizer

            cfg = dict(agentless_like_config or {})
            agent = AgentlessLikeLocalizer(
                rag_index=rag_index,
                graph=graph,
                client=client,
                model=manager_model,
                stage2_enabled=bool(cfg.get("stage2_enabled", True)),
                stage3_enabled=bool(cfg.get("stage3_enabled", True)),
                edit_location_samples=int(cfg.get("edit_location_samples", 4) or 4),
                file_branch_top_n=int(cfg.get("file_branch_top_n", 3) or 3),
                embed_branch_top_k=int(cfg.get("embed_branch_top_k", 20) or 20),
                merge_top_k=int(cfg.get("merge_top_k", 12) or 12),
                stage3_context_window_lines=int(cfg.get("stage3_context_window_lines", 10) or 10),
                stage3_max_tokens_per_file=int(cfg.get("stage3_max_tokens_per_file", 1200) or 1200),
                constrained_candidates_max=int(cfg.get("constrained_candidates_max", 200) or 200),
                reject_out_of_candidate_paths=bool(cfg.get("reject_out_of_candidate_paths", True)),
            )
            files, tokens = agent.find_relevant_files(query, max_turns=manager_max_turns)

        else:
            raise ValueError(f"Unsupported retrieval method: {method}")

    resolved_valid_paths: set[str] = set(valid_file_paths or set())
    if not resolved_valid_paths:
        if graph is not None:
            resolved_valid_paths = {
                str(node_id)
                for node_id, node_data in graph.nodes(data=True)
                if node_data.get("type") == "file" and str(node_id).endswith(".py")
            }
        elif rag_index is not None:
            resolved_valid_paths = {
                str(chunk.get("file", ""))
                for chunk in getattr(rag_index, "chunks", [])
                if str(chunk.get("file", "")).endswith(".py")
            }
        elif bm25_index is not None:
            resolved_valid_paths = {
                str(path)
                for path in getattr(bm25_index, "_file_paths", [])
                if str(path).endswith(".py")
            }

    normalized = normalize_file_paths(files)
    canonical = canonicalize_file_paths(normalized, resolved_valid_paths) if resolved_valid_paths else normalized
    return canonical, tokens


def _cap_retrieved_files(
    files: list[str],
    *,
    max_files: int | None,
) -> tuple[list[str], int, int]:
    """Apply a global post-retrieval file cap for patch-context fairness."""
    normalized = list(files or [])
    pre_count = len(normalized)
    if max_files is None:
        return normalized, pre_count, pre_count
    capped = normalized[: max(max_files, 1)]
    return capped, pre_count, len(capped)


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


def _build_method_scoped_commit_context(
    *,
    retrieval_method: str,
    repo_dir: str,
    prefixes: tuple[str, ...] | None,
    client,
    graph_builder_cls,
    graph_index_cls,
    rag_index_cls,
    validate_commit_context_fn,
) -> dict:
    """Build only the index family needed by the retrieval method."""
    context = {
        "graph": None,
        "graph_index": None,
        "rag_index": None,
        "bm25_index": None,
        "graph_file_paths": set(),
        "retrieval_setup_tokens": 0,
        "setup_tokens_graph_built": 0,
        "setup_tokens_rag_built": 0,
        "setup_tokens_method_accounted": 0,
    }

    gm_family = {"gm_progressive", "gm_deterministic", "gm_baseline"}
    rag_family = {"rag_progressive", "rag_baseline", "raw_rag_function", "raw_rag_fixed"}
    repomap_family = {"repomap_like"}
    agentless_family = {"agentless_like_localization"}
    rag_metadata_family = {"rag_metadata"}

    if retrieval_method in gm_family:
        print("    Building graph index...")
        builder = graph_builder_cls(repo_dir, include_prefixes=prefixes)
        graph = builder.build()
        print(
            f"      Graph: {graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges"
        )
        graph_index = graph_index_cls(graph, client)
        graph_index.build()
        graph_tokens = int(getattr(graph_index, "embedding_tokens_estimate", 0) or 0)

        setup_costs = {
            "gm_progressive": {"embedding_tokens": graph_tokens},
            "gm_deterministic": {"embedding_tokens": graph_tokens},
            "gm_baseline": {"embedding_tokens": graph_tokens},
        }
        validate_commit_context_fn(
            {"graph_file_paths": set(), "setup_costs": setup_costs},
            required_methods=(retrieval_method,),
        )
        context.update(
            {
                "graph": graph,
                "graph_index": graph_index,
                "graph_file_paths": {
                    str(node_id)
                    for node_id, node_data in graph.nodes(data=True)
                    if node_data.get("type") == "file"
                },
                "retrieval_setup_tokens": graph_tokens,
                "setup_tokens_graph_built": graph_tokens,
                "setup_tokens_method_accounted": graph_tokens,
            }
        )
        return context

    if retrieval_method in repomap_family:
        print("    Building graph (repomap_like)...")
        builder = graph_builder_cls(repo_dir, include_prefixes=prefixes)
        graph = builder.build()
        file_paths = {
            str(node_id)
            for node_id, node_data in graph.nodes(data=True)
            if node_data.get("type") == "file"
        }
        if not file_paths:
            raise ValueError(
                "repomap_like graph is empty (no Python files in scope). "
                "Check source_prefixes against repository layout."
            )
        context.update(
            {
                "graph": graph,
                "graph_file_paths": file_paths,
                "retrieval_setup_tokens": 0,
                "setup_tokens_graph_built": 0,
                "setup_tokens_method_accounted": 0,
            }
        )
        return context

    if retrieval_method in rag_family:
        print("    Building RAG index...")
        rag_chunk_strategy = "fixed" if retrieval_method == "raw_rag_fixed" else "function"
        rag_index = rag_index_cls(
            repo_dir,
            client,
            chunk_strategy=rag_chunk_strategy,
            include_prefixes=prefixes,
        )
        rag_index.build()
        rag_tokens = int(getattr(rag_index, "embedding_tokens_estimate", 0) or 0)

        setup_costs = {
            "rag_progressive": {"embedding_tokens": rag_tokens},
            "rag_baseline": {"embedding_tokens": rag_tokens},
            "raw_rag_function": {"embedding_tokens": rag_tokens},
            "raw_rag_fixed": {"embedding_tokens": rag_tokens},
        }
        validate_commit_context_fn(
            {"graph_file_paths": set(), "setup_costs": setup_costs},
            required_methods=(retrieval_method,),
        )
        context.update(
            {
                "rag_index": rag_index,
                "graph_file_paths": {
                    str(chunk.get("file", ""))
                    for chunk in getattr(rag_index, "chunks", [])
                    if str(chunk.get("file", ""))
                },
                "retrieval_setup_tokens": rag_tokens,
                "setup_tokens_rag_built": rag_tokens,
                "setup_tokens_method_accounted": rag_tokens,
            }
        )
        return context

    if retrieval_method in agentless_family:
        print("    Building graph (agentless_like_localization)...")
        builder = graph_builder_cls(repo_dir, include_prefixes=prefixes)
        graph = builder.build()
        graph_file_paths = {
            str(node_id)
            for node_id, node_data in graph.nodes(data=True)
            if node_data.get("type") == "file"
        }
        if not graph_file_paths:
            raise ValueError(
                "agentless_like_localization graph is empty (no Python files in scope). "
                "Check source_prefixes against repository layout."
            )

        print("    Building RAG index (agentless_like_localization)...")
        rag_index = rag_index_cls(
            repo_dir,
            client,
            chunk_strategy="function",
            include_prefixes=prefixes,
        )
        rag_index.build()
        rag_tokens = int(getattr(rag_index, "embedding_tokens_estimate", 0) or 0)
        validate_commit_context_fn(
            {"graph_file_paths": set(), "setup_costs": {"rag_progressive": {"embedding_tokens": rag_tokens}}},
            required_methods=("rag_progressive",),
        )
        context.update(
            {
                "graph": graph,
                "rag_index": rag_index,
                "graph_file_paths": {
                    str(chunk.get("file", ""))
                    for chunk in getattr(rag_index, "chunks", [])
                    if str(chunk.get("file", ""))
                } | graph_file_paths,
                "retrieval_setup_tokens": rag_tokens,
                "setup_tokens_graph_built": 0,
                "setup_tokens_rag_built": rag_tokens,
                "setup_tokens_method_accounted": rag_tokens,
            }
        )
        return context

    if retrieval_method in rag_metadata_family:
        print("    Building graph (rag_metadata)...")
        builder = graph_builder_cls(repo_dir, include_prefixes=prefixes)
        graph = builder.build()
        graph_file_paths = {
            str(node_id)
            for node_id, node_data in graph.nodes(data=True)
            if node_data.get("type") == "file"
        }
        if not graph_file_paths:
            raise ValueError(
                "rag_metadata graph is empty (no Python files in scope). "
                "Check source_prefixes against repository layout."
            )

        print("    Building RAGMetadataIndex (rag_metadata)...")
        from src.rag_baseline import RAGMetadataIndex
        rag_metadata_idx = RAGMetadataIndex(graph, client)
        rag_metadata_idx.build()
        meta_tokens = int(getattr(rag_metadata_idx, "embedding_tokens_estimate", 0) or 0)

        setup_costs = {"rag_metadata": {"embedding_tokens": meta_tokens}}
        validate_commit_context_fn(
            {"graph_file_paths": graph_file_paths, "setup_costs": setup_costs},
            required_methods=(retrieval_method,),
        )
        context.update(
            {
                "graph": graph,
                "rag_metadata_index": rag_metadata_idx,
                "graph_file_paths": graph_file_paths,
                "retrieval_setup_tokens": meta_tokens,
                "setup_tokens_graph_built": meta_tokens,
                "setup_tokens_method_accounted": meta_tokens,
            }
        )
        return context

    if retrieval_method == "bm25":
        print("    Building BM25 index...")
        from src.bm25_baseline import BM25Index
        bm25_index = BM25Index(repo_dir, include_prefixes=prefixes)
        bm25_index.build()
        bm25_file_paths = set(bm25_index._file_paths)
        print(f"      BM25: {len(bm25_file_paths)} files indexed")

        context.update(
            {
                "bm25_index": bm25_index,
                "graph_file_paths": bm25_file_paths,  # used for patch context file set
                "retrieval_setup_tokens": 0,          # BM25 has no embedding cost
                "setup_tokens_method_accounted": 0,
            }
        )
        return context

    # none/oracle/agentic_cold_start do not build retrieval indices, but still
    # expose valid repo file paths for canonicalization and path safety.
    repo_paths = set()
    for py_file in sorted(Path(repo_dir).rglob("*.py")):
        rel = py_file.relative_to(repo_dir).as_posix()
        if any(part.startswith(".") for part in py_file.parts):
            continue
        if prefixes:
            if not any(rel == prefix or rel.startswith(prefix + "/") for prefix in prefixes):
                continue
        repo_paths.add(rel)
    context["graph_file_paths"] = repo_paths
    return context


def _compute_cost_summary_fields(
    *,
    per_instance_results: list[dict],
    retrieval_setup_tokens: int,
    harness_results: dict | None,
    setup_tokens_graph_built: int = 0,
    setup_tokens_rag_built: int = 0,
    setup_tokens_method_accounted: int | None = None,
) -> dict:
    retrieval_runtime_tokens = sum(
        int((result.get("retrieval_tokens") or {}).get("total_tokens", 0) or 0)
        for result in per_instance_results
    )
    patch_runtime_tokens = sum(
        int((result.get("patch_tokens") or {}).get("total_tokens", 0) or 0)
        for result in per_instance_results
    )
    total_cost_tokens = int(retrieval_setup_tokens or 0) + retrieval_runtime_tokens + patch_runtime_tokens

    resolved_instances = []
    n_resolved = None
    if isinstance(harness_results, dict):
        raw_instances = harness_results.get("resolved_instances", [])
        if isinstance(raw_instances, list):
            resolved_instances = sorted(str(i) for i in raw_instances)
        if _tokenish_number(harness_results.get("n_resolved")):
            n_resolved = int(harness_results.get("n_resolved", 0))
        elif resolved_instances:
            n_resolved = len(resolved_instances)

    cost_per_resolved_issue = None
    if isinstance(n_resolved, int) and n_resolved > 0:
        cost_per_resolved_issue = total_cost_tokens / n_resolved

    if setup_tokens_method_accounted is None:
        setup_tokens_method_accounted = int(retrieval_setup_tokens or 0)

    return {
        "retrieval_setup_tokens": int(retrieval_setup_tokens or 0),
        "setup_tokens_graph_built": int(setup_tokens_graph_built or 0),
        "setup_tokens_rag_built": int(setup_tokens_rag_built or 0),
        "setup_tokens_method_accounted": int(setup_tokens_method_accounted or 0),
        "retrieval_runtime_tokens": retrieval_runtime_tokens,
        "patch_runtime_tokens": patch_runtime_tokens,
        "total_cost_tokens": total_cost_tokens,
        "n_resolved": n_resolved,
        "resolved_instances": resolved_instances,
        "cost_per_resolved_issue": cost_per_resolved_issue,
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


def _make_swebench_prediction(
    *,
    instance_id: str,
    retrieval_method: str,
    patch_text: str | None,
    patch_status: str,
) -> dict:
    """Build a single SWE-bench prediction entry.

    The harness is the ground truth evaluator.  Submit the generated patch
    regardless of whether our local git-apply check passed (B7 fix).  Our local
    check is only a diagnostic used in the repair-retry loop; submitting an
    empty string for apply_failed patches silently zeros out resolved_rate.
    """
    return {
        "instance_id": instance_id,
        "model_name_or_path": f"graphmanager-{retrieval_method}",
        "model_patch": patch_text or "",
    }


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


def _worker_checkpoint_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    suffix = stem.removeprefix("predictions_worker_")
    try:
        return int(suffix), path.name
    except ValueError:
        return 10**9, path.name


def _checkpoint_files(run_dir: Path) -> list[Path]:
    worker_files = list(
        sorted(
            run_dir.glob("predictions_worker_*.jsonl"),
            key=_worker_checkpoint_sort_key,
        )
    )
    partial_path = run_dir / "predictions_partial.jsonl"
    # Prefer worker snapshots first, then canonical partial file last so
    # sequential/resume updates override older worker entries for same IID.
    if partial_path.exists():
        worker_files.append(partial_path)
    return worker_files


def _load_partial_checkpoint(run_dir: Path) -> dict:
    """Load completed instances from predictions_partial.jsonl.

    Returns a dict mapping instance_id → {"prediction": {...}, "per_instance": {...}}.
    Returns empty dict if no checkpoint file exists or all lines are malformed.
    """
    checkpoint_files = _checkpoint_files(run_dir)
    if not checkpoint_files:
        return {}
    completed = {}
    for checkpoint_file in checkpoint_files:
        for line in checkpoint_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                iid = entry["instance_id"]
                completed[iid] = entry
            except (json.JSONDecodeError, KeyError):
                continue
    return completed


def _flush_instance_to_checkpoint(
    run_dir: Path,
    instance_id: str,
    prediction: dict,
    per_instance: dict,
    checkpoint_filename: str = "predictions_partial.jsonl",
) -> None:
    """Append one completed instance to a checkpoint JSONL (atomic line append)."""
    partial_path = run_dir / checkpoint_filename
    entry = {"instance_id": instance_id, "prediction": prediction, "per_instance": per_instance}
    with partial_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _merge_worker_predictions(run_dir: Path, n_workers: int) -> tuple[dict, list]:
    """Merge per-worker partial JSONL files into a single predictions dict and per_instance list.

    Each worker writes to predictions_worker_N.jsonl. This function reads all worker files
    (in worker order, instances within each file in order) and returns:
      - predictions: dict mapping instance_id → prediction dict (for SWE-bench harness)
      - per_instance_list: ordered list of per-instance result dicts

    Missing or empty worker files are silently skipped (worker may have crashed before writing).
    Malformed lines are skipped.
    """
    predictions: dict = {}
    per_instance_list: list = []
    for worker_id in range(n_workers):
        worker_file = run_dir / f"predictions_worker_{worker_id}.jsonl"
        if not worker_file.exists():
            continue
        for line in worker_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                iid = entry["instance_id"]
                predictions[iid] = entry["prediction"]
                per_instance_list.append(entry["per_instance"])
            except (json.JSONDecodeError, KeyError):
                continue
    return predictions, per_instance_list


def _distribute_instances(instances: list, n_workers: int) -> list[list]:
    """Split *instances* into *n_workers* contiguous chunks.

    Remainder items go to earlier workers (chunk 0 gets the extras).
    Always returns exactly *n_workers* lists, some of which may be empty
    if n_workers > len(instances).

    Example:
        _distribute_instances(range(10), 3) → [[0,1,2,3], [4,5,6], [7,8,9]]
    """
    n = len(instances)
    if n_workers <= 0:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")
    base, extra = divmod(n, n_workers)
    chunks: list[list] = []
    start = 0
    for i in range(n_workers):
        size = base + (1 if i < extra else 0)
        chunks.append(list(instances[start: start + size]))
        start += size
    return chunks


def _run_evaluate_only(run_dir: str, modal: bool = False) -> dict:
    """
    Stage 2 (evaluate-only): run SWE-bench harness on an existing predictions.json.

    Loads patch_summary.json from *run_dir*, runs the harness, updates cost fields,
    overwrites patch_summary.json, and returns the updated summary dict.
    """
    load_dotenv()
    results_path = Path(run_dir)
    summary_path = results_path / "patch_summary.json"
    if not summary_path.exists():
        print(f"ERROR: No patch_summary.json found in {run_dir}")
        sys.exit(1)

    summary = json.loads(summary_path.read_text())
    run_id = summary["run_id"]
    dataset_name = summary["dataset_name"]
    retrieval_method = summary.get("retrieval_method", "unknown")
    existing_harness_run_id = summary.get("harness_run_id")
    predictions_path = Path(summary["predictions_path"])
    per_instance = summary.get("per_instance", [])
    instance_ids = [r["instance_id"] for r in per_instance]
    n_total = summary.get("n_instances", len(instance_ids))

    # Recover split from the manifest if it still exists, otherwise default to "test"
    split = "test"
    manifest_path = summary.get("manifest", "")
    if manifest_path and Path(manifest_path).exists():
        try:
            manifest = yaml.safe_load(Path(manifest_path).read_text())
            split = manifest.get("split", "test")
        except Exception:
            pass

    if not predictions_path.exists():
        print(f"ERROR: predictions.json not found at {predictions_path}")
        sys.exit(1)
    if not instance_ids:
        print("ERROR: No instance IDs found in summary — cannot run harness")
        sys.exit(1)

    print(f"Evaluate-only mode")
    print(f"  Run dir:      {run_dir}")
    print(f"  Run ID:       {run_id}")
    print(f"  Dataset:      {dataset_name} ({split})")
    print(f"  Instances:    {n_total}")
    print(f"  Predictions:  {predictions_path}")
    print(f"  Modal:        {modal}")

    if modal:
        docker_ok = True
    else:
        docker_ok = _check_docker()
    if not docker_ok:
        print("\nWARNING: Docker daemon not reachable.")
        print("  Use --modal for Modal cloud evaluation.")
        sys.exit(1)

    print("\n=== Running SWE-bench harness evaluation ===")
    try:
        from swebench.harness.run_evaluation import main as swebench_eval
        harness_run_id = _build_harness_run_id(
            run_id=run_id,
            retrieval_method=retrieval_method,
            results_path=results_path,
            existing_harness_run_id=existing_harness_run_id,
        )
        summary["harness_run_id"] = harness_run_id
        harness_report_dir = results_path / "harness_reports"
        harness_report_dir.mkdir(exist_ok=True)

        eval_report_path = swebench_eval(
            dataset_name=dataset_name,
            split=split,
            instance_ids=instance_ids,
            predictions_path=str(predictions_path),
            max_workers=4,  # Modal path ignores this; 4 controls local Docker thread count
            force_rebuild=False,
            cache_level="env",
            clean=False,
            open_file_limit=4096,
            run_id=harness_run_id,
            timeout=600,
            namespace=None,
            rewrite_reports=False,
            modal=modal,
            report_dir=str(harness_report_dir),
        )

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

    # Recompute cost fields now that harness_results is known
    summary.update(
        _compute_cost_summary_fields(
            per_instance_results=per_instance,
            retrieval_setup_tokens=summary.get("retrieval_setup_tokens", 0),
            harness_results=summary.get("harness_results"),
            setup_tokens_graph_built=summary.get("setup_tokens_graph_built", 0),
            setup_tokens_rag_built=summary.get("setup_tokens_rag_built", 0),
            setup_tokens_method_accounted=summary.get("setup_tokens_method_accounted"),
        )
    )

    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary updated: {summary_path}")
    if summary.get("cost_per_resolved_issue") is not None:
        print(f"Cost/resolved:  {summary['cost_per_resolved_issue']:,.1f} tokens/resolved")

    return summary


def run_patch_pipeline(
    manifest_path: str,
    results_dir: str,
    *,
    evaluate: bool = False,
    dry_run: bool = False,
    modal: bool = False,
    evaluate_only: bool = False,
    run_dir: str | None = None,
    resume: bool = False,
    n_workers: int = 1,
) -> dict:
    """
    Run retrieval → patch generation → optional evaluation for all instances in a manifest.

    When *evaluate_only* is True, skips patch generation entirely and runs the
    SWE-bench harness on an existing predictions.json from a prior Stage-1 run.
    *run_dir* must point to that run's directory (e.g. results/patch_runs/20260222_210339).

    Returns summary dict with per-instance results and aggregate metrics.
    """
    if evaluate_only:
        if not run_dir:
            print("ERROR: --evaluate-only requires --run-dir <path-to-existing-run>")
            sys.exit(1)
        return _run_evaluate_only(run_dir=run_dir, modal=modal)

    n_workers = max(1, int(n_workers))

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
    retrieval_max_files_raw = manifest.get("retrieval_max_files_for_patch", 6)
    retrieval_max_files_for_patch = None
    if retrieval_max_files_raw is not None:
        retrieval_max_files_for_patch = max(1, int(retrieval_max_files_raw))
    patch_apply_repair_retries = min(2, max(0, int(manifest.get("patch_apply_repair_retries", 2))))
    patch_retrieval_retry_max = min(1, max(0, int(manifest.get("patch_retrieval_retry_max", 1))))
    retrieval_redact_paths_in_issue_text = bool(manifest.get("retrieval_redact_paths_in_issue_text", True))
    patch_redact_paths_in_issue_text = bool(manifest.get("patch_redact_paths_in_issue_text", False))
    rag_symmetric_tools = bool(manifest.get("rag_symmetric_tools", False))
    repomap_config = {
        "map_tokens": int(manifest.get("repomap_like_map_tokens", 1000) or 1000),
        "top_k_files": int(manifest.get("repomap_like_top_k_files", 10) or 10),
        "use_llm_selector": bool(manifest.get("repomap_like_use_llm_selector", False)),
        "refresh_mode": str(manifest.get("repomap_like_refresh_mode", "static_per_issue") or "static_per_issue"),
        "edge_weights": dict(manifest.get("repomap_like_edge_weights", {}) or {}),
        "enable_same_module_edge": bool(manifest.get("repomap_like_enable_same_module_edge", False)),
        "personalization_enabled": bool(manifest.get("repomap_like_personalization_enabled", True)),
    }
    agentless_like_config = {
        "stage2_enabled": bool(manifest.get("agentless_like_stage2_enabled", True)),
        "stage3_enabled": bool(manifest.get("agentless_like_stage3_enabled", True)),
        "edit_location_samples": int(manifest.get("agentless_like_edit_location_samples", 4) or 4),
        "file_branch_top_n": int(manifest.get("agentless_like_file_branch_top_n", 3) or 3),
        "embed_branch_top_k": int(manifest.get("agentless_like_embed_branch_top_k", 20) or 20),
        "merge_top_k": int(manifest.get("agentless_like_merge_top_k", 12) or 12),
        "stage3_context_window_lines": int(manifest.get("agentless_like_stage3_context_window_lines", 10) or 10),
        "stage3_max_tokens_per_file": int(manifest.get("agentless_like_stage3_max_tokens_per_file", 1200) or 1200),
        "constrained_candidates_max": int(manifest.get("agentless_like_constrained_candidates_max", 200) or 200),
        "reject_out_of_candidate_paths": bool(manifest.get("agentless_like_reject_out_of_candidate_paths", True)),
    }
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
    instance_wall_clock_cap_s = float(manifest.get("instance_wall_clock_cap_s", 0.0))
    api_timeout_s = int(manifest.get("api_timeout_s", 120))
    if resume:
        if not run_dir:
            print("ERROR: --resume requires --run-dir <path-to-interrupted-stage-1-run>")
            sys.exit(1)
        results_path = Path(run_dir)
        run_id = results_path.name
    else:
        run_id, results_path = _allocate_run_output_dir(results_dir)

    patches_path = results_path / "patches"
    patches_path.mkdir(exist_ok=True)
    repos_root = results_path / "_repos"
    repos_root.mkdir(exist_ok=True)

    # Load any prior checkpoint (populated if resuming; empty on fresh start)
    _checkpoint: dict = _load_partial_checkpoint(results_path)
    if _checkpoint:
        print(f"Resume mode: {len(_checkpoint)} instances already complete, will skip them.")

    run_meta = {
        "run_id": run_id,
        "manifest": str(Path(manifest_path).resolve()),
        "dataset_name": dataset_name,
        "split": split,
        "repo_name": repo_name,
        "retrieval_method": retrieval_method,
        "manager_model": manager_model,
        "patch_model": patch_model,
        "n_instances_planned": len(instance_ids),
        "n_workers": int(max(1, n_workers)),
        "pid": os.getpid(),
        "provenance": _capture_provenance(manifest_path),
    }
    (results_path / "run_meta.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

    print(f"Run ID: {run_id}")
    print(f"Dataset: {dataset_name} ({split})")
    print(f"Instances: {len(instance_ids)}")
    print(f"Retrieval method: {retrieval_method}")
    print(f"Manager model: {manager_model}")
    print(f"Patch model: {patch_model}")
    print(f"Manager max turns: {manager_max_turns}")
    print(f"Patch max output tokens: {patch_max_output_tokens}")
    print(f"Patch max file chars: {patch_max_file_chars}")
    if retrieval_max_files_for_patch is None:
        print("Retrieval max files for patch: disabled")
    else:
        print(f"Retrieval max files for patch: {retrieval_max_files_for_patch}")
    print(f"Patch redact issue paths: {patch_redact_paths_in_issue_text}")
    print(f"API timeout (s): {api_timeout_s}")
    if instance_wall_clock_cap_s > 0:
        print(f"Instance wall-clock cap (s): {instance_wall_clock_cap_s}")
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

    # Restore completed instances from checkpoint (empty on fresh run)
    per_instance_results = [v["per_instance"] for v in _checkpoint.values()]
    swebench_predictions = {iid: v["prediction"] for iid, v in _checkpoint.items()}
    run_retrieval_setup_tokens = 0
    run_setup_tokens_graph_built = 0
    run_setup_tokens_rag_built = 0
    run_setup_tokens_method_accounted = 0

    def _run_repo_issue_batch(
        *,
        repo: str,
        repo_issues: list[dict],
        repo_dir: str,
        checkpoint_snapshot: dict,
        checkpoint_filename: str,
        worker_label: str | None = None,
    ) -> dict:
        """Run retrieval+patch loop for a chunk of issues against one repo clone."""
        label_prefix = f"[{worker_label}] " if worker_label else ""
        local_httpx_client = httpx.Client(timeout=api_timeout_s)
        local_client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(httpx_client=local_httpx_client),
        )

        try:
            import git as _git
            repo_git = _git.Repo(repo_dir)
            current_commit = None
            prefixes = tuple(dict.fromkeys(source_prefixes)) if source_prefixes else None
            from src.evaluation import NO_BASE_COMMIT
            commit_context_cache: dict[str, dict] = {}
            patch_agent_cache: dict[str, PatchAgent] = {}
            det_cfg = {
                "seed_k": manifest.get("deterministic_seed_k", 8),
                "depth": manifest.get("deterministic_depth", 2),
                "neighbor_cap": manifest.get("deterministic_neighbor_cap", 12),
            }

            local_predictions: dict[str, dict] = {}
            local_per_instance: list[dict] = []
            local_setup_tokens = 0
            local_setup_tokens_graph = 0
            local_setup_tokens_rag = 0
            local_setup_tokens_method = 0

            for issue in repo_issues:
                iid = issue["instance_id"]
                if iid in checkpoint_snapshot:
                    print(f"\n  {label_prefix}[{iid}] (skipped — already in checkpoint)")
                    continue
                print(f"\n  {label_prefix}[{iid}]")
                current_commit = _checkout_issue_commit(
                    repo_git=repo_git,
                    snapshot_commit=snapshot_commit,
                    issue=issue,
                    current_commit=current_commit,
                    issue_id=iid,
                )
                used_commit = repo_git.head.commit.hexsha
                commit_key = used_commit or NO_BASE_COMMIT
                if current_commit:
                    print(f"    {label_prefix}Commit: {current_commit[:12]}")
                else:
                    print(f"    {label_prefix}Commit: {used_commit[:12]}")
                instance_start_monotonic = time.monotonic()
                instance_deadline = (
                    instance_start_monotonic + instance_wall_clock_cap_s
                    if instance_wall_clock_cap_s > 0
                    else None
                )

                context = commit_context_cache.get(commit_key)
                if context is None:
                    context = _build_method_scoped_commit_context(
                        retrieval_method=retrieval_method,
                        repo_dir=repo_dir,
                        prefixes=prefixes,
                        client=local_client,
                        graph_builder_cls=GraphBuilder,
                        graph_index_cls=GraphIndex,
                        rag_index_cls=RAGIndex,
                        validate_commit_context_fn=validate_commit_context,
                    )
                    context["used_commit"] = used_commit
                    commit_context_cache[commit_key] = context
                    local_setup_tokens += int(context.get("retrieval_setup_tokens", 0) or 0)
                    local_setup_tokens_graph += int(context.get("setup_tokens_graph_built", 0) or 0)
                    local_setup_tokens_rag += int(context.get("setup_tokens_rag_built", 0) or 0)
                    local_setup_tokens_method += int(context.get("setup_tokens_method_accounted", 0) or 0)

                patch_agent = patch_agent_cache.get(commit_key)
                if patch_agent is None:
                    patch_agent = PatchAgent(
                        repo_dir,
                        local_client,
                        model=patch_model,
                        max_file_chars=patch_max_file_chars,
                        max_output_tokens=patch_max_output_tokens,
                    )
                    patch_agent_cache[commit_key] = patch_agent

                # --- Retrieval ---
                t0 = time.time()
                retrieval_error = None
                retrieved_files_pre_cap = 0
                retrieved_files_post_cap = 0
                if dry_run:
                    retrieved_files = issue.get("gold_files", [])[:2]
                    retrieval_tokens = {"total_tokens": 0, "stop_reason": "dry_run"}
                else:
                    try:
                        retrieved_files, retrieval_tokens = _run_with_rate_limit_backoff(
                            lambda: _run_retrieval(
                                issue,
                                graph=context["graph"],
                                graph_index=context["graph_index"],
                                rag_index=context["rag_index"],
                                bm25_index=context.get("bm25_index"),
                                rag_metadata_index=context.get("rag_metadata_index"),
                                client=local_client,
                                method=retrieval_method,
                                manager_model=manager_model,
                                manager_max_turns=manager_max_turns,
                                deterministic_config=det_cfg,
                                redact_paths=retrieval_redact_paths_in_issue_text,
                                rag_symmetric_tools=rag_symmetric_tools,
                                repo_dir=repo_dir,
                                include_prefixes=prefixes,
                                valid_file_paths=context.get("graph_file_paths"),
                                patch_max_file_chars=patch_max_file_chars,
                                repomap_config=repomap_config,
                                agentless_like_config=agentless_like_config,
                            ),
                            label=f"retrieval[{iid}]",
                            max_retries=rate_limit_max_retries,
                            initial_delay_s=rate_limit_initial_delay_s,
                            backoff_multiplier=rate_limit_backoff_multiplier,
                            max_delay_s=rate_limit_max_delay_s,
                            jitter_s=rate_limit_jitter_s,
                            deadline_monotonic=instance_deadline,
                        )
                    except TimeoutError as exc:
                        retrieval_error = exc
                        retrieved_files = []
                        retrieval_tokens = {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "tool_calls": 0,
                            "stop_reason": "timeout_budget_exceeded",
                            "error": str(exc),
                        }
                        print(f"    {label_prefix}Retrieval timed out: {exc}")
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
                        print(f"    {label_prefix}Retrieval failed after retries: {type(exc).__name__}")

                retrieved_files, retrieved_files_pre_cap, retrieved_files_post_cap = _cap_retrieved_files(
                    retrieved_files,
                    max_files=retrieval_max_files_for_patch,
                )
                retrieval_time = time.time() - t0
                cap_suffix = ""
                if retrieved_files_post_cap < retrieved_files_pre_cap:
                    cap_suffix = f" (capped {retrieved_files_pre_cap}->{retrieved_files_post_cap})"
                print(f"    {label_prefix}Retrieved: {retrieved_files}{cap_suffix}")
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
                        "stop_reason": (
                            "timeout_budget_exceeded"
                            if isinstance(retrieval_error, TimeoutError)
                            else "skipped_due_to_retrieval_error"
                        ),
                    }
                    status = "timeout_budget_exceeded" if isinstance(retrieval_error, TimeoutError) else "no_patch"
                else:
                    issue_text = prepare_issue_text(
                        issue.get("problem_statement", ""),
                        redact_paths=patch_redact_paths_in_issue_text,
                    )

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
                            deadline_monotonic=instance_deadline,
                        )

                    def apply_check_fn(patch_candidate: str):
                        return _git_apply_check(repo_dir, patch_candidate)

                    def retrieval_retry_fn(*, previous_files: list[str], failure_hint: str):
                        retry_files, retry_tokens = _run_with_rate_limit_backoff(
                            lambda: _run_retrieval(
                                issue,
                                graph=context["graph"],
                                graph_index=context["graph_index"],
                                rag_index=context["rag_index"],
                                bm25_index=context.get("bm25_index"),
                                rag_metadata_index=context.get("rag_metadata_index"),
                                client=local_client,
                                method=retrieval_method,
                                manager_model=manager_model,
                                manager_max_turns=manager_max_turns,
                                deterministic_config=det_cfg,
                                redact_paths=retrieval_redact_paths_in_issue_text,
                                retry_feedback=failure_hint,
                                rag_symmetric_tools=rag_symmetric_tools,
                                repo_dir=repo_dir,
                                include_prefixes=prefixes,
                                valid_file_paths=context.get("graph_file_paths"),
                                patch_max_file_chars=patch_max_file_chars,
                                repomap_config=repomap_config,
                                agentless_like_config=agentless_like_config,
                            ),
                            label=f"retrieval_retry[{iid}]",
                            max_retries=rate_limit_max_retries,
                            initial_delay_s=rate_limit_initial_delay_s,
                            backoff_multiplier=rate_limit_backoff_multiplier,
                            max_delay_s=rate_limit_max_delay_s,
                            jitter_s=rate_limit_jitter_s,
                            deadline_monotonic=instance_deadline,
                        )
                        capped_retry_files, retry_pre_cap, retry_post_cap = _cap_retrieved_files(
                            retry_files,
                            max_files=retrieval_max_files_for_patch,
                        )
                        retry_token_map = dict(retry_tokens or {})
                        retry_token_map["retrieved_files_pre_cap"] = retry_pre_cap
                        retry_token_map["retrieved_files_post_cap"] = retry_post_cap
                        return capped_retry_files, retry_token_map

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
                    except TimeoutError as exc:
                        patch_text = None
                        patch_tokens = {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "tool_calls": 0,
                            "stop_reason": "timeout_budget_exceeded",
                            "error": str(exc),
                        }
                        status = "timeout_budget_exceeded"
                        print(f"    {label_prefix}Patch generation timed out: {exc}")
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
                        print(f"    {label_prefix}Patch generation failed after retries: {type(exc).__name__}")
                patch_time = time.time() - t1

                print(f"    {label_prefix}Patch status: {status}")

                if per_instance_cooldown_s > 0 and not dry_run:
                    time.sleep(per_instance_cooldown_s)

                # Save patch to disk
                if patch_text and status in {"patched", "apply_failed"}:
                    patch_file = patches_path / f"{iid}.patch"
                    patch_file.write_text(patch_text)
                else:
                    patch_file = None

                prediction = _make_swebench_prediction(
                    instance_id=iid,
                    retrieval_method=retrieval_method,
                    patch_text=patch_text,
                    patch_status=status,
                )

                instance_result = {
                    "instance_id": iid,
                    "repo": repo,
                    "gold_files": issue.get("gold_files", []),
                    "retrieved_files": retrieved_files,
                    "retrieved_files_pre_cap": retrieved_files_pre_cap,
                    "retrieved_files_post_cap": retrieved_files_post_cap,
                    "retrieval_max_files_for_patch": retrieval_max_files_for_patch,
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
                    "total_time_s": round(time.monotonic() - instance_start_monotonic, 2),
                    "timeout_budget_exceeded": status == "timeout_budget_exceeded",
                }
                local_predictions[iid] = prediction
                local_per_instance.append(instance_result)
                _flush_instance_to_checkpoint(
                    run_dir=results_path,
                    instance_id=iid,
                    prediction=prediction,
                    per_instance=instance_result,
                    checkpoint_filename=checkpoint_filename,
                )

            return {
                "predictions": local_predictions,
                "per_instance": local_per_instance,
                "retrieval_setup_tokens": local_setup_tokens,
                "setup_tokens_graph_built": local_setup_tokens_graph,
                "setup_tokens_rag_built": local_setup_tokens_rag,
                "setup_tokens_method_accounted": local_setup_tokens_method,
            }
        finally:
            try:
                local_httpx_client.close()
            except Exception:
                pass

    for repo, repo_issues in by_repo.items():
        print(f"\n=== Repo: {repo} ({len(repo_issues)} issues) ===")
        repo_slug = _slugify_identifier(repo.replace("/", "_"))
        base_repo_dir = str((repos_root / f"{repo_slug}_base").resolve())
        clone_repo(repo, base_repo_dir)

        if n_workers <= 1:
            repo_result = _run_repo_issue_batch(
                repo=repo,
                repo_issues=repo_issues,
                repo_dir=base_repo_dir,
                checkpoint_snapshot=_checkpoint,
                checkpoint_filename="predictions_partial.jsonl",
                worker_label=None,
            )
            swebench_predictions.update(repo_result["predictions"])
            per_instance_results.extend(repo_result["per_instance"])
            run_retrieval_setup_tokens += int(repo_result["retrieval_setup_tokens"] or 0)
            run_setup_tokens_graph_built += int(repo_result["setup_tokens_graph_built"] or 0)
            run_setup_tokens_rag_built += int(repo_result["setup_tokens_rag_built"] or 0)
            run_setup_tokens_method_accounted += int(repo_result["setup_tokens_method_accounted"] or 0)
            continue

        issue_chunks = _distribute_instances(repo_issues, n_workers=n_workers)
        worker_specs = [(worker_id, chunk) for worker_id, chunk in enumerate(issue_chunks) if chunk]
        print(
            f"  Parallel Stage-1: workers={len(worker_specs)} requested={n_workers} "
            f"chunk_sizes={[len(chunk) for _, chunk in worker_specs]}"
        )

        worker_futures: dict[concurrent.futures.Future, int] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(worker_specs))) as pool:
            for worker_id, chunk in worker_specs:
                worker_repo_dir = str((repos_root / f"{repo_slug}_worker_{worker_id}").resolve())
                worker_repo_path = Path(worker_repo_dir)
                if worker_repo_path.exists() and not (worker_repo_path / ".git").exists():
                    shutil.rmtree(worker_repo_path)
                if not worker_repo_path.exists():
                    subprocess.run(
                        ["git", "clone", "--shared", "--quiet", base_repo_dir, worker_repo_dir],
                        check=True,
                    )

                future = pool.submit(
                    _run_repo_issue_batch,
                    repo=repo,
                    repo_issues=chunk,
                    repo_dir=worker_repo_dir,
                    checkpoint_snapshot=_checkpoint,
                    checkpoint_filename=f"predictions_worker_{worker_id}.jsonl",
                    worker_label=f"W{worker_id + 1}",
                )
                worker_futures[future] = worker_id

            for future in concurrent.futures.as_completed(worker_futures):
                worker_id = worker_futures[future]
                worker_result = future.result()
                print(
                    f"  Worker W{worker_id + 1} complete: "
                    f"{len(worker_result['per_instance'])} new instances"
                )
                swebench_predictions.update(worker_result["predictions"])
                per_instance_results.extend(worker_result["per_instance"])
                run_retrieval_setup_tokens += int(worker_result["retrieval_setup_tokens"] or 0)
                run_setup_tokens_graph_built += int(worker_result["setup_tokens_graph_built"] or 0)
                run_setup_tokens_rag_built += int(worker_result["setup_tokens_rag_built"] or 0)
                run_setup_tokens_method_accounted += int(worker_result["setup_tokens_method_accounted"] or 0)

    # Rebuild in-memory outputs from checkpoints (partial + worker files) so
    # summary/predictions remain complete and resume-safe after worker execution.
    _checkpoint_final = _load_partial_checkpoint(results_path)
    per_instance_results = [v["per_instance"] for v in _checkpoint_final.values()]
    swebench_predictions = {iid: v["prediction"] for iid, v in _checkpoint_final.items()}

    # Save predictions file for SWE-bench harness
    predictions_path = results_path / "predictions.json"
    predictions_path.write_text(json.dumps(swebench_predictions, indent=2))
    print(f"\nPredictions saved: {predictions_path}")

    robustness = _compute_patch_robustness_metrics(per_instance_results)
    n_patched = robustness["n_apply_ok"]
    n_total = len(per_instance_results)
    total_tokens = sum(r["total_tokens"] for r in per_instance_results)
    cost_fields = _compute_cost_summary_fields(
        per_instance_results=per_instance_results,
        retrieval_setup_tokens=run_retrieval_setup_tokens,
        harness_results=None,
        setup_tokens_graph_built=run_setup_tokens_graph_built,
        setup_tokens_rag_built=run_setup_tokens_rag_built,
        setup_tokens_method_accounted=run_setup_tokens_method_accounted,
    )

    summary = {
        "run_id": run_id,
        "manifest": manifest_path,
        "dataset_name": dataset_name,
        "retrieval_method": retrieval_method,
        "retrieval_max_files_for_patch": retrieval_max_files_for_patch,
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
        "harness_run_id": None,
        "per_instance": per_instance_results,
        **cost_fields,
    }

    # --- SWE-bench harness evaluation ---
    if evaluate:
        if modal:
            docker_ok = True  # Modal uses its own Sandbox runtime; no local Docker needed
        else:
            docker_ok = _check_docker()
        if not docker_ok:
            print("\nWARNING: Docker daemon not reachable. Skipping harness evaluation.")
            print("  Start Docker and rerun with: python run_patch.py --evaluate-only")
            print("  Or use Modal (no local Docker needed): python run_patch.py --evaluate --modal")
            summary["harness_skipped_reason"] = "docker_not_available"
        else:
            print("\n=== Running SWE-bench harness evaluation ===")
            try:
                from swebench.harness.run_evaluation import main as swebench_eval
                harness_run_id = _build_harness_run_id(
                    run_id=run_id,
                    retrieval_method=retrieval_method,
                    results_path=results_path,
                )
                summary["harness_run_id"] = harness_run_id
                harness_report_dir = results_path / "harness_reports"
                harness_report_dir.mkdir(exist_ok=True)

                eval_report_path = swebench_eval(
                    dataset_name=dataset_name,
                    split=split,
                    instance_ids=instance_ids,
                    predictions_path=str(predictions_path),
                    max_workers=4,  # Modal path ignores this; 4 controls local Docker thread count
                    force_rebuild=False,
                    cache_level="env",
                    clean=False,
                    open_file_limit=4096,
                    run_id=harness_run_id,
                    timeout=600,
                    namespace=None,
                    rewrite_reports=False,
                    modal=modal,
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

    # Refresh derived cost metrics once harness results (if any) are known.
    summary.update(
        _compute_cost_summary_fields(
            per_instance_results=per_instance_results,
            retrieval_setup_tokens=run_retrieval_setup_tokens,
            harness_results=summary.get("harness_results"),
            setup_tokens_graph_built=run_setup_tokens_graph_built,
            setup_tokens_rag_built=run_setup_tokens_rag_built,
            setup_tokens_method_accounted=run_setup_tokens_method_accounted,
        )
    )

    # Save summary
    summary_path = results_path / "patch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*60}")
    print(f"PATCH RUN COMPLETE")
    print(f"  Instances: {n_total}")
    print(f"  Patched:   {n_patched}/{n_total} ({n_patched/n_total:.1%})" if n_total else "  Patched: 0/0")
    print(f"  Tokens:    {total_tokens:,} total ({summary['avg_tokens_per_instance']:,.0f} avg/instance)")
    print(f"  Cost:      {summary['total_cost_tokens']:,} total (incl. setup)")
    if summary.get("harness_results"):
        r = summary["harness_results"]
        print(f"  Resolved:  {r['n_resolved']}/{n_total} ({r['resolved_rate']:.1%})")
        if summary.get("cost_per_resolved_issue") is not None:
            print(f"  Cost/Res:  {summary['cost_per_resolved_issue']:,.1f} tokens/resolved")
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
        help="Run SWE-bench harness after patch generation (requires Docker, or --modal)",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Run harness on Modal cloud (parallel Sandboxes, no local Docker needed). "
             "Requires 'modal setup' first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls; use gold files as retrieved, skip patch generation",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help=(
            "Stage 2: skip patch generation and run SWE-bench harness on an existing "
            "predictions.json. Requires --run-dir."
        ),
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Path to a prior Stage-1 run directory (e.g. results/patch_runs/20260222_210339). "
             "Used with --evaluate-only or --resume.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume an interrupted Stage-1 run. Requires --run-dir pointing to the interrupted "
            "run directory. Instances already in predictions_partial.jsonl are skipped; "
            "new instances are appended."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Stage-1 issue-level worker count per manifest (default: 1). "
            "Each worker uses an isolated repo clone and writes a worker checkpoint file."
        ),
    )
    args = parser.parse_args()

    run_patch_pipeline(
        manifest_path=args.manifest,
        results_dir=args.results_dir,
        evaluate=args.evaluate,
        modal=args.modal,
        dry_run=args.dry_run,
        evaluate_only=args.evaluate_only,
        run_dir=args.run_dir,
        resume=args.resume,
        n_workers=args.workers,
    )


if __name__ == "__main__":
    main()
