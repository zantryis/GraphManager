"""
Evaluation pipeline: Load SWE-bench issues, run all retrieval methods,
compute metrics, and produce results.
"""

import json
import re
import shutil
import time
from pathlib import Path

import git
from google import genai

from .bm25_baseline import BM25Index
from .datasets import build_issue_adapter
from .deterministic_retrieval import DEFAULT_WEIGHTS, DeterministicGraphRetriever
from .graph_builder import GraphBuilder, GraphIndex
from .manager_agent import ManagerAgent
from .repomap_like import RepoMapLikeRetriever
from .path_resolution import (
    canonicalize_file_paths,
    normalize_file_path as _normalize_file_path,
    normalize_file_paths as _normalize_file_paths,
)
from .rag_baseline import RAGAgent, RAGIndex, RawRAG
from .agentless_like_localization import AgentlessLikeLocalizer
from .run_ids import build_issue_set_id, build_suite_id

DEFAULT_SOURCE_PREFIXES = None  # None = index entire repo
NO_BASE_COMMIT = "__NO_BASE_COMMIT__"


def load_issues(
    repo: str = "pallets/flask",
    n: int = 10,
    *,
    task_family: str = "swe-bench",
    dataset_name: str = "SWE-bench/SWE-bench",
    instance_ids: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """
    Load normalized issues for a repository via dataset adapters.
    """
    print(f"Loading issues for {repo} from {dataset_name} ({task_family})...")
    adapter = build_issue_adapter(task_family=task_family, dataset_name=dataset_name)
    selected = adapter.load_issues(
        repo=repo,
        n=n,
        instance_ids=list(instance_ids) if instance_ids else None,
    )

    print(f"  Found {len(selected)} issues")
    if len(selected) < n:
        print(f"  Warning: only found {len(selected)} issues (requested {n})")

    for issue in selected:
        issue["gold_files"] = normalize_file_paths(issue.get("gold_files", []))
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
    return _normalize_file_path(path)


def normalize_file_paths(paths: list[str]) -> list[str]:
    """Normalize and deduplicate paths while preserving order."""
    return _normalize_file_paths(paths)


def compute_metrics(predicted: list[str], gold: list[str]) -> dict:
    """Compute precision, recall, and F1 at the file level."""
    if not gold:
        # Empty gold indicates a data-loading error. Do NOT return F1=1.0 for the
        # empty-vs-empty case — that silently inflates mean F1 across instances.
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "skipped_empty_gold": True}
    if not predicted:
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


def group_issues_by_base_commit(issues: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """Group issues by base_commit while preserving first-seen order."""
    grouped: dict[str, list[dict]] = {}
    ordered_keys: list[str] = []
    for issue in issues:
        commit = issue.get("base_commit") or NO_BASE_COMMIT
        if commit not in grouped:
            grouped[commit] = []
            ordered_keys.append(commit)
        grouped[commit].append(issue)
    result = []
    for commit in ordered_keys:
        result.append((None if commit == NO_BASE_COMMIT else commit, grouped[commit]))
    return result


def validate_commit_context(
    context: dict,
    *,
    required_methods: tuple[str, ...] | None = None,
) -> None:
    """Raise ValueError if any required index for this context is empty.

    An empty index (setup_embedding_tokens == 0 for a required method family)
    means source_prefixes matched no Python files. This can silently produce
    all-zero F1 results that pass CI gates.
    """
    setup_costs = context.get("setup_costs", {})
    graph_embedding_methods = {"gm_progressive", "gm_baseline", "gm_deterministic"}
    graph_structure_methods = graph_embedding_methods | {"repomap_like", "agentless_like_localization"}
    rag_function_methods = {"rag_progressive", "rag_baseline", "raw_rag_function", "agentless_like_localization"}
    rag_fixed_methods = {"raw_rag_fixed"}
    required = set(required_methods or ALL_METHODS)
    unknown = required - set(ALL_METHODS)
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown required methods in validate_commit_context: {unknown_list}")

    needs_graph_structure = bool(required & graph_structure_methods)
    needs_graph_embedding = bool(required & graph_embedding_methods)
    needs_rag_function = bool(required & rag_function_methods)
    needs_rag_fixed = bool(required & rag_fixed_methods)

    if needs_graph_structure:
        graph_file_paths = context.get("graph_file_paths", set())
        if not graph_file_paths:
            raise ValueError(
                "Graph structure is empty (no Python files in graph_file_paths). "
                "source_prefixes likely matches no Python files in the repo at this commit. "
                "Check source_prefixes against the actual directory layout."
            )

    if needs_graph_embedding:
        graph_tokens = max(
            int(setup_costs.get(method, {}).get("embedding_tokens", 0) or 0)
            for method in graph_embedding_methods
        )
        if graph_tokens == 0:
            raise ValueError(
                "Graph index is empty (gm_* setup_embedding_tokens=0). "
                "source_prefixes likely matches no Python files in the repo at this commit. "
                "Check source_prefixes against the actual directory layout."
            )

    if needs_rag_function:
        rag_func_tokens = max(
            int(setup_costs.get(method, {}).get("embedding_tokens", 0) or 0)
            for method in rag_function_methods
        )
        if rag_func_tokens == 0:
            raise ValueError(
                "RAG function index is empty (rag_progressive/rag_baseline/raw_rag_function "
                "setup_embedding_tokens=0). source_prefixes likely matches no Python files "
                "in the repo at this commit. Check source_prefixes against the actual "
                "directory layout."
            )

    if needs_rag_fixed:
        rag_fixed_tokens = int(setup_costs.get("raw_rag_fixed", {}).get("embedding_tokens", 0) or 0)
        if rag_fixed_tokens == 0:
            raise ValueError(
                "RAG fixed index is empty (raw_rag_fixed setup_embedding_tokens=0). "
                "source_prefixes likely matches no Python files in the repo at this commit. "
                "Check source_prefixes against the actual directory layout."
            )

    if "bm25" in required:
        bm25_file_paths = context.get("bm25_file_paths", set())
        if not bm25_file_paths:
            raise ValueError(
                "BM25 index is empty (no .py files indexed). "
                "source_prefixes likely matches no Python files in the repo at this commit. "
                "Check source_prefixes against the actual directory layout."
            )



def build_issue_groups(
    issues: list[dict],
    *,
    evaluation_track: str = "strict_commit_fidelity",
    snapshot_commit: str | None = None,
) -> list[tuple[str | None, list[dict]]]:
    """Build evaluation issue groups for strict or same-snapshot tracks."""
    if evaluation_track == "strict_commit_fidelity":
        return group_issues_by_base_commit(issues)
    if evaluation_track == "same_snapshot_amortized":
        commit = snapshot_commit
        if commit is None and issues:
            commit = issues[0].get("base_commit")
        return [(commit, list(issues))]
    raise ValueError(f"Unsupported evaluation track: {evaluation_track}")


def run_with_retries(callable_fn, retries: int = 3, initial_delay_s: float = 3.0):
    """Retry transient rate-limit failures from the API."""
    delay_s = initial_delay_s
    for attempt in range(retries + 1):
        try:
            return callable_fn()
        except Exception as e:
            msg = str(e).upper()
            transient_error = (
                "429" in msg
                or "RESOURCE_EXHAUSTED" in msg
                or "503" in msg
                or "UNAVAILABLE" in msg
            )
            should_retry = transient_error and attempt < retries
            if not should_retry:
                raise
            print(f"    Rate limited (attempt {attempt + 1}/{retries + 1}), retrying in {delay_s:.1f}s...")
            time.sleep(delay_s)
            delay_s *= 2


_PY_PATH_PATTERN = re.compile(r"\b(?:[\w.-]+/)+[\w.-]+\.py\b")
_CODE_FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_CHECKBOX_LINE_PATTERN = re.compile(r"^\s*[-*]\s*\[[xX ]\]\s+")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}#{2,6}\s+(.+?)\s*$")
_NOISE_SECTION_KEYWORDS = (
    "checklist",
    "environment",
    "logs",
    "traceback",
    "stack trace",
    "system info",
    "versions",
)


def redact_issue_paths(issue_text: str) -> str:
    """Redact explicit Python file paths in issue text to reduce path-copy leakage."""
    if not issue_text:
        return ""
    return _PY_PATH_PATTERN.sub("<PY_PATH>", issue_text)


def _is_noise_heading(heading: str) -> bool:
    lowered = heading.strip().lower()
    return any(keyword in lowered for keyword in _NOISE_SECTION_KEYWORDS)


def prepare_issue_text(
    issue_text: str,
    *,
    redact_paths: bool = True,
    max_chars: int = 4000,
) -> str:
    """
    Compact issue text for retrieval by stripping template-heavy noise.

    - drops fenced code/log blocks,
    - removes known low-signal template sections (checklists/env/logs),
    - removes checkbox lines,
    - optionally redacts explicit file paths,
    - caps final payload length.
    """
    if not issue_text:
        return ""

    text = issue_text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CODE_FENCE_PATTERN.sub("\n", text)

    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush_section():
        if current_heading is not None or current_lines:
            sections.append((current_heading, current_lines.copy()))

    for raw_line in text.splitlines():
        heading_match = _MARKDOWN_HEADING_PATTERN.match(raw_line)
        if heading_match:
            flush_section()
            current_heading = heading_match.group(1).strip()
            current_lines = []
            continue
        if _CHECKBOX_LINE_PATTERN.match(raw_line):
            continue
        current_lines.append(raw_line)
    flush_section()

    kept_blocks: list[str] = []
    for heading, lines in sections:
        if heading and _is_noise_heading(heading):
            continue
        body = "\n".join(lines).strip()
        if not body:
            continue
        if heading:
            kept_blocks.append(f"### {heading}\n{body}")
        else:
            kept_blocks.append(body)

    compact = "\n\n".join(kept_blocks).strip()
    if not compact:
        compact = text.strip()

    # Keep spacing predictable for retrieval prompts.
    compact = re.sub(r"\n{3,}", "\n\n", compact).strip()
    if redact_paths:
        compact = redact_issue_paths(compact)

    if max_chars > 0 and len(compact) > max_chars:
        if max_chars <= 3:
            return compact[:max_chars]
        compact = compact[: max_chars - 3].rstrip() + "..."
    return compact


def normalize_token_usage(tokens: dict | None) -> dict:
    """Normalize token usage payloads across agents/methods."""
    src = tokens or {}
    return {
        "prompt_tokens": int(src.get("prompt_tokens", 0) or 0),
        "candidate_tokens": int(src.get("candidate_tokens", 0) or 0),
        "total_tokens": int(src.get("total_tokens", 0) or 0),
        "query_embedding_tokens": int(
            src.get("query_embedding_tokens", src.get("embedding_tokens", 0)) or 0
        ),
        "tool_calls": int(src.get("tool_calls", 0) or 0),
        "tool_cache_hits": int(src.get("tool_cache_hits", 0) or 0),
        "tool_response_chars": int(src.get("tool_response_chars", 0) or 0),
        "tool_calls_by_name": dict(src.get("tool_calls_by_name", {}) or {}),
        "stop_reason": str(src.get("stop_reason", "") or ""),
        "manager_telemetry": dict(src.get("manager_telemetry", {}) or {}),
    }


def build_cost_components(tokens: dict, setup_embedding_tokens: int) -> dict:
    """Build per-issue cost breakdown."""
    llm_tokens = int(tokens.get("total_tokens", 0) or 0)
    query_tokens = int(tokens.get("query_embedding_tokens", 0) or 0)
    setup_tokens = int(setup_embedding_tokens or 0)
    return {
        "setup_embedding_tokens": setup_tokens,
        "llm_tokens": llm_tokens,
        "query_embedding_tokens": query_tokens,
        "total_cost_tokens": setup_tokens + llm_tokens + query_tokens,
    }


def build_error_result(error: Exception | str, setup_embedding_tokens: int) -> dict:
    """Build a standardized failed-method result with zero metrics."""
    tokens = normalize_token_usage({})
    return {
        "predicted_files_raw": [],
        "predicted_files_normalized": [],
        "predicted_files": [],
        "tokens": tokens,
        "metrics": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        "cost_tokens": build_cost_components(tokens, setup_embedding_tokens),
        "error": str(error),
    }


def _copy_run_artifacts(
    *,
    run_path: Path,
    base_results_path: Path,
    create_run_subdir: bool,
) -> None:
    """Copy stable artifacts from a run directory into latest/ convenience paths."""
    if not create_run_subdir:
        return

    latest_path = base_results_path / "latest"
    if latest_path.exists():
        shutil.rmtree(latest_path)
    latest_path.mkdir(parents=True, exist_ok=True)

    artifact_names = ("graph.json", "detailed_results.json", "summary.json")
    for name in artifact_names:
        src = run_path / name
        if not src.exists():
            continue
        shutil.copy2(src, latest_path / name)
        shutil.copy2(src, base_results_path / name)


def run_experiment(
    gemini_api_key: str,
    n_issues: int = 10,
    results_dir: str = "results",
    create_run_subdir: bool = True,
    source_prefixes: tuple[str, ...] | None = DEFAULT_SOURCE_PREFIXES,
    manager_max_turns: int = 3,
    rag_max_turns: int = 10,
    task_family: str = "swe-bench",
    dataset_name: str = "SWE-bench/SWE-bench",
    repo_name: str = "pallets/flask",
    issue_set_id: str | None = None,
    suite_id: str | None = None,
    repeat_count: int = 1,
    repeat_index: int = 1,
    experiment_notes: str = "",
    redact_paths_in_issue_text: bool = True,
    evaluation_track: str = "strict_commit_fidelity",
    snapshot_commit: str | None = None,
    instance_ids: tuple[str, ...] | None = None,
    domain: str = "",
    seed: int | None = None,
    deterministic_seed_k: int = 8,
    deterministic_depth: int = 2,
    deterministic_neighbor_cap: int = 12,
    deterministic_min_return_files: int = 1,
    deterministic_score_ratio_cutoff: float = 0.70,
    deterministic_min_score_cutoff: float = 0.0,
    deterministic_hub_degree_threshold: int = 20,
    deterministic_hub_penalty_scale: float = 0.35,
    deterministic_w_sem: float = DEFAULT_WEIGHTS["w_sem"],
    deterministic_w_graph: float = DEFAULT_WEIGHTS["w_graph"],
    deterministic_w_conf: float = DEFAULT_WEIGHTS["w_conf"],
    deterministic_w_hint: float = DEFAULT_WEIGHTS["w_hint"],
    deterministic_w_pen: float = DEFAULT_WEIGHTS["w_pen"],
    methods: tuple[str, ...] | None = None,
    model_name: str = "gemini-3-flash-preview",
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
    enabled_methods = tuple(methods or ALL_METHODS)
    if not enabled_methods:
        raise ValueError("At least one retrieval method must be enabled")
    unknown_methods = sorted(set(enabled_methods) - set(ALL_METHODS))
    if unknown_methods:
        raise ValueError(f"Unsupported methods requested: {', '.join(unknown_methods)}")
    enabled_method_set = set(enabled_methods)
    print(f"Enabled methods: {', '.join(enabled_methods)}")

    # Step 1: Load issues
    print(f"\n=== Step 1: Loading {repo_name} issues ===")
    manifest_instance_ids = tuple(instance_ids or ())
    requested_issue_count = len(manifest_instance_ids) if manifest_instance_ids else n_issues
    issues = load_issues(
        repo=repo_name,
        n=requested_issue_count,
        task_family=task_family,
        dataset_name=dataset_name,
        instance_ids=manifest_instance_ids,
    )
    if not issues:
        print(f"ERROR: No {repo_name} issues found. Aborting.")
        return
    issue_instance_ids = [issue.get("instance_id", "") for issue in issues]
    if manifest_instance_ids:
        missing_ids = [
            issue_id for issue_id in dict.fromkeys(manifest_instance_ids)
            if issue_id not in issue_instance_ids
        ]
        if missing_ids:
            print(
                f"  Warning: {len(missing_ids)} manifest issue IDs were not found "
                f"in {dataset_name}: {missing_ids}"
            )

    inferred_issue_set_id = issue_set_id or build_issue_set_id(repo_name, issue_instance_ids)
    inferred_suite_id = suite_id or build_suite_id(
        task_family=task_family,
        dataset_name=dataset_name,
        repo_name=repo_name,
        issue_set_id=inferred_issue_set_id,
        n_issues_requested=requested_issue_count,
        source_prefixes=source_prefixes,
        manager_max_turns=manager_max_turns,
        rag_max_turns=rag_max_turns,
        evaluation_track=evaluation_track,
        snapshot_commit=snapshot_commit,
        seed=seed,
    )

    # Step 2: Clone repository
    repo_short = repo_name.split("/")[-1]
    print(f"\n=== Step 2: Cloning {repo_name} ===")
    repo_dir = str(Path.cwd() / f"{repo_short}_repo")
    clone_repo(repo_name, repo_dir)
    repo_git = git.Repo(repo_dir)

    # Step 3: Group issues by base commit
    grouped_issues = build_issue_groups(
        issues,
        evaluation_track=evaluation_track,
        snapshot_commit=snapshot_commit,
    )
    print(f"\n=== Step 3: Grouping issues by base commit ({len(grouped_issues)} groups) ===")
    for commit, commit_issues in grouped_issues:
        label = commit[:12] if commit else "WORKTREE_HEAD"
        print(f"  {label}: {len(commit_issues)} issues")

    # Step 4: Build commit-scoped indices and run evaluation
    print("\n=== Step 4: Building commit contexts + evaluating issues ===")
    method_setup_totals = {
        method: {"build_time_s": 0.0, "embedding_tokens": 0}
        for method in ALL_METHODS
    }
    commit_context_cache: dict[str, dict] = {}
    commit_context_cache_stats = {"lookups": 0, "hits": 0, "misses": 0}
    detailed_results = []

    def get_or_build_commit_context(base_commit: str | None) -> dict:
        cache_key = base_commit or NO_BASE_COMMIT
        commit_context_cache_stats["lookups"] += 1
        if cache_key in commit_context_cache:
            commit_context_cache_stats["hits"] += 1
            return commit_context_cache[cache_key]
        commit_context_cache_stats["misses"] += 1

        if base_commit:
            print(f"\n  Checking out commit {base_commit[:12]}...")
            repo_git.git.checkout(base_commit, force=True)
        used_commit = repo_git.head.commit.hexsha
        print(f"  Building indices for {used_commit[:12]}...")
        graph = None
        graph_index = None
        rag_func = None
        rag_fixed = None
        bm25_index = None
        graph_file_paths = set()
        rag_function_file_paths = set()
        rag_fixed_file_paths = set()
        bm25_file_paths = set()
        graph_setup = {"build_time_s": 0.0, "embedding_tokens": 0}
        rag_func_setup = {"build_time_s": 0.0, "embedding_tokens": 0}
        rag_fixed_setup = {"build_time_s": 0.0, "embedding_tokens": 0}
        bm25_setup = {"build_time_s": 0.0, "embedding_tokens": 0}

        needs_graph_index = bool(enabled_method_set & {"gm_deterministic", "gm_progressive", "gm_baseline"})
        needs_graph_structure = needs_graph_index or bool(
            enabled_method_set & {"repomap_like", "agentless_like_localization"}
        )
        needs_rag_function = bool(
            enabled_method_set
            & {"rag_progressive", "rag_baseline", "raw_rag_function", "agentless_like_localization"}
        )
        needs_rag_fixed = "raw_rag_fixed" in enabled_method_set
        needs_bm25 = "bm25" in enabled_method_set

        if needs_graph_structure:
            t0 = time.time()
            builder = GraphBuilder(repo_dir, include_prefixes=source_prefixes)
            graph = builder.build()
            graph_build_time = time.time() - t0
            print(
                f"    Graph: {graph.number_of_nodes()} nodes, "
                f"{graph.number_of_edges()} edges ({graph_build_time:.1f}s)"
            )
            commit_graph_path = results_path / f"graph_{used_commit[:12]}.json"
            builder.save(str(commit_graph_path))
            canonical_graph_path = results_path / "graph.json"
            if not canonical_graph_path.exists():
                shutil.copy2(commit_graph_path, canonical_graph_path)

            graph_index_time = 0.0
            graph_embedding_tokens = 0
            if needs_graph_index:
                t0 = time.time()
                graph_index = GraphIndex(graph, client)
                graph_index.build()
                graph_index_time = time.time() - t0
                graph_embedding_tokens = int(graph_index.embedding_tokens_estimate)
            graph_setup = {
                "build_time_s": graph_build_time + graph_index_time,
                "embedding_tokens": graph_embedding_tokens,
            }
            graph_file_paths = {
                str(node_id)
                for node_id, node_data in graph.nodes(data=True)
                if node_data.get("type") == "file" and str(node_id).endswith(".py")
            }

        if needs_rag_function:
            t0 = time.time()
            rag_func = RAGIndex(
                repo_dir,
                client,
                chunk_strategy="function",
                include_prefixes=source_prefixes,
            )
            rag_func.build()
            rag_func_time = time.time() - t0
            rag_func_setup = {
                "build_time_s": rag_func_time,
                "embedding_tokens": int(rag_func.embedding_tokens_estimate),
            }
            rag_function_file_paths = {
                str(chunk.get("file", ""))
                for chunk in rag_func.chunks
                if chunk.get("file")
            }

        if needs_rag_fixed:
            t0 = time.time()
            rag_fixed = RAGIndex(
                repo_dir,
                client,
                chunk_strategy="fixed",
                include_prefixes=source_prefixes,
            )
            rag_fixed.build()
            rag_fixed_time = time.time() - t0
            rag_fixed_setup = {
                "build_time_s": rag_fixed_time,
                "embedding_tokens": int(rag_fixed.embedding_tokens_estimate),
            }
            rag_fixed_file_paths = {
                str(chunk.get("file", ""))
                for chunk in rag_fixed.chunks
                if chunk.get("file")
            }

        if needs_bm25:
            t0 = time.time()
            bm25_index = BM25Index(repo_dir, include_prefixes=source_prefixes)
            bm25_index.build()
            bm25_build_time = time.time() - t0
            bm25_setup = {
                "build_time_s": bm25_build_time,
                "embedding_tokens": 0,  # BM25 has no embedding cost
            }
            bm25_file_paths = set(bm25_index._file_paths)
            print(f"    BM25: {len(bm25_file_paths)} files indexed ({bm25_build_time:.1f}s)")

        setup_costs = {
            "gm_deterministic": graph_setup,
            "gm_progressive": graph_setup,
            "gm_baseline": graph_setup,
            "rag_progressive": rag_func_setup,
            "rag_baseline": rag_func_setup,
            "raw_rag_function": rag_func_setup,
            "raw_rag_fixed": rag_fixed_setup,
            "bm25": bm25_setup,
            "repomap_like": {
                "build_time_s": graph_setup["build_time_s"],
                "embedding_tokens": 0,
            },
            "agentless_like_localization": {
                "build_time_s": graph_setup["build_time_s"] + rag_func_setup["build_time_s"],
                "embedding_tokens": int(rag_func_setup.get("embedding_tokens", 0) or 0),
            },
        }
        for method_key, setup in setup_costs.items():
            method_setup_totals[method_key]["build_time_s"] += float(setup.get("build_time_s", 0.0))
            method_setup_totals[method_key]["embedding_tokens"] += int(setup.get("embedding_tokens", 0))

        context = {
            "used_commit": used_commit,
            "graph": graph,
            "graph_index": graph_index,
            "rag_function_index": rag_func,
            "rag_fixed_index": rag_fixed,
            "bm25_index": bm25_index,
            "graph_file_paths": graph_file_paths,
            "rag_function_file_paths": rag_function_file_paths,
            "rag_fixed_file_paths": rag_fixed_file_paths,
            "bm25_file_paths": bm25_file_paths,
            "setup_costs": setup_costs,
        }
        validate_commit_context(context, required_methods=enabled_methods)
        commit_context_cache[cache_key] = context
        return context

    issue_index = 0
    for group_idx, (base_commit, commit_issues) in enumerate(grouped_issues):
        print(
            f"\n=== Commit Group {group_idx + 1}/{len(grouped_issues)} "
            f"({(base_commit or 'WORKTREE_HEAD')[:12]}) ==="
        )
        context = get_or_build_commit_context(base_commit)

        deterministic_methods = []
        if "gm_deterministic" in enabled_method_set:
            gm_deterministic = DeterministicGraphRetriever(
                context["graph"],
                context["graph_index"],
                seed_k=deterministic_seed_k,
                depth=deterministic_depth,
                neighbor_cap=deterministic_neighbor_cap,
                min_return_files=deterministic_min_return_files,
                score_ratio_cutoff=deterministic_score_ratio_cutoff,
                min_score_cutoff=deterministic_min_score_cutoff,
                hub_degree_threshold=deterministic_hub_degree_threshold,
                hub_penalty_scale=deterministic_hub_penalty_scale,
                w_sem=deterministic_w_sem,
                w_graph=deterministic_w_graph,
                w_conf=deterministic_w_conf,
                w_hint=deterministic_w_hint,
                w_pen=deterministic_w_pen,
            )
            deterministic_methods.append(
                ("gm_deterministic", "GM (deterministic)", gm_deterministic)
            )
        if "repomap_like" in enabled_method_set:
            repomap_like = RepoMapLikeRetriever(
                graph=context["graph"],
                client=None,
                top_k_files=10,
                map_tokens=1000,
                use_llm_selector=False,
                refresh_mode="static_per_issue",
                edge_weights=None,
                enable_same_module_edge=False,
                personalization_enabled=True,
            )
            deterministic_methods.append(
                ("repomap_like", "RepoMap-like", repomap_like)
            )

        agentic_methods = []
        if "gm_progressive" in enabled_method_set:
            gm_progressive = ManagerAgent(
                context["graph"], context["graph_index"], client, retrieval_mode="progressive"
            )
            agentic_methods.append(
                ("gm_progressive", "GM (progressive)", gm_progressive, manager_max_turns)
            )
        if "gm_baseline" in enabled_method_set:
            gm_baseline = ManagerAgent(
                context["graph"], context["graph_index"], client, retrieval_mode="baseline"
            )
            agentic_methods.append(
                ("gm_baseline", "GM (baseline)", gm_baseline, manager_max_turns)
            )
        if "rag_progressive" in enabled_method_set:
            rag_progressive = RAGAgent(
                context["rag_function_index"], client, retrieval_mode="progressive"
            )
            agentic_methods.append(
                ("rag_progressive", "RAG (progressive)", rag_progressive, rag_max_turns)
            )
        if "rag_baseline" in enabled_method_set:
            rag_baseline = RAGAgent(
                context["rag_function_index"], client, retrieval_mode="baseline"
            )
            agentic_methods.append(
                ("rag_baseline", "RAG (baseline)", rag_baseline, rag_max_turns)
            )
        if "agentless_like_localization" in enabled_method_set:
            agentless_like = AgentlessLikeLocalizer(
                rag_index=context["rag_function_index"],
                graph=context["graph"],
                client=client,
                model=model_name,
                stage2_enabled=True,
                stage3_enabled=True,
                edit_location_samples=4,
                file_branch_top_n=3,
                embed_branch_top_k=20,
                merge_top_k=12,
                stage3_context_window_lines=10,
                stage3_max_tokens_per_file=1200,
                constrained_candidates_max=200,
                reject_out_of_candidate_paths=True,
            )
            agentic_methods.append(
                ("agentless_like_localization", "Agentless-like", agentless_like, manager_max_turns)
            )

        raw_methods = []
        if "raw_rag_function" in enabled_method_set:
            raw_rag_func_agent = RawRAG(context["rag_function_index"])
            raw_methods.append(("raw_rag_function", "Raw-RAG (func)", raw_rag_func_agent))
        if "raw_rag_fixed" in enabled_method_set:
            raw_rag_fixed_agent = RawRAG(context["rag_fixed_index"])
            raw_methods.append(("raw_rag_fixed", "Raw-RAG (fixed)", raw_rag_fixed_agent))
        if "bm25" in enabled_method_set:
            raw_methods.append(("bm25", "BM25", context["bm25_index"]))

        for issue in commit_issues:
            issue_index += 1
            print(f"\n--- Issue {issue_index}/{len(issues)}: {issue['instance_id']} ---")
            print(f"  Gold files: {issue['gold_files']}")
            issue_query = prepare_issue_text(
                issue.get("problem_statement", ""),
                redact_paths=redact_paths_in_issue_text,
            )

            issue_results = {
                "instance_id": issue["instance_id"],
                "gold_files": issue["gold_files"],
                "base_commit": issue.get("base_commit"),
                "used_commit": context["used_commit"],
                "track_name": evaluation_track,
                "methods": {},
            }

            for method_key, method_label, agent in deterministic_methods:
                print(f"  Running {method_label}...")
                setup_tokens = int(
                    context["setup_costs"].get(method_key, {}).get("embedding_tokens", 0)
                )
                valid_files = context["graph_file_paths"]
                try:
                    files, tokens = run_with_retries(lambda: agent.find_relevant_files(issue_query))
                    normalized_files = normalize_file_paths(files)
                    canonical_files = canonicalize_file_paths(normalized_files, valid_files)
                    metrics = compute_metrics(canonical_files, issue["gold_files"])
                    norm_tokens = normalize_token_usage(tokens)
                    payload = {
                        "predicted_files_raw": files,
                        "predicted_files_normalized": normalized_files,
                        "predicted_files": canonical_files,
                        "tokens": norm_tokens,
                        "metrics": metrics,
                        "cost_tokens": build_cost_components(norm_tokens, setup_tokens),
                    }
                    trace = getattr(agent, "last_trace", None)
                    if isinstance(trace, dict):
                        payload["retrieval_trace"] = trace
                    issue_results["methods"][method_key] = payload
                    print(f"    Files: {canonical_files}")
                    print(
                        f"    P={metrics['precision']:.2f} "
                        f"R={metrics['recall']:.2f} F1={metrics['f1']:.2f} | "
                        f"Q-embed: {norm_tokens['query_embedding_tokens']}"
                    )
                except Exception as e:
                    print(f"    ERROR: {e}")
                    issue_results["methods"][method_key] = build_error_result(
                        e, setup_embedding_tokens=setup_tokens
                    )

            for method_key, method_label, agent, max_turns in agentic_methods:
                print(f"  Running {method_label}...")
                setup_tokens = int(
                    context["setup_costs"].get(method_key, {}).get("embedding_tokens", 0)
                )
                valid_files = (
                    context["graph_file_paths"]
                    if (method_key.startswith("gm_") or method_key == "agentless_like_localization")
                    else context["rag_function_file_paths"]
                )
                try:
                    files, tokens = run_with_retries(
                        lambda: agent.find_relevant_files(
                            issue_query,
                            max_turns=max_turns,
                        )
                    )
                    normalized_files = normalize_file_paths(files)
                    canonical_files = canonicalize_file_paths(normalized_files, valid_files)
                    metrics = compute_metrics(canonical_files, issue["gold_files"])
                    norm_tokens = normalize_token_usage(tokens)
                    issue_results["methods"][method_key] = {
                        "predicted_files_raw": files,
                        "predicted_files_normalized": normalized_files,
                        "predicted_files": canonical_files,
                        "tokens": norm_tokens,
                        "metrics": metrics,
                        "cost_tokens": build_cost_components(norm_tokens, setup_tokens),
                    }
                    print(f"    Files: {canonical_files}")
                    print(
                        f"    P={metrics['precision']:.2f} "
                        f"R={metrics['recall']:.2f} F1={metrics['f1']:.2f} | "
                        f"LLM tokens: {norm_tokens['total_tokens']} | "
                        f"Q-embed: {norm_tokens['query_embedding_tokens']}"
                    )
                except Exception as e:
                    print(f"    ERROR: {e}")
                    issue_results["methods"][method_key] = build_error_result(
                        e, setup_embedding_tokens=setup_tokens
                    )

            for method_key, method_label, agent in raw_methods:
                print(f"  Running {method_label}...")
                setup_tokens = int(
                    context["setup_costs"].get(method_key, {}).get("embedding_tokens", 0)
                )
                if method_key == "raw_rag_fixed":
                    valid_files = context["rag_fixed_file_paths"]
                elif method_key == "bm25":
                    valid_files = context["bm25_file_paths"]
                else:
                    valid_files = context["rag_function_file_paths"]
                try:
                    files, tokens = agent.find_relevant_files(issue_query)
                    normalized_files = normalize_file_paths(files)
                    canonical_files = canonicalize_file_paths(normalized_files, valid_files)
                    metrics = compute_metrics(canonical_files, issue["gold_files"])
                    norm_tokens = normalize_token_usage(tokens)
                    issue_results["methods"][method_key] = {
                        "predicted_files_raw": files,
                        "predicted_files_normalized": normalized_files,
                        "predicted_files": canonical_files,
                        "tokens": norm_tokens,
                        "metrics": metrics,
                        "cost_tokens": build_cost_components(norm_tokens, setup_tokens),
                    }
                    print(f"    Files: {canonical_files[:5]}{'...' if len(canonical_files) > 5 else ''}")
                    print(
                        f"    P={metrics['precision']:.2f} "
                        f"R={metrics['recall']:.2f} F1={metrics['f1']:.2f} | "
                        f"Q-embed: {norm_tokens['query_embedding_tokens']}"
                    )
                except Exception as e:
                    print(f"    ERROR: {e}")
                    issue_results["methods"][method_key] = build_error_result(
                        e, setup_embedding_tokens=setup_tokens
                    )

            detailed_results.append(issue_results)

    # Step 5: Aggregate and save results
    print("\n=== Step 5: Aggregating results ===")
    summary = aggregate_results(
        detailed_results,
        setup_costs=method_setup_totals,
        track_name=evaluation_track,
        cache_stats=commit_context_cache_stats,
    )
    summary["_meta"] = {
        "run_id": results_path.name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task_family": task_family,
        "dataset_name": dataset_name,
        "repo_name": repo_name,
        "issue_set_id": inferred_issue_set_id,
        "suite_id": inferred_suite_id,
        "n_issues_requested": requested_issue_count,
        "n_issues_evaluated": len(issues),
        "issue_instance_ids": issue_instance_ids,
        "manifest_instance_ids": list(manifest_instance_ids),
        "n_commit_groups": len(grouped_issues),
        "commit_group_base_commits": [
            (commit[:12] if commit else None) for commit, _ in grouped_issues
        ],
        "domain": domain,
        "evaluation_track": evaluation_track,
        "snapshot_commit": snapshot_commit,
        "seed": seed,
        "enabled_methods": list(enabled_methods),
        "deterministic_retrieval": {
            "seed_k": deterministic_seed_k,
            "depth": deterministic_depth,
            "neighbor_cap": deterministic_neighbor_cap,
            "min_return_files": deterministic_min_return_files,
            "score_ratio_cutoff": deterministic_score_ratio_cutoff,
            "min_score_cutoff": deterministic_min_score_cutoff,
            "hub_degree_threshold": deterministic_hub_degree_threshold,
            "hub_penalty_scale": deterministic_hub_penalty_scale,
            "w_sem": deterministic_w_sem,
            "w_graph": deterministic_w_graph,
            "w_conf": deterministic_w_conf,
            "w_hint": deterministic_w_hint,
            "w_pen": deterministic_w_pen,
        },
        "commit_context_cache_stats": commit_context_cache_stats,
        "source_prefixes": list(source_prefixes) if source_prefixes else [],
        "manager_max_turns": manager_max_turns,
        "rag_max_turns": rag_max_turns,
        "model": model_name,
        "repeat_count": repeat_count,
        "repeat_index": repeat_index,
        "notes": experiment_notes,
        "redact_paths_in_issue_text": redact_paths_in_issue_text,
    }

    # Save detailed results
    with open(results_path / "detailed_results.json", "w") as f:
        json.dump(detailed_results, f, indent=2)

    # Save summary
    with open(results_path / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Keep a copy of the latest run in a stable path for quick inspection.
    _copy_run_artifacts(
        run_path=results_path,
        base_results_path=base_results_path,
        create_run_subdir=create_run_subdir,
    )

    # Print results table
    print_results_table(summary)

    print(f"\nResults saved to {results_path}/")
    return summary


ALL_METHODS = [
    "gm_deterministic",
    "gm_progressive", "gm_baseline",
    "rag_progressive", "rag_baseline",
    "raw_rag_function", "raw_rag_fixed",
    "bm25",
    "repomap_like",
    "agentless_like_localization",
]

METHOD_LABELS = {
    "gm_deterministic": "GM (deterministic)",
    "gm_progressive": "GM (progressive)",
    "gm_baseline": "GM (baseline)",
    "rag_progressive": "RAG (progressive)",
    "rag_baseline": "RAG (baseline)",
    "raw_rag_function": "Raw-RAG (func)",
    "raw_rag_fixed": "Raw-RAG (fixed)",
    "bm25": "BM25",
    "repomap_like": "RepoMap-like",
    "agentless_like_localization": "Agentless-like",
}


def _validate_track_consistency(detailed_results: list[dict], track_name: str):
    observed_track_names = {
        str(item.get("track_name"))
        for item in detailed_results
        if item.get("track_name")
    }
    if not observed_track_names:
        return
    if observed_track_names != {track_name}:
        found = ", ".join(sorted(observed_track_names))
        raise ValueError(
            f"Mixed evaluation tracks in one aggregation call. expected={track_name}, found={found}"
        )


def _compute_pairwise_break_even(summary: dict) -> dict[str, float | None]:
    pairwise: dict[str, float | None] = {}
    for left in ALL_METHODS:
        for right in ALL_METHODS:
            if left == right:
                continue
            left_setup = float(summary.get(left, {}).get("setup_embedding_tokens", 0) or 0)
            right_setup = float(summary.get(right, {}).get("setup_embedding_tokens", 0) or 0)
            left_runtime = float(summary.get(left, {}).get("avg_runtime_tokens_per_issue", 0) or 0)
            right_runtime = float(summary.get(right, {}).get("avg_runtime_tokens_per_issue", 0) or 0)
            denom = left_runtime - right_runtime
            key = f"{left}__vs__{right}"
            if denom == 0:
                pairwise[key] = None
                continue
            n_break_even = (right_setup - left_setup) / denom
            pairwise[key] = round(n_break_even, 6) if n_break_even > 0 else None
    return pairwise


def _build_amortization_block(
    detailed_results: list[dict],
    summary: dict,
    *,
    track_name: str,
    cache_stats: dict | None,
) -> dict:
    n_issues = len(detailed_results)
    commit_keys = [
        result.get("used_commit")
        or result.get("base_commit")
        or NO_BASE_COMMIT
        for result in detailed_results
    ]
    unique_commits = len(set(commit_keys))
    commit_repeat_ratio = ((n_issues - unique_commits) / n_issues) if n_issues else 0.0

    # Track-level amortization is issue-level reuse, not commit-group cache probes.
    lookups = n_issues
    hits = max(n_issues - unique_commits, 0)
    cache_hit_rate = (hits / lookups) if lookups else 0.0

    observed_cache_lookups = int((cache_stats or {}).get("lookups", 0) or 0)
    observed_cache_hits = int((cache_stats or {}).get("hits", 0) or 0)
    observed_cache_hit_rate = (
        observed_cache_hits / observed_cache_lookups
        if observed_cache_lookups
        else 0.0
    )

    return {
        "track_name": track_name,
        "n_issues": n_issues,
        "n_unique_commits": unique_commits,
        "commit_repeat_ratio": commit_repeat_ratio,
        "cache_lookups": lookups,
        "cache_hits": hits,
        "cache_hit_rate": cache_hit_rate,
        "observed_cache_lookups": observed_cache_lookups,
        "observed_cache_hits": observed_cache_hits,
        "observed_cache_hit_rate": observed_cache_hit_rate,
        "pairwise_break_even_n": _compute_pairwise_break_even(summary),
    }


def aggregate_results(
    detailed_results: list[dict],
    setup_costs: dict,
    track_name: str = "strict_commit_fidelity",
    cache_stats: dict | None = None,
) -> dict:
    """Compute aggregate metrics across all issues for each method."""
    _validate_track_consistency(detailed_results, track_name)
    summary = {}
    n_total_issues = len(detailed_results)

    for method in ALL_METHODS:
        precisions = []
        recalls = []
        f1s = []
        total_prompt_tokens = 0
        total_candidate_tokens = 0
        total_tokens = 0
        total_query_embedding_tokens = 0
        n_errors = 0
        stop_reason_counts: dict[str, int] = {}

        for result in detailed_results:
            method_data = result["methods"].get(method, {})
            if not method_data:
                method_data = build_error_result(
                    "missing method result", setup_embedding_tokens=0
                )
            if "error" in method_data:
                n_errors += 1
            metrics = method_data.get("metrics", {}) or {}
            precisions.append(metrics.get("precision", 0))
            recalls.append(metrics.get("recall", 0))
            f1s.append(metrics.get("f1", 0))
            tokens = normalize_token_usage(method_data.get("tokens", {}))
            total_prompt_tokens += tokens.get("prompt_tokens", 0)
            total_candidate_tokens += tokens.get("candidate_tokens", 0)
            total_tokens += tokens.get("total_tokens", 0)
            total_query_embedding_tokens += tokens.get("query_embedding_tokens", 0)
            stop_reason = str(tokens.get("stop_reason", "")).strip()
            if stop_reason:
                stop_reason_counts[stop_reason] = stop_reason_counts.get(stop_reason, 0) + 1

        n = max(n_total_issues, 1)
        setup = setup_costs.get(method, {})
        setup_embedding_tokens = int(setup.get("embedding_tokens", 0) or 0)
        n_success = max(n_total_issues - n_errors, 0)
        runtime_tokens = total_tokens + total_query_embedding_tokens
        total_cost_tokens = runtime_tokens + setup_embedding_tokens
        avg_runtime_tokens = runtime_tokens / n
        mean_f1 = (sum(f1s) / n) if f1s else 0
        tokens_per_f1 = (avg_runtime_tokens / mean_f1) if mean_f1 > 0 else None

        summary[method] = {
            "n_issues": n_total_issues,
            "n_success": n_success,
            "n_errors": n_errors,
            "error_rate": (n_errors / n_total_issues) if n_total_issues else 0.0,
            "mean_precision": sum(precisions) / n if precisions else 0,
            "mean_recall": sum(recalls) / n if recalls else 0,
            "mean_f1": mean_f1,
            "total_prompt_tokens": total_prompt_tokens,
            "total_candidate_tokens": total_candidate_tokens,
            "total_llm_tokens": total_tokens,
            "avg_llm_tokens_per_issue": total_tokens / n,
            "total_query_embedding_tokens": total_query_embedding_tokens,
            "avg_query_embedding_tokens_per_issue": total_query_embedding_tokens / n,
            "total_runtime_tokens": runtime_tokens,
            "avg_runtime_tokens_per_issue": avg_runtime_tokens,
            "tokens_per_f1": tokens_per_f1,
            "setup_embedding_tokens": setup_embedding_tokens,
            "setup_time_s": setup.get("build_time_s", 0),
            "total_cost_tokens": total_cost_tokens,
            "avg_total_cost_tokens_per_issue": (
                setup_embedding_tokens + (total_tokens / n) + (total_query_embedding_tokens / n)
            ),
            "avg_total_cost_tokens_per_issue_unamortized_setup": (
                setup_embedding_tokens + avg_runtime_tokens
            ),
            "avg_total_cost_tokens_per_issue_amortized_setup": total_cost_tokens / n,
            "stop_reason_counts": stop_reason_counts,
        }

    baseline_tokens_per_f1 = summary.get("rag_baseline", {}).get("tokens_per_f1")
    for method in ALL_METHODS:
        method_tpf1 = summary.get(method, {}).get("tokens_per_f1")
        if baseline_tokens_per_f1 is None or method_tpf1 is None:
            summary[method]["token_per_f1_delta_vs_rag_baseline"] = None
        else:
            summary[method]["token_per_f1_delta_vs_rag_baseline"] = (
                float(method_tpf1) - float(baseline_tokens_per_f1)
            )

    summary["_amortization"] = _build_amortization_block(
        detailed_results=detailed_results,
        summary=summary,
        track_name=track_name,
        cache_stats=cache_stats,
    )
    return summary


def print_results_table(summary: dict):
    """Print a formatted comparison table."""
    print("\n" + "=" * 120)
    print("RESULTS SUMMARY")
    print("=" * 120)
    header = (
        f"{'Method':<22} {'P':>6} {'R':>6} {'F1':>6} "
        f"{'Err':>5} {'LLM Tok':>10} {'QEmb Tok':>10} {'Setup Tok':>10}"
    )
    print(header)
    print("-" * 120)

    for method in ALL_METHODS:
        s = summary.get(method, {})
        print(
            f"{METHOD_LABELS.get(method, method):<22} "
            f"{s.get('mean_precision', 0):>6.3f} "
            f"{s.get('mean_recall', 0):>6.3f} "
            f"{s.get('mean_f1', 0):>6.3f} "
            f"{s.get('n_errors', 0):>5} "
            f"{s.get('total_llm_tokens', 0):>10,} "
            f"{s.get('total_query_embedding_tokens', 0):>10,} "
            f"{s.get('setup_embedding_tokens', 0):>10,}"
        )

    print("=" * 120)
    print("\nKey: P=Precision, R=Recall, F1=F1 Score, LLM Tok=Total LLM tokens across all issues")
    print("     QEmb Tok=Total query embedding tokens, Setup Tok=One-time setup embedding tokens")
