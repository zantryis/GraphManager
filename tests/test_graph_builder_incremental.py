import tempfile
import unittest
from pathlib import Path

from src.graph_builder import GraphBuilder


class GraphBuilderIncrementalTests(unittest.TestCase):
    def _graph_snapshot(self, graph) -> tuple[list[tuple], list[tuple]]:
        node_snapshot = sorted(
            (
                node_id,
                tuple(sorted((key, value) for key, value in attrs.items() if not key.startswith("_"))),
            )
            for node_id, attrs in graph.nodes(data=True)
        )
        edge_snapshot = sorted(
            (
                src,
                dst,
                tuple(sorted(attrs.items())),
            )
            for src, dst, attrs in graph.edges(data=True)
        )
        return node_snapshot, edge_snapshot

    def test_update_files_matches_full_rebuild_for_controlled_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "lib.py").write_text(
                """
def helper():
    return 1
""",
                encoding="utf-8",
            )
            (root / "caller.py").write_text(
                """
from lib import helper

def run():
    return helper()
""",
                encoding="utf-8",
            )

            incremental_builder = GraphBuilder(str(root))
            incremental_builder.build()

            (root / "lib.py").write_text(
                """
def helper():
    return 1

def extra():
    return helper()
""",
                encoding="utf-8",
            )

            incremental_graph = incremental_builder.update_files(["lib.py"])
            full_graph = GraphBuilder(str(root)).build()

        self.assertEqual(self._graph_snapshot(incremental_graph), self._graph_snapshot(full_graph))

    def test_recompute_edges_for_matches_full_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.py").write_text(
                """
def foo():
    return 1
""",
                encoding="utf-8",
            )
            (root / "b.py").write_text(
                """
def run():
    return foo()
""",
                encoding="utf-8",
            )

            incremental_builder = GraphBuilder(str(root))
            incremental_builder.build()

            (root / "b.py").write_text(
                """
from a import foo

def run():
    return foo()
""",
                encoding="utf-8",
            )

            incremental_graph = incremental_builder.recompute_edges_for(["b.py::run"], strategy="full")
            full_graph = GraphBuilder(str(root)).build()

        self.assertEqual(self._graph_snapshot(incremental_graph), self._graph_snapshot(full_graph))


if __name__ == "__main__":
    unittest.main()
