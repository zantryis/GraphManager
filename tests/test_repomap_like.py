import unittest

import networkx as nx

from src.repomap_like import RepoMapLikeRetriever


class _FakeUsage:
    prompt_token_count = 12
    candidates_token_count = 4
    total_token_count = 16


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = _FakeUsage()


class _FakeModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, model, contents):  # noqa: ARG002
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str):
        self.models = _FakeModels(text=text)


class RepoMapLikeRetrieverTests(unittest.TestCase):
    def _graph(self):
        graph = nx.DiGraph()
        for file_path in ("pkg/a.py", "pkg/b.py", "pkg/c.py", "tests/test_a.py"):
            graph.add_node(file_path, type="file")

        graph.add_node("pkg/a.py::fa", type="function", name="fa", file="pkg/a.py", start_line=1, end_line=5)
        graph.add_node("pkg/b.py::fb", type="function", name="fb", file="pkg/b.py", start_line=1, end_line=5)
        graph.add_node("pkg/c.py::fc", type="function", name="fc", file="pkg/c.py", start_line=1, end_line=5)
        graph.add_node("tests/test_a.py::test_a", type="function", name="test_a", file="tests/test_a.py", start_line=1, end_line=5)

        graph.add_edge("pkg/a.py", "pkg/b.py", type="IMPORTS")
        graph.add_edge("pkg/a.py::fa", "pkg/c.py::fc", type="CALLS")
        graph.add_edge("tests/test_a.py::test_a", "pkg/a.py::fa", type="CALLS")
        return graph

    def test_retriever_ranks_files_and_reports_edge_counts(self):
        retriever = RepoMapLikeRetriever(
            graph=self._graph(),
            top_k_files=3,
            map_tokens=500,
            use_llm_selector=False,
            personalization_enabled=True,
        )
        files, tokens = retriever.find_relevant_files("bug in pkg a and c")
        self.assertTrue(files)
        self.assertIn("pkg/a.py", files)
        self.assertIn("repomap_meta", tokens)
        meta = tokens["repomap_meta"]
        self.assertGreaterEqual(meta["edge_type_counts"]["import"], 1)
        self.assertGreaterEqual(meta["edge_type_counts"]["symbol_ref"], 1)

    def test_same_module_edge_toggle_affects_edge_counts(self):
        retriever = RepoMapLikeRetriever(
            graph=self._graph(),
            top_k_files=3,
            enable_same_module_edge=True,
            use_llm_selector=False,
        )
        _, tokens = retriever.find_relevant_files("anything")
        self.assertGreater(tokens["repomap_meta"]["edge_type_counts"]["same_module"], 0)

    def test_llm_selector_rejects_out_of_candidate_paths(self):
        client = _FakeClient(text='{"files":["not/in/repo.py","pkg/b.py"]}')
        retriever = RepoMapLikeRetriever(
            graph=self._graph(),
            client=client,
            use_llm_selector=True,
            top_k_files=2,
        )
        files, tokens = retriever.find_relevant_files("choose b")
        self.assertIn("pkg/b.py", files)
        self.assertGreater(tokens["repomap_meta"]["invalid_path_selection_count"], 0)
        self.assertEqual(tokens["total_tokens"], 16)


if __name__ == "__main__":
    unittest.main()
