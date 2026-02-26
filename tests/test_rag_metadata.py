"""Tests for RAGMetadataIndex — the metadata-embedding ablation baseline."""

import unittest
from unittest.mock import MagicMock

import networkx as nx
import numpy as np

from src.rag_baseline import RAGMetadataIndex, RawRAG
from src.evaluation import ALL_METHODS


class TestRAGMetadataInAllMethods(unittest.TestCase):
    def test_rag_metadata_in_all_methods(self):
        self.assertIn("rag_metadata", ALL_METHODS)

    def test_rag_metadata_positioned_near_raw_rag(self):
        # Should sit in the Tier-0 / raw-search block alongside raw_rag_*
        idx_meta = ALL_METHODS.index("rag_metadata")
        idx_func = ALL_METHODS.index("raw_rag_function")
        idx_fixed = ALL_METHODS.index("raw_rag_fixed")
        self.assertLess(abs(idx_meta - idx_func), 4)
        self.assertLess(abs(idx_meta - idx_fixed), 4)


class TestRAGMetadataIndexBuildAndSearch(unittest.TestCase):
    def _make_graph(self):
        """Small graph with two function nodes in different files."""
        g = nx.DiGraph()
        g.add_node(
            "src/module_a.py",
            type="file",
            docstring="",
        )
        g.add_node(
            "src/module_b.py",
            type="file",
            docstring="",
        )
        g.add_node(
            "src/module_a.py::calculate_total",
            type="function",
            name="calculate_total",
            signature="(self, items)",
            docstring="Calculate total price of items.",
            file="src/module_a.py",
            start_line=10,
            end_line=20,
        )
        g.add_node(
            "src/module_b.py::format_output",
            type="function",
            name="format_output",
            signature="(data)",
            docstring="Format output data for display.",
            file="src/module_b.py",
            start_line=5,
            end_line=15,
        )
        return g

    def _mock_client(self, dim=768):
        """Client whose embed_content returns unit vectors."""
        client = MagicMock()
        def fake_embed(model, contents, config=None):
            n = len(contents) if isinstance(contents, list) else 1
            resp = MagicMock()
            resp.embeddings = []
            for _ in range(n):
                vec = MagicMock()
                arr = np.random.rand(dim).astype(np.float32)
                arr /= np.linalg.norm(arr)
                vec.values = arr.tolist()
                resp.embeddings.append(vec)
            return resp
        client.models.embed_content.side_effect = fake_embed
        return client

    def test_build_creates_chunks_for_functions_and_classes(self):
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()

        # Should have 2 chunks (one per function node)
        self.assertEqual(len(idx.chunks), 2)
        files = {c["file"] for c in idx.chunks}
        self.assertIn("src/module_a.py", files)
        self.assertIn("src/module_b.py", files)

    def test_build_text_matches_graphindex_format(self):
        """Chunk text must be identical to what GraphIndex.build() produces."""
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()

        chunk_a = next(c for c in idx.chunks if c["name"] == "calculate_total")
        # GraphIndex format: name + signature + ": " + docstring[:200]
        expected = "calculate_total(self, items): Calculate total price of items."
        self.assertEqual(chunk_a["text"], expected)

    def test_build_skips_file_nodes(self):
        """File-type nodes must not appear as chunks."""
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()
        names = {c["name"] for c in idx.chunks}
        self.assertNotIn("src/module_a.py", names)
        self.assertNotIn("src/module_b.py", names)

    def test_build_empty_graph_produces_no_chunks(self):
        graph = nx.DiGraph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()
        self.assertEqual(len(idx.chunks), 0)
        self.assertIsNone(idx.index)

    def test_search_returns_correct_format(self):
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()

        result = idx.search("calculate total price", top_k=5)
        self.assertIn("results", result)
        self.assertIn("query_embedding_tokens", result)
        for r in result["results"]:
            self.assertIn("file", r)
            self.assertIn("score", r)
            self.assertIsInstance(r["score"], float)

    def test_search_returns_unique_files(self):
        """Each file should appear at most once in search results."""
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()

        result = idx.search("any query", top_k=10)
        files = [r["file"] for r in result["results"]]
        self.assertEqual(len(files), len(set(files)))

    def test_search_empty_index_returns_empty(self):
        graph = nx.DiGraph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()  # empty

        result = idx.search("query")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["query_embedding_tokens"], 0)

    def test_rawrag_works_with_rag_metadata_index(self):
        """RawRAG should work unmodified with RAGMetadataIndex (same interface)."""
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()

        agent = RawRAG(idx)
        files, tokens = agent.find_relevant_files("calculate total price")
        self.assertIsInstance(files, list)
        self.assertIsInstance(tokens, dict)
        self.assertIn("query_embedding_tokens", tokens)
        # All returned files must be real graph file paths
        for f in files:
            self.assertIn(f, {"src/module_a.py", "src/module_b.py"})

    def test_embedding_tokens_estimate_nonzero_after_build(self):
        graph = self._make_graph()
        client = self._mock_client()
        idx = RAGMetadataIndex(graph, client)
        idx.build()
        self.assertGreater(idx.embedding_tokens_estimate, 0)


class TestRAGMetadataInValidateCommitContext(unittest.TestCase):
    def test_validate_passes_with_rag_metadata_tokens(self):
        from src.evaluation import validate_commit_context
        context = {
            "graph_file_paths": {"src/a.py"},
            "setup_costs": {
                "rag_metadata": {"embedding_tokens": 500},
            },
        }
        # Should not raise
        validate_commit_context(context, required_methods=("rag_metadata",))

    def test_validate_raises_when_rag_metadata_empty(self):
        from src.evaluation import validate_commit_context
        context = {
            "graph_file_paths": {"src/a.py"},
            "setup_costs": {
                "rag_metadata": {"embedding_tokens": 0},
            },
        }
        with self.assertRaises(ValueError) as cm:
            validate_commit_context(context, required_methods=("rag_metadata",))
        self.assertIn("rag_metadata", str(cm.exception))

    def test_validate_raises_when_graph_empty_for_rag_metadata(self):
        from src.evaluation import validate_commit_context
        context = {
            "graph_file_paths": set(),  # empty graph
            "setup_costs": {
                "rag_metadata": {"embedding_tokens": 500},
            },
        }
        with self.assertRaises(ValueError):
            validate_commit_context(context, required_methods=("rag_metadata",))


if __name__ == "__main__":
    unittest.main()
