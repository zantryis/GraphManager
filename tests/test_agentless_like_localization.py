import unittest

import networkx as nx

from src.agentless_like_localization import AgentlessLikeLocalizer


class _FakeUsage:
    prompt_token_count = 10
    candidates_token_count = 3
    total_token_count = 13


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = _FakeUsage()


class _FakeModels:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    def generate_content(self, model, contents):  # noqa: ARG002
        text = self._responses.pop(0) if self._responses else "{}"
        return _FakeResponse(text)


class _FakeClient:
    def __init__(self, responses: list[str]):
        self.models = _FakeModels(responses)


class _FakeRAGIndex:
    def __init__(self):
        self.chunks = [
            {"file": "pkg/a.py", "text": "def fa():\n    return 1\n", "start_line": 1, "end_line": 5},
            {
                "file": "pkg/b.py",
                "text": "def fb():\n    value = 1\n    return value\n",
                "start_line": 1,
                "end_line": 8,
            },
            {"file": "pkg/c.py", "text": "def fc():\n    return 3\n", "start_line": 1, "end_line": 5},
        ]

    def search(self, query: str, top_k: int = 20):  # noqa: ARG002
        return {
            "results": [
                {"file": "pkg/b.py", "score": 0.9},
                {"file": "pkg/c.py", "score": 0.6},
                {"file": "pkg/a.py", "score": 0.5},
            ][:top_k],
            "query_embedding_tokens": 5,
        }


class AgentlessLikeLocalizationTests(unittest.TestCase):
    def _graph(self):
        graph = nx.DiGraph()
        for file_path in ("pkg/a.py", "pkg/b.py", "pkg/c.py"):
            graph.add_node(file_path, type="file")
        graph.add_node("pkg/a.py::fa", type="function", file="pkg/a.py", name="fa", start_line=3, end_line=10)
        graph.add_node("pkg/b.py::fb", type="function", file="pkg/b.py", name="fb", start_line=5, end_line=20)
        graph.add_node("pkg/c.py::fc", type="function", file="pkg/c.py", name="fc", start_line=7, end_line=9)
        return graph

    def test_localizer_without_llm_returns_ranked_files(self):
        localizer = AgentlessLikeLocalizer(
            rag_index=_FakeRAGIndex(),
            graph=self._graph(),
            client=None,
            stage2_enabled=False,
            stage3_enabled=False,
            merge_top_k=3,
        )
        files, tokens = localizer.find_relevant_files("bug around b")
        self.assertTrue(files)
        self.assertIn("pkg/b.py", files)
        self.assertEqual(tokens["query_embedding_tokens"], 5)
        self.assertIn("agentless_like_meta", tokens)

    def test_localizer_rejects_out_of_candidate_paths(self):
        client = _FakeClient(
            responses=[
                '{"files":["bad/path.py","pkg/b.py"]}',
                '{"symbols":["pkg/b.py::fb"]}',
                '{"spans":[{"symbol_id":"pkg/b.py::fb","confidence":0.8}]}',
            ]
        )
        localizer = AgentlessLikeLocalizer(
            rag_index=_FakeRAGIndex(),
            graph=self._graph(),
            client=client,
            stage2_enabled=True,
            stage3_enabled=True,
            file_branch_top_n=2,
            merge_top_k=3,
        )
        files, tokens = localizer.find_relevant_files("choose b")
        self.assertIn("pkg/b.py", files)
        meta = tokens["agentless_like_meta"]
        self.assertGreater(meta["stage1_invalid_selection_count"], 0)
        self.assertGreater(tokens["total_tokens"], 0)

    def test_stage3_context_budget_is_enforced_per_file(self):
        class _LongChunkRAG(_FakeRAGIndex):
            def __init__(self):
                super().__init__()
                self.chunks = [
                    {
                        "file": "pkg/b.py",
                        "text": "X" * 2000,
                        "start_line": 1,
                        "end_line": 40,
                    }
                ]

        client = _FakeClient(
            responses=[
                '{"files":["pkg/b.py"]}',
                '{"symbols":["pkg/b.py::fb"]}',
                '{"spans":[{"symbol_id":"pkg/b.py::fb","confidence":0.9}]}',
            ]
        )
        localizer = AgentlessLikeLocalizer(
            rag_index=_LongChunkRAG(),
            graph=self._graph(),
            client=client,
            stage2_enabled=True,
            stage3_enabled=True,
            stage3_max_tokens_per_file=20,
            file_branch_top_n=1,
            merge_top_k=1,
        )
        _, tokens = localizer.find_relevant_files("pick b")
        per_file = tokens["agentless_like_meta"]["stage3_context_tokens_per_file"]
        self.assertIn("pkg/b.py", per_file)
        self.assertLessEqual(per_file["pkg/b.py"], 20)

    def test_stage3_deterministic_spans_are_stable(self):
        localizer = AgentlessLikeLocalizer(
            rag_index=_FakeRAGIndex(),
            graph=self._graph(),
            client=None,
            stage2_enabled=False,
            stage3_enabled=False,
            edit_location_samples=2,
        )
        symbols = [
            {
                "file": "pkg/a.py",
                "symbol_id": "pkg/a.py::fa",
                "start_line": 3,
                "end_line": 10,
            },
            {
                "file": "pkg/b.py",
                "symbol_id": "pkg/b.py::fb",
                "start_line": 5,
                "end_line": 20,
            },
        ]
        first = localizer._deterministic_stage3_spans(symbols, "same issue text")
        second = localizer._deterministic_stage3_spans(symbols, "same issue text")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
