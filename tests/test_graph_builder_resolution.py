import json
import tempfile
import unittest
from pathlib import Path

from src.graph_builder import GraphBuilder


class GraphBuilderResolutionTests(unittest.TestCase):
    def _build_graph(self, files: dict[str, str]):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for rel_path, content in files.items():
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            builder = GraphBuilder(str(root))
            return builder.build()

    def _call_targets(self, graph, caller_id: str) -> set[str]:
        return {
            dst
            for _, dst, attrs in graph.out_edges(caller_id, data=True)
            if attrs.get("type") == "CALLS"
        }

    def _inherits_targets(self, graph, child_class_id: str) -> set[str]:
        return {
            dst
            for _, dst, attrs in graph.out_edges(child_class_id, data=True)
            if attrs.get("type") == "INHERITS"
        }

    def _call_edge_confidence(self, graph, caller_id: str, callee_id: str) -> str | None:
        attrs = graph.get_edge_data(caller_id, callee_id, default={})
        if attrs.get("type") != "CALLS":
            return None
        return attrs.get("confidence")

    def test_call_resolution_cascade(self):
        graph = self._build_graph(
            {
                "a.py": """
class A:
    def foo(self):
        return 1

    def bar(self):
        return self.foo()

class B:
    def foo(self):
        return 2

def foo():
    return 3

def caller_local():
    return foo()
""",
                "b.py": """
def foo():
    return 10
""",
                "c.py": """
from a import foo as imported_foo
import b as mod

def call_imported():
    return imported_foo()

def call_module():
    return mod.foo()
""",
                "pkg1/mod.py": """
def foo():
    return "pkg1"
""",
                "pkg1/sub/caller.py": """
def call_global():
    return foo()
""",
                "pkg2/mod.py": """
def foo():
    return "pkg2"
""",
            }
        )

        self.assertIn("a.py::A.foo", self._call_targets(graph, "a.py::A.bar"))
        self.assertNotIn("a.py::B.foo", self._call_targets(graph, "a.py::A.bar"))
        self.assertNotIn("a.py::foo", self._call_targets(graph, "a.py::A.bar"))
        self.assertNotIn("b.py::foo", self._call_targets(graph, "a.py::A.bar"))

        self.assertEqual(self._call_targets(graph, "a.py::caller_local"), {"a.py::foo"})
        self.assertEqual(self._call_targets(graph, "c.py::call_imported"), {"a.py::foo"})
        self.assertEqual(self._call_targets(graph, "c.py::call_module"), {"b.py::foo"})
        self.assertEqual(
            self._call_targets(graph, "pkg1/sub/caller.py::call_global"),
            {"pkg1/mod.py::foo"},
        )

    def test_inherits_edges_resolved_from_imports_and_local_scope(self):
        graph = self._build_graph(
            {
                "base.py": """
class Base:
    pass
""",
                "child.py": """
from base import Base
import base as base_module

class ChildA(Base):
    pass

class ChildB(base_module.Base):
    pass
""",
                "local.py": """
class Parent:
    pass

class Child(Parent):
    pass
""",
            }
        )

        self.assertEqual(self._inherits_targets(graph, "child.py::ChildA"), {"base.py::Base"})
        self.assertEqual(self._inherits_targets(graph, "child.py::ChildB"), {"base.py::Base"})
        self.assertEqual(self._inherits_targets(graph, "local.py::Child"), {"local.py::Parent"})

    def test_call_resolution_honors_wildcard_import_before_global_fallback(self):
        graph = self._build_graph(
            {
                "pkg1/__init__.py": """
from .mod1 import foo
""",
                "pkg1/mod1.py": """
def foo():
    return "pkg1"
""",
                "pkg2/mod2.py": """
def foo():
    return "pkg2"
""",
                "pkg2/caller.py": """
from pkg1 import *

def run():
    return foo()
""",
            }
        )

        self.assertEqual(
            self._call_targets(graph, "pkg2/caller.py::run"),
            {"pkg1/mod1.py::foo"},
        )

    def test_call_resolution_prefers_same_module_symbol_over_imported_and_global(self):
        graph = self._build_graph(
            {
                "shared.py": """
def foo():
    return "shared"
""",
                "remote.py": """
def foo():
    return "remote"
""",
                "caller.py": """
from remote import foo

def foo():
    return "local"

def run():
    return foo()
""",
            }
        )

        self.assertEqual(self._call_targets(graph, "caller.py::run"), {"caller.py::foo"})

    def test_call_resolution_uses_latest_import_binding_for_same_alias(self):
        graph = self._build_graph(
            {
                "pkg_a.py": """
def foo():
    return "a"
""",
                "pkg_b.py": """
def foo():
    return "b"
""",
                "caller.py": """
from pkg_a import foo
from pkg_b import foo

def run():
    return foo()
""",
            }
        )

        self.assertEqual(self._call_targets(graph, "caller.py::run"), {"pkg_b.py::foo"})

    def test_call_resolution_disambiguates_methods_using_local_type_hint(self):
        graph = self._build_graph(
            {
                "services.py": """
class Alpha:
    def execute(self):
        return "alpha"

class Beta:
    def execute(self):
        return "beta"
""",
                "caller.py": """
from services import Alpha, Beta

def run():
    service: Beta = Beta()
    return service.execute()
""",
            }
        )

        targets = self._call_targets(graph, "caller.py::run")
        self.assertIn("services.py::Beta.execute", targets)
        self.assertNotIn("services.py::Alpha.execute", targets)

    def test_call_resolution_adds_confidence_metadata(self):
        graph = self._build_graph(
            {
                "external.py": """
def foo():
    return 1
""",
                "local.py": """
def local_target():
    return 1

class Worker:
    def fallback(self):
        return 1

def run():
    local_target()
    fallback()
    foo()
""",
            }
        )

        self.assertEqual(
            self._call_edge_confidence(graph, "local.py::run", "local.py::local_target"),
            "high",
        )
        self.assertEqual(
            self._call_edge_confidence(graph, "local.py::run", "local.py::Worker.fallback"),
            "medium",
        )
        self.assertEqual(
            self._call_edge_confidence(graph, "local.py::run", "external.py::foo"),
            "low",
        )

    def test_call_resolution_can_disable_low_confidence_edges(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target.py").write_text(
                """
def foo():
    return 1
""",
                encoding="utf-8",
            )
            (root / "caller.py").write_text(
                """
def run():
    return foo()
""",
                encoding="utf-8",
            )

            builder = GraphBuilder(str(root), include_low_confidence_calls=False)
            graph = builder.build()

        self.assertEqual(self._call_targets(graph, "caller.py::run"), set())

    def test_graph_export_includes_call_confidence_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target.py").write_text(
                """
def foo():
    return 1
""",
                encoding="utf-8",
            )
            (root / "caller.py").write_text(
                """
def run():
    return foo()
""",
                encoding="utf-8",
            )

            output_path = root / "graph.json"
            builder = GraphBuilder(str(root))
            builder.build()
            builder.save(str(output_path))
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        call_edges = [
            edge
            for edge in payload["edges"]
            if edge["source"] == "caller.py::run"
            and edge["target"] == "target.py::foo"
            and edge["type"] == "CALLS"
        ]
        self.assertEqual(len(call_edges), 1)
        self.assertEqual(call_edges[0].get("confidence"), "low")


if __name__ == "__main__":
    unittest.main()
