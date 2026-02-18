"""Deterministic graph-first retriever with explicit evidence scoring."""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import networkx as nx

from .path_resolution import canonicalize_file_path


DEFAULT_ALLOWED_EDGE_TYPES = (
    "CALLS",
    "IMPORTS",
    "INHERITS",
    "DEFINES",
    "CONTAINS",
)

DEFAULT_WEIGHTS = {
    "w_sem": 0.35,
    "w_graph": 0.30,
    "w_conf": 0.20,
    "w_hint": 0.10,
    "w_pen": 0.05,
}

CONFIDENCE_WEIGHTS = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
}


def _normalize_seed_scores(seed_results: list[dict[str, Any]]) -> list[float]:
    scores = [float(item.get("score", 0.0) or 0.0) for item in seed_results]
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi - lo <= 1e-12:
        return [1.0 for _ in scores]
    return [(value - lo) / (hi - lo) for value in scores]


def _tokenize_text(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", (text or "").lower())
        if token
    }


def _tokenize_path(path: str) -> set[str]:
    parts = []
    for part in str(path or "").replace("\\", "/").split("/"):
        if not part:
            continue
        stem = part.rsplit(".", 1)[0]
        parts.extend(re.split(r"[^a-zA-Z0-9]+", stem))
    return {token.lower() for token in parts if token}


def _label_for_confidence(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.4:
        return "medium"
    return "low"


def _path_confidence(edge_types: tuple[str, ...], confidences: tuple[float, ...]) -> float:
    signal_conf = [
        confidence
        for edge_type, confidence in zip(edge_types, confidences)
        if edge_type == "CALLS"
    ]
    if signal_conf:
        return float(sum(signal_conf) / len(signal_conf))
    if confidences:
        return float(sum(confidences) / len(confidences))
    return 1.0


@dataclass
class _PathRecord:
    seed_node: str
    node_id: str
    file: str
    depth: int
    edge_types: tuple[str, ...]
    confidences: tuple[float, ...]
    confidence_label: str


def score_file_evidence(
    *,
    s_sem: float,
    s_graph: float,
    s_conf: float,
    s_hint: float,
    s_pen: float,
    w_sem: float,
    w_graph: float,
    w_conf: float,
    w_hint: float,
    w_pen: float,
) -> float:
    """Compute final deterministic score from normalized evidence components."""
    return (
        (w_sem * s_sem)
        + (w_graph * s_graph)
        + (w_conf * s_conf)
        + (w_hint * s_hint)
        - (w_pen * s_pen)
    )


class DeterministicGraphRetriever:
    """Deterministic graph-first retrieval with bounded bidirectional expansion."""

    def __init__(
        self,
        graph: nx.DiGraph,
        graph_index,
        *,
        seed_k: int = 8,
        depth: int = 2,
        neighbor_cap: int = 12,
        max_return_files: int = 6,
        min_return_files: int = 1,
        score_ratio_cutoff: float = 0.70,
        min_score_cutoff: float = 0.0,
        hub_degree_threshold: int = 20,
        hub_penalty_scale: float = 0.35,
        allowed_edge_types: tuple[str, ...] = DEFAULT_ALLOWED_EDGE_TYPES,
        w_sem: float = DEFAULT_WEIGHTS["w_sem"],
        w_graph: float = DEFAULT_WEIGHTS["w_graph"],
        w_conf: float = DEFAULT_WEIGHTS["w_conf"],
        w_hint: float = DEFAULT_WEIGHTS["w_hint"],
        w_pen: float = DEFAULT_WEIGHTS["w_pen"],
    ):
        self.graph = graph
        self.index = graph_index
        self.seed_k = max(int(seed_k), 1)
        self.depth = max(int(depth), 0)
        self.neighbor_cap = max(int(neighbor_cap), 1)
        self.max_return_files = max(int(max_return_files), 1)
        self.min_return_files = max(int(min_return_files), 1)
        self.score_ratio_cutoff = max(float(score_ratio_cutoff), 0.0)
        self.min_score_cutoff = max(float(min_score_cutoff), 0.0)
        self.hub_degree_threshold = max(int(hub_degree_threshold), 1)
        self.hub_penalty_scale = max(float(hub_penalty_scale), 0.0)
        self.allowed_edge_types = tuple(allowed_edge_types)
        self.weights = {
            "w_sem": float(w_sem),
            "w_graph": float(w_graph),
            "w_conf": float(w_conf),
            "w_hint": float(w_hint),
            "w_pen": float(w_pen),
        }
        self.valid_files = {
            str(node_id)
            for node_id, node_data in self.graph.nodes(data=True)
            if node_data.get("type") == "file" and str(node_id).endswith(".py")
        }
        file_degree_accumulator: dict[str, int] = defaultdict(int)
        for file_path in self.valid_files:
            file_degree_accumulator[file_path] += int(self.graph.degree(file_path))
        for node_id, node_data in self.graph.nodes(data=True):
            file_path = str(node_data.get("file", "") or "")
            if file_path in self.valid_files:
                file_degree_accumulator[file_path] += int(self.graph.degree(node_id))
        self.file_degrees = dict(file_degree_accumulator)
        self.last_trace: dict[str, Any] = {}

    def _canonical_file_for_node(self, node_id: str) -> str | None:
        data = self.graph.nodes.get(node_id, {})
        if data.get("type") == "file":
            candidate = str(node_id)
        else:
            candidate = str(data.get("file", "") or "")
        if not candidate:
            return None
        return canonicalize_file_path(candidate, self.valid_files)

    def _neighbors_for(self, node_id: str) -> list[tuple[str, str, float]]:
        neighbors: list[tuple[str, str, float]] = []

        for _, dst, attrs in self.graph.out_edges(node_id, data=True):
            edge_type = str(attrs.get("type", "") or "")
            if edge_type not in self.allowed_edge_types:
                continue
            conf_label = str(attrs.get("confidence", "medium") or "medium").lower()
            confidence = CONFIDENCE_WEIGHTS.get(conf_label, CONFIDENCE_WEIGHTS["medium"])
            neighbors.append((str(dst), edge_type, confidence))

        for src, _, attrs in self.graph.in_edges(node_id, data=True):
            edge_type = str(attrs.get("type", "") or "")
            if edge_type not in self.allowed_edge_types:
                continue
            conf_label = str(attrs.get("confidence", "medium") or "medium").lower()
            confidence = CONFIDENCE_WEIGHTS.get(conf_label, CONFIDENCE_WEIGHTS["medium"])
            neighbors.append((str(src), edge_type, confidence))

        neighbors.sort(key=lambda item: (item[0], item[1], item[2]))
        return neighbors[: self.neighbor_cap]

    def _build_paths(
        self,
        *,
        seed_node: str,
        seed_strength: float,
    ) -> list[_PathRecord]:
        paths: list[_PathRecord] = []
        queue: deque[tuple[str, int, tuple[str, ...], tuple[float, ...]]] = deque()
        queue.append((seed_node, 0, tuple(), tuple()))
        best_depth: dict[str, int] = {seed_node: 0}

        while queue:
            current, depth, edge_types, confidences = queue.popleft()
            current_file = self._canonical_file_for_node(current)
            if current_file is not None:
                confidence_value = _path_confidence(edge_types, confidences)
                paths.append(
                    _PathRecord(
                        seed_node=seed_node,
                        node_id=current,
                        file=current_file,
                        depth=depth,
                        edge_types=edge_types,
                        confidences=confidences,
                        confidence_label=_label_for_confidence(confidence_value),
                    )
                )

            if depth >= self.depth:
                continue

            for neighbor, edge_type, confidence in self._neighbors_for(current):
                next_depth = depth + 1
                prev_depth = best_depth.get(neighbor)
                if prev_depth is not None and prev_depth <= next_depth:
                    continue
                best_depth[neighbor] = next_depth
                queue.append(
                    (
                        neighbor,
                        next_depth,
                        edge_types + (edge_type,),
                        confidences + (confidence,),
                    )
                )

        # Ensure stable path ordering regardless of traversal queue behavior.
        paths.sort(
            key=lambda item: (
                item.file,
                item.depth,
                item.node_id,
                item.edge_types,
                item.confidences,
            )
        )

        # Attach seed semantics as an attribute without mutating dataclass fields.
        for record in paths:
            setattr(record, "seed_strength", seed_strength)
        return paths

    def _score_paths(
        self,
        paths: list[_PathRecord],
        issue_text: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        issue_tokens = _tokenize_text(issue_text)
        evidence: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "semantic_values": [],
                "path_ids": set(),
                "path_depths": [],
                "path_confidences": [],
                "high_conf_paths": 0,
                "medium_conf_paths": 0,
                "low_conf_paths": 0,
                "edge_types": set(),
            }
        )

        trace_paths: list[dict[str, Any]] = []

        for path in paths:
            avg_conf = _path_confidence(path.edge_types, path.confidences)
            path_id = (path.seed_node, path.node_id, path.depth, path.edge_types)
            bucket = evidence[path.file]
            if path_id not in bucket["path_ids"]:
                bucket["path_ids"].add(path_id)
                bucket["path_depths"].append(path.depth)
                bucket["path_confidences"].append(avg_conf)
                bucket["edge_types"].update(path.edge_types)
                if path.confidence_label == "high":
                    bucket["high_conf_paths"] += 1
                elif path.confidence_label == "medium":
                    bucket["medium_conf_paths"] += 1
                else:
                    bucket["low_conf_paths"] += 1

            seed_strength = float(getattr(path, "seed_strength", 0.0))
            bucket["semantic_values"].append(seed_strength / (path.depth + 1))

            trace_paths.append(
                {
                    "seed_node": path.seed_node,
                    "node_id": path.node_id,
                    "file": path.file,
                    "depth": path.depth,
                    "edge_types": list(path.edge_types),
                    "avg_confidence": avg_conf,
                    "confidence_label": path.confidence_label,
                }
            )

        graph_raw: dict[str, float] = {}
        for file_path, info in evidence.items():
            unique_paths = max(len(info["path_ids"]), 1)
            diversity_bonus = min(len(info["edge_types"]), 3) / 3.0
            graph_raw[file_path] = math.log1p(unique_paths) + (0.25 * diversity_bonus)

        max_graph_raw = max(graph_raw.values()) if graph_raw else 1.0
        ranked_rows: list[dict[str, Any]] = []

        for file_path, info in evidence.items():
            total_paths = max(len(info["path_ids"]), 1)
            high = int(info["high_conf_paths"])
            medium = int(info["medium_conf_paths"])
            low = int(info["low_conf_paths"])

            s_sem = float(max(info["semantic_values"])) if info["semantic_values"] else 0.0
            s_graph = float(graph_raw.get(file_path, 0.0) / max_graph_raw) if max_graph_raw > 0 else 0.0
            s_conf = (
                float(sum(info["path_confidences"]) / len(info["path_confidences"]))
                if info["path_confidences"]
                else 0.0
            )

            path_tokens = _tokenize_path(file_path)
            if path_tokens and issue_tokens:
                s_hint = len(path_tokens & issue_tokens) / len(path_tokens)
            else:
                s_hint = 0.0

            if low > 0 and (high + medium) == 0:
                base_pen = 1.0
            else:
                low_ratio = low / total_paths
                base_pen = max(0.0, low_ratio - 0.7)

            file_degree = float(self.file_degrees.get(file_path, 0))
            if file_degree > self.hub_degree_threshold:
                hub_ratio = min(
                    (file_degree - self.hub_degree_threshold) / self.hub_degree_threshold,
                    1.0,
                )
            else:
                hub_ratio = 0.0
            s_pen = min(1.0, base_pen + (self.hub_penalty_scale * hub_ratio))

            score = score_file_evidence(
                s_sem=s_sem,
                s_graph=s_graph,
                s_conf=s_conf,
                s_hint=s_hint,
                s_pen=s_pen,
                **self.weights,
            )
            avg_depth = (
                float(sum(info["path_depths"]) / len(info["path_depths"]))
                if info["path_depths"]
                else 0.0
            )

            ranked_rows.append(
                {
                    "file": file_path,
                    "score": score,
                    "high_conf_paths": high,
                    "avg_path_depth": avg_depth,
                    "components": {
                        "s_sem": s_sem,
                        "s_graph": s_graph,
                        "s_conf": s_conf,
                        "s_hint": s_hint,
                        "s_pen": s_pen,
                        "s_pen_low_conf_only": base_pen,
                        "s_pen_hub": self.hub_penalty_scale * hub_ratio,
                    },
                    "hub_degree": file_degree,
                }
            )

        ranked_rows.sort(
            key=lambda row: (
                -float(row["score"]),
                -int(row["high_conf_paths"]),
                float(row["avg_path_depth"]),
                str(row["file"]),
            )
        )

        return ranked_rows, trace_paths

    def _select_top_rows(
        self,
        ranked_rows: list[dict[str, Any]],
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], float]:
        if not ranked_rows:
            return [], 0.0
        limit = max(int(limit), 1)
        top_score = float(ranked_rows[0].get("score", 0.0) or 0.0)
        adaptive_cutoff = max(
            self.min_score_cutoff,
            top_score * self.score_ratio_cutoff,
        )
        selected: list[dict[str, Any]] = []
        for idx, row in enumerate(ranked_rows):
            if len(selected) >= limit:
                break
            if idx < self.min_return_files:
                selected.append(row)
                continue
            score = float(row.get("score", 0.0) or 0.0)
            if score < adaptive_cutoff:
                break
            selected.append(row)
        if not selected:
            selected.append(ranked_rows[0])
        return selected, adaptive_cutoff

    def find_relevant_files(self, issue_text: str, top_k: int | None = None) -> tuple[list[str], dict[str, Any]]:
        """Run one semantic seed retrieval call and deterministic graph expansion."""
        search_outcome = self.index.search(issue_text, top_k=self.seed_k)
        seed_results = list(search_outcome.get("results", []) or [])[: self.seed_k]
        seed_scores = _normalize_seed_scores(seed_results)

        paths: list[_PathRecord] = []
        max_neighbors_expanded = 0
        for idx, seed in enumerate(seed_results):
            seed_node = str(seed.get("node_id", "") or "")
            if not seed_node or seed_node not in self.graph:
                continue
            # Keep track of traversal fanout in trace metadata.
            node_neighbors = self._neighbors_for(seed_node)
            max_neighbors_expanded = max(max_neighbors_expanded, len(node_neighbors))
            seed_strength = seed_scores[idx] if idx < len(seed_scores) else 0.0
            paths.extend(self._build_paths(seed_node=seed_node, seed_strength=seed_strength))

        ranked_rows, trace_paths = self._score_paths(paths, issue_text)
        limit = self.max_return_files if top_k is None else max(int(top_k), 1)
        top_rows, adaptive_cutoff = self._select_top_rows(
            ranked_rows,
            limit=limit,
        )
        files = [str(row["file"]) for row in top_rows]

        token_usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": int(search_outcome.get("query_embedding_tokens", 0) or 0),
            "tool_calls": 0,
            "tool_cache_hits": 0,
            "tool_response_chars": 0,
            "tool_calls_by_name": {},
            "stop_reason": "deterministic_complete",
            "manager_telemetry": {
                "tool_calls": 0,
                "tool_cache_hits": 0,
                "tool_response_chars": 0,
                "tool_calls_by_name": {},
                "stop_reason": "deterministic_complete",
                "seed_count": len(seed_results),
                "paths_considered": len(trace_paths),
            },
        }

        self.last_trace = {
            "query": issue_text,
            "seed_results": [
                {
                    "node_id": str(seed.get("node_id", "") or ""),
                    "score": float(seed.get("score", 0.0) or 0.0),
                    "normalized_score": seed_scores[idx] if idx < len(seed_scores) else 0.0,
                    "file": self._canonical_file_for_node(str(seed.get("node_id", "") or "")),
                }
                for idx, seed in enumerate(seed_results)
            ],
            "paths": trace_paths,
            "budget": {
                "seed_k": self.seed_k,
                "depth": self.depth,
                "neighbor_cap": self.neighbor_cap,
                "max_neighbors_expanded": max_neighbors_expanded,
            },
            "weights": dict(self.weights),
            "selection": {
                "max_return_files": self.max_return_files,
                "min_return_files": self.min_return_files,
                "score_ratio_cutoff": self.score_ratio_cutoff,
                "min_score_cutoff": self.min_score_cutoff,
                "effective_score_cutoff": adaptive_cutoff,
                "hub_degree_threshold": self.hub_degree_threshold,
                "hub_penalty_scale": self.hub_penalty_scale,
            },
            "ranked_files": top_rows,
        }
        return files, token_usage


__all__ = [
    "DeterministicGraphRetriever",
    "DEFAULT_ALLOWED_EDGE_TYPES",
    "DEFAULT_WEIGHTS",
    "score_file_evidence",
]
