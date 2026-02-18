import unittest

import networkx as nx

from src.manager_agent import ManagerAgent
from src.manager_agent import serialize_manager_telemetry
from src.rag_baseline import RAGAgent


class _DummyModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, **kwargs):
        class _Content:
            parts = []

        class _Candidate:
            content = _Content()

        class _Response:
            usage_metadata = None
            candidates = [_Candidate()]
            text = ""

        response = _Response()
        response.text = self._text
        return response


class _DummyClient:
    def __init__(self, text: str):
        self.models = _DummyModels(text)


class _DummyRAGIndex:
    def __init__(self):
        self.chunks = [
            {"file": "src/flask/app.py", "text": "def app():\n  pass"},
            {"file": "src/flask/helpers.py", "text": "def helper():\n  pass"},
        ]

    def search(self, query: str, top_k: int = 5):
        return {"results": [], "query_embedding_tokens": 0}


class _DummyGraphIndex:
    def search(self, query: str, top_k: int = 5):
        return {
            "results": [
                {
                    "node_id": "src/flask/app.py::app",
                    "name": "app",
                    "type": "function",
                    "file": "src/flask/app.py",
                    "docstring": "Very long function docstring that should not be returned in compact mode.",
                    "signature": "(environ, start_response)",
                    "score": 0.91,
                }
            ],
            "query_embedding_tokens": 3,
        }


class AgentGroundingTests(unittest.TestCase):
    def test_serialize_manager_telemetry_payload(self):
        telemetry = serialize_manager_telemetry(
            {
                "tool_calls": 4,
                "tool_cache_hits": 2,
                "tool_response_chars": 120,
                "tool_calls_by_name": {"search_nodes": 2, "get_neighbors": 2},
                "stop_reason": "max_turns",
            }
        )
        self.assertEqual(telemetry["tool_calls"], 4)
        self.assertEqual(telemetry["tool_cache_hits"], 2)
        self.assertEqual(telemetry["tool_response_chars"], 120)
        self.assertEqual(telemetry["tool_calls_by_name"]["search_nodes"], 2)
        self.assertEqual(telemetry["stop_reason"], "max_turns")

    def test_manager_rejects_zero_tool_hallucinated_path(self):
        graph = nx.DiGraph()
        graph.add_node("src/flask/app.py", type="file", docstring="")
        agent = ManagerAgent(
            graph=graph,
            graph_index=None,
            gemini_client=_DummyClient('{"files":["src/flask/ghost.py"]}'),
            retrieval_mode="progressive",
        )
        files, tokens = agent.find_relevant_files("irrelevant", max_turns=1)
        self.assertEqual(files, [])
        self.assertEqual(tokens["tool_calls"], 0)
        self.assertEqual(tokens["stop_reason"], "budget")
        self.assertEqual(tokens["manager_telemetry"]["stop_reason"], "budget")
        self.assertEqual(tokens["manager_telemetry"]["tool_calls"], 0)

    def test_rag_rejects_zero_tool_hallucinated_path(self):
        agent = RAGAgent(
            rag_index=_DummyRAGIndex(),
            gemini_client=_DummyClient('{"files":["src/flask/ghost.py"]}'),
            retrieval_mode="progressive",
        )
        files, tokens = agent.find_relevant_files("irrelevant", max_turns=1)
        self.assertEqual(files, [])
        self.assertEqual(tokens["tool_calls"], 0)

    def test_manager_finalize_canonicalizes_suffix_when_observed(self):
        graph = nx.DiGraph()
        graph.add_node("src/flask/app.py", type="file", docstring="")
        agent = ManagerAgent(
            graph=graph,
            graph_index=None,
            gemini_client=_DummyClient(""),
            retrieval_mode="progressive",
        )
        finalized = agent._finalize_file_list(
            files=["flask/app.py"],
            confirmed_files=set(),
            observed_files={"src/flask/app.py"},
        )
        self.assertEqual(finalized, ["src/flask/app.py"])

    def test_manager_finalize_baseline_ranks_by_file_score(self):
        graph = nx.DiGraph()
        graph.add_node("src/flask/app.py", type="file", docstring="")
        graph.add_node("src/flask/helpers.py", type="file", docstring="")
        agent = ManagerAgent(
            graph=graph,
            graph_index=None,
            gemini_client=_DummyClient(""),
            retrieval_mode="baseline",
        )
        finalized = agent._finalize_file_list(
            files=["src/flask/app.py", "src/flask/helpers.py"],
            confirmed_files=set(),
            observed_files={"src/flask/app.py", "src/flask/helpers.py"},
            file_scores={
                "src/flask/app.py": 0.1,
                "src/flask/helpers.py": 2.0,
            },
        )
        self.assertEqual(finalized, ["src/flask/helpers.py", "src/flask/app.py"])

    def test_manager_finalize_progressive_drops_unconfirmed_when_confirmed_exist(self):
        graph = nx.DiGraph()
        graph.add_node("src/flask/app.py", type="file", docstring="")
        graph.add_node("src/flask/helpers.py", type="file", docstring="")
        agent = ManagerAgent(
            graph=graph,
            graph_index=None,
            gemini_client=_DummyClient(""),
            retrieval_mode="progressive",
        )
        finalized = agent._finalize_file_list(
            files=["src/flask/app.py", "src/flask/helpers.py"],
            confirmed_files={"src/flask/app.py"},
            observed_files={"src/flask/app.py", "src/flask/helpers.py"},
            file_scores={
                "src/flask/app.py": 0.1,
                "src/flask/helpers.py": 3.0,
            },
        )
        self.assertEqual(finalized, ["src/flask/app.py"])

    def test_manager_compact_search_payload_drops_docstring_and_signature(self):
        graph = nx.DiGraph()
        graph.add_node("src/flask/app.py", type="file", docstring="")
        graph.add_node(
            "src/flask/app.py::app",
            type="function",
            name="app",
            file="src/flask/app.py",
            docstring="Very long function docstring",
            signature="(environ, start_response)",
        )
        agent = ManagerAgent(
            graph=graph,
            graph_index=_DummyGraphIndex(),
            gemini_client=_DummyClient(""),
            retrieval_mode="progressive",
        )

        result, usage = agent._execute_tool("search_nodes", {"query": "app"})
        self.assertEqual(usage["query_embedding_tokens"], 3)
        self.assertEqual(len(result), 1)
        self.assertNotIn("docstring", result[0])
        self.assertNotIn("signature", result[0])

    def test_rag_finalize_ranks_by_file_score(self):
        agent = RAGAgent(
            rag_index=_DummyRAGIndex(),
            gemini_client=_DummyClient(""),
            retrieval_mode="progressive",
        )
        finalized = agent._finalize_file_list(
            files=["src/flask/app.py", "src/flask/helpers.py"],
            observed_files={"src/flask/app.py", "src/flask/helpers.py"},
            file_scores={
                "src/flask/app.py": 0.2,
                "src/flask/helpers.py": 1.4,
            },
        )
        self.assertEqual(finalized, ["src/flask/helpers.py", "src/flask/app.py"])


if __name__ == "__main__":
    unittest.main()
