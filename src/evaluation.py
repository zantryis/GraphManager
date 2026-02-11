"""
Evaluation pipeline: Load SWE-bench issues, run all retrieval methods,
compute metrics, and produce results.
"""

import json
import hashlib
import re
import shutil
import time
from collections import Counter
from pathlib import Path

import git
from datasets import load_dataset
from google import genai

from .graph_builder import GraphBuilder, GraphIndex
from .manager_agent import ManagerAgent
from .rag_baseline import RAGAgent, RAGIndex, RawRAG

DEFAULT_SOURCE_PREFIXES = None  # None = index entire repo


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
    }
    digest = hashlib.sha1(json.dumps(key_obj, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"suite_{digest}"


def load_issues(repo: str = "pallets/flask", n: int = 10) -> list[dict]:
    """
    Load issues for a given repository from SWE-bench.
    Pulls from all splits to maximise coverage.
    """
    print(f"Loading SWE-bench issues for {repo}...")
    all_issues = []

    for split_name in ["test", "train", "dev"]:
        try:
            ds = load_dataset("SWE-bench/SWE-bench", split=split_name)
            matched = [row for row in ds if row["repo"] == repo]
            for issue in matched:
                all_issues.append({
                    "instance_id": issue["instance_id"],
                    "problem_statement": issue["problem_statement"],
                    "patch": issue["patch"],
                    "base_commit": issue["base_commit"],
                    "split": split_name,
                })
        except Exception as e:
            print(f"  Warning: could not load split '{split_name}': {e}")

    print(f"  Found {len(all_issues)} total {repo} issues across all splits")

    # Deduplicate by instance_id
    seen = set()
    unique = []
    for issue in all_issues:
        if issue["instance_id"] not in seen:
            seen.add(issue["instance_id"])
            unique.append(issue)
    all_issues = unique

    if len(all_issues) < n:
        print(f"  Warning: only found {len(all_issues)} issues (requested {n})")
        n = len(all_issues)

    selected = all_issues[:n]
    for issue in selected:
        issue["gold_files"] = normalize_file_paths(extract_gold_files(issue["patch"]))
        print(f"  {issue['instance_id']}: gold files = {issue['gold_files']}")

    return selected


def extract_gold_files(patch: str) -> list[str]:
    """Extract modified file paths from a unified diff patch."""
    pattern = r"^diff --git a/.+ b/(.+)$"
    matches = re.findall(pattern, patch, re.MULTILINE)
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def normalize_file_path(path: str) -> str:
    """Normalize paths so predictions and gold labels are scored consistently."""
    if not path:
        return ""
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def normalize_file_paths(paths: list[str]) -> list[str]:
    """Normalize and deduplicate paths while preserving order."""
    seen = set()
    normalized_paths = []
    for path in paths:
        normalized = normalize_file_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_paths.append(normalized)
    return normalized_paths


def compute_metrics(predicted: list[str], gold: list[str]) -> dict:
    """Compute precision, recall, and F1 at the file level."""
    if not predicted and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not predicted:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not gold:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    pred_set = set(predicted)
    gold_set = set(gold)
    tp = len(pred_set & gold_set)

    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def clone_repo(repo_name: str, target_dir: str, base_commit: str | None = None) -> str:
    """Clone a GitHub repo and optionally checkout a specific commit."""
    repo_url = f"https://github.com/{repo_name}.git"
    target = Path(target_dir)

    if target.exists() and (target / ".git").exists():
        print(f"  Repo already exists at {target_dir}")
        repo = git.Repo(target_dir)
    else:
        print(f"  Cloning {repo_name} to {target_dir}...")
        repo = git.Repo.clone_from(repo_url, target_dir)

    if base_commit:
        print(f"  Checking out commit {base_commit[:12]}...")
        repo.git.checkout(base_commit, force=True)

    return target_dir


def pick_base_commit(issues: list[dict]) -> str | None:
    """Pick the most common base_commit among selected issues."""
    commits = [i["base_commit"] for i in issues if i.get("base_commit")]
    if not commits:
        return None
    counter = Counter(commits)
    most_common = counter.most_common(1)[0][0]
    print(f"  Most common base commit: {most_common[:12]} ({counter[most_common]}/{len(commits)} issues)")
    return most_common


def run_with_retries(callable_fn, retries: int = 3, initial_delay_s: float = 3.0):
    """Retry transient rate-limit failures from the API."""
    delay_s = initial_delay_s
    for attempt in range(retries + 1):
        try:
            return callable_fn()
        except Exception as e:
            msg = str(e).upper()
            should_retry = ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < retries
            if not should_retry:
                raise
            print(f"    Rate limited (attempt {attempt + 1}/{retries + 1}), retrying in {delay_s:.1f}s...")
            time.sleep(delay_s)
            delay_s *= 2


def run_experiment(
    gemini_api_key: str,
    n_issues: int = 10,
    results_dir: str = "results",
    create_run_subdir: bool = True,
    source_prefixes: tuple[str, ...] | None = DEFAULT_SOURCE_PREFIXES,
    manager_max_turns: int = 3,
    rag_max_turns: int = 10,
    manager_retrieval_mode: str = "progressive",
    rag_retrieval_mode: str = "progressive",
    task_family: str = "swe-bench",
    dataset_name: str = "SWE-bench/SWE-bench",
    repo_name: str = "pallets/flask",
    issue_set_id: str | None = None,
    suite_id: str | None = None,
    repeat_count: int = 1,
    repeat_index: int = 1,
    experiment_notes: str = "",
):
    """
    Main experiment: compare Graph-Manager vs RAG-Agent vs Raw-RAG
    on Flask issues from SWE-bench.
    """
    base_results_path = Path(results_dir)
    base_results_path.mkdir(parents=True, exist_ok=True)
    if create_run_subdir:
        run_id = time.strftime("%Y%m%d_%H%M%S")
        results_path = base_results_path / "runs" / run_id
    else:
        results_path = base_results_path
    results_path.mkdir(parents=True, exist_ok=True)
    print(f"Results directory: {results_path}")

    # Initialize Gemini client
    client = genai.Client(api_key=gemini_api_key)
    print("Gemini client initialized.")

    # Step 1: Load issues
    print(f"\n=== Step 1: Loading {repo_name} issues ===")
    issues = load_issues(repo=repo_name, n=n_issues)
    if not issues:
        print(f"ERROR: No {repo_name} issues found. Aborting.")
        return
    issue_instance_ids = [issue.get("instance_id", "") for issue in issues]

    inferred_issue_set_id = issue_set_id or build_issue_set_id(repo_name, issue_instance_ids)
    inferred_suite_id = suite_id or build_suite_id(
        task_family=task_family,
        dataset_name=dataset_name,
        repo_name=repo_name,
        issue_set_id=inferred_issue_set_id,
        n_issues_requested=n_issues,
        source_prefixes=source_prefixes,
        manager_max_turns=manager_max_turns,
        rag_max_turns=rag_max_turns,
    )

    # Step 2: Clone repository
    repo_short = repo_name.split("/")[-1]
    print(f"\n=== Step 2: Cloning {repo_name} ===")
    repo_dir = str(Path.cwd() / f"{repo_short}_repo")
    base_commit = pick_base_commit(issues)
    clone_repo(repo_name, repo_dir, base_commit)

    # Step 3: Build knowledge graph
    print("\n=== Step 3: Building knowledge graph ===")
    t0 = time.time()
    builder = GraphBuilder(repo_dir, include_prefixes=source_prefixes)
    graph = builder.build()
    graph_build_time = time.time() - t0
    print(f"  Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges ({graph_build_time:.1f}s)")
    builder.save(str(results_path / "graph.json"))

    # Step 4: Build graph vector index
    print("\n=== Step 4: Building graph vector index ===")
    t0 = time.time()
    graph_index = GraphIndex(graph, client)
    graph_index.build()
    graph_index_time = time.time() - t0
    graph_embedding_tokens = graph_index.embedding_tokens_estimate

    # Step 5: Build RAG indices
    print("\n=== Step 5: Building RAG indices ===")
    t0 = time.time()
    rag_func = RAGIndex(
        repo_dir,
        client,
        chunk_strategy="function",
        include_prefixes=source_prefixes,
    )
    rag_func.build()
    rag_func_time = time.time() - t0
    rag_func_embedding_tokens = rag_func.embedding_tokens_estimate

    t0 = time.time()
    rag_fixed = RAGIndex(
        repo_dir,
        client,
        chunk_strategy="fixed",
        include_prefixes=source_prefixes,
    )
    rag_fixed.build()
    rag_fixed_time = time.time() - t0
    rag_fixed_embedding_tokens = rag_fixed.embedding_tokens_estimate

    # Step 6: Run all methods on each issue
    print("\n=== Step 6: Running evaluation ===")
    manager_agent = ManagerAgent(
        graph,
        graph_index,
        client,
        retrieval_mode=manager_retrieval_mode,
    )
    rag_agent = RAGAgent(
        rag_func,
        client,
        retrieval_mode=rag_retrieval_mode,
    )
    raw_rag_func = RawRAG(rag_func)
    raw_rag_fixed = RawRAG(rag_fixed)

    detailed_results = []

    for i, issue in enumerate(issues):
        print(f"\n--- Issue {i+1}/{len(issues)}: {issue['instance_id']} ---")
        print(f"  Gold files: {issue['gold_files']}")

        issue_results = {
            "instance_id": issue["instance_id"],
            "gold_files": issue["gold_files"],
            "methods": {},
        }

        # Method 1: Graph-Manager
        print("  Running Graph-Manager...")
        try:
            files, tokens = run_with_retries(
                lambda: manager_agent.find_relevant_files(
                    issue["problem_statement"],
                    max_turns=manager_max_turns,
                )
            )
            normalized_files = normalize_file_paths(files)
            metrics = compute_metrics(normalized_files, issue["gold_files"])
            issue_results["methods"]["graph_manager"] = {
                "predicted_files_raw": files,
                "predicted_files": normalized_files,
                "tokens": tokens,
                "metrics": metrics,
            }
            print(f"    Files: {normalized_files}")
            print(f"    P={metrics['precision']:.2f} R={metrics['recall']:.2f} F1={metrics['f1']:.2f} | Tokens: {tokens['total_tokens']}")
        except Exception as e:
            print(f"    ERROR: {e}")
            issue_results["methods"]["graph_manager"] = {"error": str(e)}

        # Method 2: RAG-Agent (function-level chunks)
        print("  Running RAG-Agent...")
        try:
            files, tokens = run_with_retries(
                lambda: rag_agent.find_relevant_files(
                    issue["problem_statement"],
                    max_turns=rag_max_turns,
                )
            )
            normalized_files = normalize_file_paths(files)
            metrics = compute_metrics(normalized_files, issue["gold_files"])
            issue_results["methods"]["rag_agent"] = {
                "predicted_files_raw": files,
                "predicted_files": normalized_files,
                "tokens": tokens,
                "metrics": metrics,
            }
            print(f"    Files: {normalized_files}")
            print(f"    P={metrics['precision']:.2f} R={metrics['recall']:.2f} F1={metrics['f1']:.2f} | Tokens: {tokens['total_tokens']}")
        except Exception as e:
            print(f"    ERROR: {e}")
            issue_results["methods"]["rag_agent"] = {"error": str(e)}

        # Method 3: Raw RAG (function-level)
        print("  Running Raw-RAG (function)...")
        try:
            files, tokens = raw_rag_func.find_relevant_files(issue["problem_statement"])
            normalized_files = normalize_file_paths(files)
            metrics = compute_metrics(normalized_files, issue["gold_files"])
            issue_results["methods"]["raw_rag_function"] = {
                "predicted_files_raw": files,
                "predicted_files": normalized_files,
                "tokens": tokens,
                "metrics": metrics,
            }
            print(f"    Files: {normalized_files[:5]}{'...' if len(normalized_files) > 5 else ''}")
            print(f"    P={metrics['precision']:.2f} R={metrics['recall']:.2f} F1={metrics['f1']:.2f}")
        except Exception as e:
            print(f"    ERROR: {e}")
            issue_results["methods"]["raw_rag_function"] = {"error": str(e)}

        # Method 4: Raw RAG (fixed-size)
        print("  Running Raw-RAG (fixed)...")
        try:
            files, tokens = raw_rag_fixed.find_relevant_files(issue["problem_statement"])
            normalized_files = normalize_file_paths(files)
            metrics = compute_metrics(normalized_files, issue["gold_files"])
            issue_results["methods"]["raw_rag_fixed"] = {
                "predicted_files_raw": files,
                "predicted_files": normalized_files,
                "tokens": tokens,
                "metrics": metrics,
            }
            print(f"    Files: {normalized_files[:5]}{'...' if len(normalized_files) > 5 else ''}")
            print(f"    P={metrics['precision']:.2f} R={metrics['recall']:.2f} F1={metrics['f1']:.2f}")
        except Exception as e:
            print(f"    ERROR: {e}")
            issue_results["methods"]["raw_rag_fixed"] = {"error": str(e)}

        detailed_results.append(issue_results)

    # Step 7: Aggregate and save results
    print("\n=== Step 7: Aggregating results ===")
    summary = aggregate_results(
        detailed_results,
        setup_costs={
            "graph_manager": {
                "build_time_s": graph_build_time + graph_index_time,
                "embedding_tokens": graph_embedding_tokens,
            },
            "rag_agent": {
                "build_time_s": rag_func_time,
                "embedding_tokens": rag_func_embedding_tokens,
            },
            "raw_rag_function": {
                "build_time_s": rag_func_time,
                "embedding_tokens": rag_func_embedding_tokens,
            },
            "raw_rag_fixed": {
                "build_time_s": rag_fixed_time,
                "embedding_tokens": rag_fixed_embedding_tokens,
            },
        },
    )
    summary["_meta"] = {
        "run_id": results_path.name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task_family": task_family,
        "dataset_name": dataset_name,
        "repo_name": repo_name,
        "issue_set_id": inferred_issue_set_id,
        "suite_id": inferred_suite_id,
        "n_issues_requested": n_issues,
        "n_issues_evaluated": len(issues),
        "issue_instance_ids": issue_instance_ids,
        "source_prefixes": list(source_prefixes) if source_prefixes else [],
        "manager_max_turns": manager_max_turns,
        "rag_max_turns": rag_max_turns,
        "manager_model": manager_agent.model,
        "rag_model": rag_agent.model,
        "manager_mode": manager_agent.retrieval_mode,
        "rag_mode": rag_agent.retrieval_mode,
        "repeat_count": repeat_count,
        "repeat_index": repeat_index,
        "notes": experiment_notes,
    }

    # Save detailed results
    with open(results_path / "detailed_results.json", "w") as f:
        json.dump(detailed_results, f, indent=2)

    # Save summary
    with open(results_path / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Keep a copy of the latest run in a stable path for quick inspection
    if create_run_subdir:
        latest_path = base_results_path / "latest"
        if latest_path.exists():
            shutil.rmtree(latest_path)
        latest_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(results_path / "graph.json", latest_path / "graph.json")
        shutil.copy2(results_path / "detailed_results.json", latest_path / "detailed_results.json")
        shutil.copy2(results_path / "summary.json", latest_path / "summary.json")

        # Backward-compatible convenience copies at results/*.json
        shutil.copy2(results_path / "graph.json", base_results_path / "graph.json")
        shutil.copy2(results_path / "detailed_results.json", base_results_path / "detailed_results.json")
        shutil.copy2(results_path / "summary.json", base_results_path / "summary.json")

    # Print results table
    print_results_table(summary)

    print(f"\nResults saved to {results_path}/")
    return summary


def aggregate_results(detailed_results: list[dict], setup_costs: dict) -> dict:
    """Compute aggregate metrics across all issues for each method."""
    methods = ["graph_manager", "rag_agent", "raw_rag_function", "raw_rag_fixed"]
    summary = {}

    for method in methods:
        precisions = []
        recalls = []
        f1s = []
        total_prompt_tokens = 0
        total_candidate_tokens = 0
        total_tokens = 0
        total_query_embedding_tokens = 0
        n_success = 0

        for result in detailed_results:
            method_data = result["methods"].get(method, {})
            if "error" in method_data:
                continue
            n_success += 1
            metrics = method_data.get("metrics", {})
            precisions.append(metrics.get("precision", 0))
            recalls.append(metrics.get("recall", 0))
            f1s.append(metrics.get("f1", 0))
            tokens = method_data.get("tokens", {})
            total_prompt_tokens += tokens.get("prompt_tokens", 0)
            total_candidate_tokens += tokens.get("candidate_tokens", 0)
            total_tokens += tokens.get("total_tokens", 0)
            total_query_embedding_tokens += tokens.get("embedding_tokens", 0)

        n = max(n_success, 1)
        setup = setup_costs.get(method, {})

        summary[method] = {
            "n_issues": n_success,
            "mean_precision": sum(precisions) / n if precisions else 0,
            "mean_recall": sum(recalls) / n if recalls else 0,
            "mean_f1": sum(f1s) / n if f1s else 0,
            "total_prompt_tokens": total_prompt_tokens,
            "total_candidate_tokens": total_candidate_tokens,
            "total_llm_tokens": total_tokens,
            "avg_llm_tokens_per_issue": total_tokens / n,
            "total_query_embedding_tokens": total_query_embedding_tokens,
            "setup_embedding_tokens": setup.get("embedding_tokens", 0),
            "setup_time_s": setup.get("build_time_s", 0),
            "total_cost_tokens": total_tokens + total_query_embedding_tokens + setup.get("embedding_tokens", 0),
        }

    return summary


def print_results_table(summary: dict):
    """Print a formatted comparison table."""
    methods = ["graph_manager", "rag_agent", "raw_rag_function", "raw_rag_fixed"]
    labels = {
        "graph_manager": "Graph-Manager",
        "rag_agent": "RAG-Agent",
        "raw_rag_function": "Raw-RAG (func)",
        "raw_rag_fixed": "Raw-RAG (fixed)",
    }

    print("\n" + "=" * 90)
    print("RESULTS SUMMARY")
    print("=" * 90)
    header = f"{'Method':<20} {'P':>6} {'R':>6} {'F1':>6} {'LLM Tok':>10} {'Avg/Issue':>10} {'Setup Tok':>10}"
    print(header)
    print("-" * 90)

    for method in methods:
        s = summary.get(method, {})
        print(
            f"{labels.get(method, method):<20} "
            f"{s.get('mean_precision', 0):>6.3f} "
            f"{s.get('mean_recall', 0):>6.3f} "
            f"{s.get('mean_f1', 0):>6.3f} "
            f"{s.get('total_llm_tokens', 0):>10,} "
            f"{s.get('avg_llm_tokens_per_issue', 0):>10,.0f} "
            f"{s.get('setup_embedding_tokens', 0):>10,}"
        )

    print("=" * 90)
    print("\nKey: P=Precision, R=Recall, F1=F1 Score, LLM Tok=Total LLM tokens across all issues")
    print("     Avg/Issue=Mean LLM tokens per issue, Setup Tok=One-time embedding tokens")
