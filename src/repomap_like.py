"""RepoMap-like file ranking baseline with explicit file-graph semantics."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import networkx as nx

DEFAULT_EDGE_WEIGHTS = {
    "import": 1.0,
    "symbol_ref": 1.0,
    "test_ref": 0.5,
    "same_module": 0.2,
}


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", (text or "").lower())
        if token
    }


def _estimate_tokens(text: str) -> int:
    return max(len(text) // 4, 0)


def _safe_response_text(response) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                return part_text
    return ""


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_test_file(path: str) -> bool:
    norm = str(path).replace("\\", "/").lower()
    parts = norm.split("/")
    if "tests" in parts or "testing" in parts:
        return True
    name = Path(norm).name
    return name.startswith("test_") or name.endswith("_test.py")


class RepoMapLikeRetriever:
    """File-graph PageRank retriever with optional constrained selector call."""

    def __init__(
        self,
        *,
        graph: nx.DiGraph,
        client=None,
        model: str = "gemini-3-flash-preview",
        top_k_files: int = 10,
        map_tokens: int = 1000,
        use_llm_selector: bool = False,
        refresh_mode: str = "static_per_issue",
        edge_weights: dict | None = None,
        enable_same_module_edge: bool = False,
        personalization_enabled: bool = True,
    ):
        self.graph = graph
        self.client = client
        self.model = model
        self.top_k_files = max(int(top_k_files), 1)
        self.map_tokens = max(int(map_tokens), 128)
        self.use_llm_selector = bool(use_llm_selector)
        self.refresh_mode = str(refresh_mode or "static_per_issue")
        self.enable_same_module_edge = bool(enable_same_module_edge)
        self.personalization_enabled = bool(personalization_enabled)

        merged_weights = dict(DEFAULT_EDGE_WEIGHTS)
        for key, value in (edge_weights or {}).items():
            if key in merged_weights:
                merged_weights[key] = max(float(value), 0.0)
        self.edge_weights = merged_weights

    def find_relevant_files(self, issue_text: str) -> tuple[list[str], dict]:
        file_graph, edge_type_counts = self._build_file_graph()
        if file_graph.number_of_nodes() == 0:
            return [], self._build_tokens(
                map_tokens_used=0,
                edge_type_counts=edge_type_counts,
                effective_edge_weights={},
                invalid_selection_count=0,
                selector_usage={},
                stop_reason="empty_file_graph",
            )

        personalization = None
        if self.personalization_enabled:
            personalization = self._build_personalization(file_graph, issue_text)
        scores = self._rank_files(file_graph=file_graph, personalization=personalization)
        ranked = sorted(
            scores.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )

        map_text, map_tokens_used = self._build_map_snapshot(ranked)
        candidate_files = [path for path, _ in ranked[: max(self.top_k_files * 3, self.top_k_files)]]
        selected_files = candidate_files[: self.top_k_files]

        selector_usage = {}
        invalid_selection_count = 0
        if self.use_llm_selector and self.client is not None and candidate_files:
            selected_files, selector_usage, invalid_selection_count = self._llm_select_files(
                issue_text=issue_text,
                map_text=map_text,
                candidate_files=candidate_files,
            )

        return selected_files, self._build_tokens(
            map_tokens_used=map_tokens_used,
            edge_type_counts=edge_type_counts,
            effective_edge_weights=self.edge_weights,
            invalid_selection_count=invalid_selection_count,
            selector_usage=selector_usage,
            stop_reason="rank_only" if not selector_usage else "llm_selector",
        )

    def _rank_files(self, *, file_graph: nx.DiGraph, personalization: dict[str, float] | None) -> dict[str, float]:
        try:
            return nx.pagerank(
                file_graph,
                alpha=0.85,
                personalization=personalization,
                weight="weight",
            )
        except ModuleNotFoundError:
            return self._power_iteration_pagerank(
                file_graph=file_graph,
                personalization=personalization,
            )

    def _power_iteration_pagerank(
        self,
        *,
        file_graph: nx.DiGraph,
        personalization: dict[str, float] | None,
        alpha: float = 0.85,
        max_iter: int = 100,
        tol: float = 1.0e-6,
    ) -> dict[str, float]:
        nodes = list(file_graph.nodes())
        n_nodes = len(nodes)
        if n_nodes == 0:
            return {}
        if personalization:
            total = sum(float(personalization.get(node, 0.0) or 0.0) for node in nodes)
            if total <= 0:
                p = {node: 1.0 / n_nodes for node in nodes}
            else:
                p = {
                    node: float(personalization.get(node, 0.0) or 0.0) / total
                    for node in nodes
                }
        else:
            p = {node: 1.0 / n_nodes for node in nodes}

        rank = {node: 1.0 / n_nodes for node in nodes}
        for _ in range(max_iter):
            new_rank = {node: (1.0 - alpha) * p[node] for node in nodes}
            for src in nodes:
                out_edges = list(file_graph.out_edges(src, data=True))
                if not out_edges:
                    for dst in nodes:
                        new_rank[dst] += alpha * rank[src] * p[dst]
                    continue
                for _, dst, attrs in out_edges:
                    weight = float(attrs.get("weight", 0.0) or 0.0)
                    new_rank[dst] += alpha * rank[src] * weight
            error = sum(abs(new_rank[node] - rank[node]) for node in nodes)
            rank = new_rank
            if error < (tol * n_nodes):
                break
        total_rank = sum(rank.values()) or 1.0
        return {node: value / total_rank for node, value in rank.items()}

    def _build_file_graph(self) -> tuple[nx.DiGraph, dict[str, int]]:
        file_graph = nx.DiGraph()
        edge_type_counts = {
            "import": 0,
            "symbol_ref": 0,
            "test_ref": 0,
            "same_module": 0,
        }

        file_nodes = {
            str(node_id)
            for node_id, node_data in self.graph.nodes(data=True)
            if node_data.get("type") == "file" and str(node_id).endswith(".py")
        }
        for file_path in sorted(file_nodes):
            file_graph.add_node(file_path)

        for src, dst, attrs in self.graph.edges(data=True):
            src_file = self._node_file(src)
            dst_file = self._node_file(dst)
            if not src_file or not dst_file or src_file == dst_file:
                continue
            if src_file not in file_nodes or dst_file not in file_nodes:
                continue

            edge_kind = self._classify_edge(
                src_file=src_file,
                dst_file=dst_file,
                edge_type=str(attrs.get("type", "") or ""),
            )
            if edge_kind is None:
                continue
            edge_type_counts[edge_kind] += 1
            self._add_weighted_edge(
                file_graph=file_graph,
                src=src_file,
                dst=dst_file,
                weight=self.edge_weights.get(edge_kind, 0.0),
            )

        if self.enable_same_module_edge:
            by_parent: dict[str, list[str]] = defaultdict(list)
            for file_path in file_nodes:
                by_parent[str(Path(file_path).parent)].append(file_path)
            for _, siblings in by_parent.items():
                siblings = sorted(siblings)
                if len(siblings) < 2:
                    continue
                for idx, src in enumerate(siblings):
                    for dst in siblings[idx + 1 :]:
                        self._add_weighted_edge(
                            file_graph=file_graph,
                            src=src,
                            dst=dst,
                            weight=self.edge_weights["same_module"],
                        )
                        self._add_weighted_edge(
                            file_graph=file_graph,
                            src=dst,
                            dst=src,
                            weight=self.edge_weights["same_module"],
                        )
                        edge_type_counts["same_module"] += 2

        self._row_normalize_outgoing_weights(file_graph)
        return file_graph, edge_type_counts

    def _node_file(self, node_id: str) -> str | None:
        data = self.graph.nodes.get(node_id, {}) if node_id in self.graph else {}
        if data.get("type") == "file":
            candidate = str(node_id)
        else:
            candidate = str(data.get("file", "") or "")
        if not candidate.endswith(".py"):
            return None
        return candidate

    def _classify_edge(self, *, src_file: str, dst_file: str, edge_type: str) -> str | None:
        if edge_type == "IMPORTS":
            return "import"
        if _is_test_file(src_file) and not _is_test_file(dst_file):
            return "test_ref"
        if edge_type in {"CALLS", "INHERITS", "CONTAINS", "DEFINES"}:
            return "symbol_ref"
        return None

    def _add_weighted_edge(self, *, file_graph: nx.DiGraph, src: str, dst: str, weight: float) -> None:
        if weight <= 0:
            return
        current = 0.0
        if file_graph.has_edge(src, dst):
            current = float(file_graph[src][dst].get("weight", 0.0) or 0.0)
        file_graph.add_edge(src, dst, weight=(current + weight))

    def _row_normalize_outgoing_weights(self, file_graph: nx.DiGraph) -> None:
        for src in list(file_graph.nodes()):
            out_edges = list(file_graph.out_edges(src, data=True))
            if not out_edges:
                continue
            total = sum(float(attrs.get("weight", 0.0) or 0.0) for _, _, attrs in out_edges)
            if total <= 0:
                continue
            for _, dst, attrs in out_edges:
                attrs["weight"] = float(attrs.get("weight", 0.0) or 0.0) / total
                file_graph[src][dst]["weight"] = attrs["weight"]

    def _build_personalization(self, file_graph: nx.DiGraph, issue_text: str) -> dict[str, float]:
        query = (issue_text or "").lower()
        query_tokens = _tokenize(query)
        raw_scores: dict[str, float] = {}
        for file_path in file_graph.nodes():
            path_tokens = _tokenize(str(file_path).replace("/", " ").replace(".", " "))
            overlap = len(query_tokens & path_tokens)
            mention_bonus = 3.0 if str(file_path).lower() in query else 0.0
            raw_scores[str(file_path)] = float(overlap) + mention_bonus

        positive = {path: score for path, score in raw_scores.items() if score > 0}
        if not positive:
            uniform = 1.0 / max(len(raw_scores), 1)
            return {path: uniform for path in raw_scores}

        total = sum(positive.values())
        return {path: score / total for path, score in positive.items()}

    def _build_map_snapshot(self, ranked_files: list[tuple[str, float]]) -> tuple[str, int]:
        lines = []
        used_tokens = 0
        for rank, (file_path, score) in enumerate(ranked_files, start=1):
            symbols = self._top_symbols_for_file(file_path=file_path, limit=6)
            symbol_text = ", ".join(symbols) if symbols else "no_symbols"
            line = f"{rank:02d}. {file_path} [{score:.4f}] :: {symbol_text}"
            line_tokens = _estimate_tokens(line) + 1
            if used_tokens + line_tokens > self.map_tokens:
                break
            lines.append(line)
            used_tokens += line_tokens
        map_text = "\n".join(lines)
        return map_text, used_tokens

    def _top_symbols_for_file(self, *, file_path: str, limit: int = 6) -> list[str]:
        symbols: list[str] = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") not in {"function", "class"}:
                continue
            if str(data.get("file", "") or "") != file_path:
                continue
            symbol = str(data.get("name", "") or "")
            if symbol:
                symbols.append(symbol)
            else:
                symbols.append(str(node_id).split("::")[-1])
        symbols = sorted(set(symbols))
        return symbols[: max(limit, 1)]

    def _llm_select_files(
        self,
        *,
        issue_text: str,
        map_text: str,
        candidate_files: list[str],
    ) -> tuple[list[str], dict, int]:
        candidate_block = "\n".join(f"- {path}" for path in candidate_files)
        prompt = (
            "Select the most likely files to modify.\n"
            "You MUST choose only from the candidate file list below.\n"
            "Return strict JSON: {\"files\": [\"...\"]}\n\n"
            f"Issue:\n{issue_text}\n\n"
            f"Repo map snapshot:\n{map_text}\n\n"
            f"Candidate files:\n{candidate_block}\n"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        usage = self._usage_from_response(response)
        parsed = _extract_json_object(_safe_response_text(response)) or {}
        selected = parsed.get("files") if isinstance(parsed, dict) else []
        if not isinstance(selected, list):
            selected = []

        candidate_set = set(candidate_files)
        chosen = []
        invalid = 0
        for item in selected:
            path = str(item or "").strip()
            if not path:
                continue
            if path not in candidate_set:
                invalid += 1
                continue
            if path not in chosen:
                chosen.append(path)

        if not chosen:
            chosen = candidate_files[: self.top_k_files]
        return chosen[: self.top_k_files], usage, invalid

    def _usage_from_response(self, response) -> dict:
        usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
        }
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return usage
        usage["prompt_tokens"] = int(getattr(meta, "prompt_token_count", 0) or 0)
        usage["candidate_tokens"] = int(getattr(meta, "candidates_token_count", 0) or 0)
        usage["total_tokens"] = int(getattr(meta, "total_token_count", 0) or 0)
        return usage

    def _build_tokens(
        self,
        *,
        map_tokens_used: int,
        edge_type_counts: dict,
        effective_edge_weights: dict,
        invalid_selection_count: int,
        selector_usage: dict,
        stop_reason: str,
    ) -> dict:
        prompt_tokens = int(selector_usage.get("prompt_tokens", 0) or 0)
        candidate_tokens = int(selector_usage.get("candidate_tokens", 0) or 0)
        total_tokens = int(selector_usage.get("total_tokens", 0) or 0)
        selector_calls = 1 if selector_usage else 0
        invalid_rate = (
            float(invalid_selection_count) / float(max(invalid_selection_count + self.top_k_files, 1))
        )
        return {
            "prompt_tokens": prompt_tokens,
            "candidate_tokens": candidate_tokens,
            "total_tokens": total_tokens,
            "query_embedding_tokens": 0,
            "tool_calls": selector_calls,
            "stop_reason": stop_reason,
            "repomap_meta": {
                "edge_type_counts": dict(edge_type_counts),
                "edge_weights": dict(effective_edge_weights),
                "map_tokens_used": int(map_tokens_used),
                "refresh_mode": self.refresh_mode,
                "invalid_path_selection_rate": invalid_rate,
                "invalid_path_selection_count": int(invalid_selection_count),
                "personalization_enabled": self.personalization_enabled,
            },
        }
