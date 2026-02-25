import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.agentic_cold_start import AgenticColdStartAgent


class AgenticColdStartTests(unittest.TestCase):
    def test_collect_python_files_respects_prefixes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "requests").mkdir()
            (root / "docs").mkdir()
            (root / "requests" / "models.py").write_text("x = 1\n", encoding="utf-8")
            (root / "docs" / "conf.py").write_text("x = 2\n", encoding="utf-8")

            agent = AgenticColdStartAgent(
                repo_dir=str(root),
                client=MagicMock(),
                include_prefixes=("requests",),
            )

        self.assertEqual(agent._valid_files, {"requests/models.py"})

    def test_handle_get_file_contents_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "repo"
            repo.mkdir()
            (root / "secret.py").write_text("SECRET = 1\n", encoding="utf-8")
            agent = AgenticColdStartAgent(
                repo_dir=str(repo),
                client=MagicMock(),
            )
            observed = set()
            result = agent._handle_get_file_contents("../secret.py", observed)

        self.assertIn("Error", result)
        self.assertEqual(observed, set())

    def test_search_paths_scores_matching_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "requests").mkdir()
            (root / "requests" / "models.py").write_text("x = 1\n", encoding="utf-8")
            (root / "requests" / "sessions.py").write_text("x = 1\n", encoding="utf-8")
            agent = AgenticColdStartAgent(
                repo_dir=str(root),
                client=MagicMock(),
            )
            results = agent._search_paths("models", top_k=5)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["file"], "requests/models.py")


if __name__ == "__main__":
    unittest.main()
