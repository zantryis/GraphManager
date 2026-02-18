import unittest

import networkx as nx

from src.deterministic_retrieval import DeterministicGraphRetriever


class _FakeGraphIndex:
    def __init__(self, results: list[dict], query_embedding_tokens: int = 9):
        self._results = list(results)
        self.query_embedding_tokens = query_embedding_tokens
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 10) -> dict:
        self.calls.append((query, top_k))
        return {
            "results": self._results[:top_k],
            "query_embedding_tokens": self.query_embedding_tokens,
        }


def _add_file_and_function(graph: nx.DiGraph, file_path: str, func_name: str) -> str:
    graph.add_node(file_path, type="file", docstring="")
    node_id = f"{file_path}::{func_name}"
    graph.add_node(node_id, type="function", file=file_path, name=func_name)
    graph.add_edge(file_path, node_id, type="DEFINES")
    return node_id


class DeterministicRetrievalTests(unittest.TestCase):
    def test_deterministic_ranking_stability(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/a.py", "seed")
        high = _add_file_and_function(graph, "pkg/b.py", "high_target")
        low = _add_file_and_function(graph, "pkg/c.py", "low_target")
        graph.add_edge(seed, high, type="CALLS", confidence="high")
        graph.add_edge(seed, low, type="CALLS", confidence="low")

        index = _FakeGraphIndex([{"node_id": seed, "score": 0.99}])
        retriever = DeterministicGraphRetriever(graph, index)

        files_first, tokens_first = retriever.find_relevant_files("fix seed path")
        trace_first = retriever.last_trace
        files_second, tokens_second = retriever.find_relevant_files("fix seed path")
        trace_second = retriever.last_trace

        self.assertEqual(files_first, files_second)
        self.assertEqual(tokens_first["query_embedding_tokens"], 9)
        self.assertEqual(tokens_first, tokens_second)
        self.assertEqual(trace_first["ranked_files"], trace_second["ranked_files"])

    def test_budget_guards_cap_depth_and_fanout(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/a.py", "seed")
        left = _add_file_and_function(graph, "pkg/b.py", "left")
        right = _add_file_and_function(graph, "pkg/c.py", "right")
        deep = _add_file_and_function(graph, "pkg/d.py", "deep")

        graph.add_edge(seed, left, type="CALLS", confidence="medium")
        graph.add_edge(seed, right, type="CALLS", confidence="medium")
        graph.add_edge(left, deep, type="CALLS", confidence="high")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(
            graph,
            index,
            depth=1,
            neighbor_cap=1,
        )

        files, _ = retriever.find_relevant_files("depth guard")
        trace = retriever.last_trace

        self.assertNotIn("pkg/d.py", files)
        self.assertTrue(all(path["depth"] <= 1 for path in trace["paths"]))
        self.assertEqual(trace["budget"]["depth"], 1)
        self.assertEqual(trace["budget"]["neighbor_cap"], 1)
        self.assertLessEqual(trace["budget"]["max_neighbors_expanded"], 1)

    def test_confidence_monotonicity_prefers_high_confidence_support(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/a.py", "seed")
        high = _add_file_and_function(graph, "pkg/b.py", "high_target")
        low = _add_file_and_function(graph, "pkg/c.py", "low_target")

        graph.add_edge(seed, high, type="CALLS", confidence="high")
        graph.add_edge(seed, low, type="CALLS", confidence="low")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(
            graph,
            index,
            score_ratio_cutoff=0.0,
        )

        retriever.find_relevant_files("confidence test")
        ranked = {row["file"]: row for row in retriever.last_trace["ranked_files"]}

        self.assertGreater(ranked["pkg/b.py"]["components"]["s_conf"], ranked["pkg/c.py"]["components"]["s_conf"])
        self.assertGreater(ranked["pkg/b.py"]["score"], ranked["pkg/c.py"]["score"])

    def test_low_confidence_only_penalty_is_applied(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/a.py", "seed")
        low_only = _add_file_and_function(graph, "pkg/b.py", "low_only")
        supported = _add_file_and_function(graph, "pkg/c.py", "supported")

        graph.add_edge(seed, low_only, type="CALLS", confidence="low")
        graph.add_edge(seed, supported, type="CALLS", confidence="medium")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(
            graph,
            index,
            score_ratio_cutoff=0.0,
        )

        retriever.find_relevant_files("penalty test")
        ranked = {row["file"]: row for row in retriever.last_trace["ranked_files"]}

        self.assertGreater(ranked["pkg/b.py"]["components"]["s_pen"], 0.0)
        self.assertEqual(ranked["pkg/c.py"]["components"]["s_pen"], 0.0)
        self.assertLess(ranked["pkg/b.py"]["score"], ranked["pkg/c.py"]["score"])

    def test_no_ungrounded_file_leakage_after_canonicalization(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "src/pkg/a.py", "seed")
        grounded = _add_file_and_function(graph, "src/pkg/b.py", "grounded")
        graph.add_node("ghost::fn", type="function", file="ghost/pkg/hidden.py", name="ghost")

        graph.add_edge(seed, grounded, type="CALLS", confidence="high")
        graph.add_edge(seed, "ghost::fn", type="CALLS", confidence="high")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(graph, index)

        files, _ = retriever.find_relevant_files("canonicalization test")

        self.assertIn("src/pkg/b.py", files)
        self.assertNotIn("ghost/pkg/hidden.py", files)

    def test_adaptive_score_cutoff_trims_low_scoring_tail_files(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/high.py", "seed")
        low = _add_file_and_function(graph, "pkg/low.py", "low_target")
        graph.add_edge(seed, low, type="CALLS", confidence="low")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(
            graph,
            index,
            max_return_files=6,
            score_ratio_cutoff=0.70,
        )

        files, _ = retriever.find_relevant_files("high precision cutoff")

        self.assertIn("pkg/high.py", files)
        self.assertNotIn("pkg/low.py", files)

    def test_hub_penalty_demotes_generic_high_degree_file(self):
        graph = nx.DiGraph()
        seed = _add_file_and_function(graph, "pkg/seed.py", "seed")
        hub = _add_file_and_function(graph, "pkg/hub.py", "hub_target")
        specific = _add_file_and_function(graph, "pkg/specific.py", "specific_target")
        graph.add_edge(seed, hub, type="CALLS", confidence="high")
        graph.add_edge(seed, specific, type="CALLS", confidence="high")

        # Inflate hub connectivity so it behaves like a generic magnet file.
        for idx in range(6):
            extra = _add_file_and_function(graph, f"pkg/extra_{idx}.py", f"extra_{idx}")
            graph.add_edge(hub, extra, type="CALLS", confidence="high")

        index = _FakeGraphIndex([{"node_id": seed, "score": 1.0}])
        retriever = DeterministicGraphRetriever(
            graph,
            index,
            hub_degree_threshold=2,
            w_pen=0.40,
        )

        retriever.find_relevant_files("prioritize specific target")
        ranked = {row["file"]: row for row in retriever.last_trace["ranked_files"]}

        self.assertGreater(ranked["pkg/hub.py"]["components"]["s_pen"], ranked["pkg/specific.py"]["components"]["s_pen"])
        self.assertLess(ranked["pkg/hub.py"]["score"], ranked["pkg/specific.py"]["score"])


if __name__ == "__main__":
    unittest.main()
