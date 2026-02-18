import copy
import tempfile
import unittest
from pathlib import Path

from src.graph_builder import GraphBuilder


class ImportMappingCacheTests(unittest.TestCase):
    def _build_import_map(self, files: dict[str, str]) -> dict[str, dict[str, list[dict]]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for rel_path, content in files.items():
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            builder = GraphBuilder(str(root))
            builder.build()
            return copy.deepcopy(builder.file_import_map)

    def test_import_map_cache_captures_module_symbol_and_relative_module_aliases(self):
        import_map = self._build_import_map(
            {
                "pkg/__init__.py": "",
                "pkg/utils.py": """
def helper():
    return "ok"
""",
                "pkg/sub/__init__.py": "",
                "pkg/sub/local.py": """
def run():
    return 1
""",
                "pkg/sub/caller.py": """
import pkg.utils as utils_mod
from pkg.utils import helper as h
from . import local as local_mod
""",
            }
        )

        caller_map = import_map["pkg/sub/caller.py"]
        self.assertEqual(caller_map["utils_mod"][0]["kind"], "module")
        self.assertEqual(caller_map["utils_mod"][0]["target_file"], "pkg/utils.py")
        self.assertEqual(caller_map["h"][0]["kind"], "symbol")
        self.assertEqual(caller_map["h"][0]["target_node"], "pkg/utils.py::helper")
        self.assertEqual(caller_map["local_mod"][0]["kind"], "module")
        self.assertEqual(caller_map["local_mod"][0]["target_file"], "pkg/sub/local.py")

    def test_import_map_cache_is_isolated_per_file(self):
        import_map = self._build_import_map(
            {
                "pkg/utils.py": """
def helper():
    return "ok"
""",
                "a.py": """
import pkg.utils as utils
""",
                "b.py": """
from pkg.utils import helper
""",
            }
        )

        self.assertIn("utils", import_map["a.py"])
        self.assertNotIn("helper", import_map["a.py"])
        self.assertIn("helper", import_map["b.py"])
        self.assertNotIn("utils", import_map["b.py"])
        self.assertEqual(import_map["a.py"]["utils"][0]["target_file"], "pkg/utils.py")
        self.assertEqual(import_map["b.py"]["helper"][0]["target_node"], "pkg/utils.py::helper")


if __name__ == "__main__":
    unittest.main()
