"""Tests for the symmetric get_file_contents tool added to RAGAgent (Step 2).

TDD: these tests are written before the implementation.

Covers:
  - _handle_get_file_contents returns correct file contents when file exists
  - _handle_get_file_contents returns error string when file doesn't exist (no crash)
  - _handle_get_file_contents clips content to max_file_chars
  - RAGAgent symmetric_tools=False by default (backward compatibility)
  - RAGAgent symmetric_tools=True only when repo_dir is also provided
  - RAGAgent symmetric_tools=True with repo_dir sets self.symmetric_tools=True
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class RAGAgentSymmetricToolsInitTests(unittest.TestCase):
    """Test RAGAgent __init__ with symmetric tools config."""

    def _make_mock_rag_index(self):
        mock_index = MagicMock()
        mock_index.chunks = []
        return mock_index

    def test_symmetric_tools_false_by_default(self):
        from src.rag_baseline import RAGAgent
        agent = RAGAgent(
            rag_index=self._make_mock_rag_index(),
            gemini_client=MagicMock(),
        )
        self.assertFalse(agent.symmetric_tools)

    def test_symmetric_tools_false_without_repo_dir(self):
        from src.rag_baseline import RAGAgent
        agent = RAGAgent(
            rag_index=self._make_mock_rag_index(),
            gemini_client=MagicMock(),
            symmetric_tools=True,  # requested but no repo_dir
            repo_dir=None,
        )
        # Should be disabled gracefully when repo_dir is not provided
        self.assertFalse(agent.symmetric_tools)

    def test_symmetric_tools_true_when_repo_dir_provided(self):
        from src.rag_baseline import RAGAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            agent = RAGAgent(
                rag_index=self._make_mock_rag_index(),
                gemini_client=MagicMock(),
                symmetric_tools=True,
                repo_dir=tmpdir,
            )
        self.assertTrue(agent.symmetric_tools)

    def test_symmetric_tools_false_explicit_false(self):
        from src.rag_baseline import RAGAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            agent = RAGAgent(
                rag_index=self._make_mock_rag_index(),
                gemini_client=MagicMock(),
                symmetric_tools=False,
                repo_dir=tmpdir,  # repo_dir provided but tools disabled
            )
        self.assertFalse(agent.symmetric_tools)


class HandleGetFileContentsTests(unittest.TestCase):
    """Test the _handle_get_file_contents helper method."""

    def _make_agent_with_repo(self, tmpdir: str, max_file_chars: int = 200000):
        from src.rag_baseline import RAGAgent
        mock_index = MagicMock()
        mock_index.chunks = []
        return RAGAgent(
            rag_index=mock_index,
            gemini_client=MagicMock(),
            symmetric_tools=True,
            repo_dir=tmpdir,
            max_file_chars=max_file_chars,
        )

    def test_returns_file_contents_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "myfile.py").write_text("def hello(): return 'hi'\n", encoding="utf-8")
            agent = self._make_agent_with_repo(tmpdir)

            result = agent._handle_get_file_contents("myfile.py", observed_files=set())

        self.assertIn("def hello", result)
        self.assertIn("return 'hi'", result)

    def test_returns_error_string_when_file_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self._make_agent_with_repo(tmpdir)
            result = agent._handle_get_file_contents("nonexistent.py", observed_files=set())

        self.assertIsInstance(result, str)
        self.assertIn("Error", result)
        # Must not raise

    def test_clips_to_max_file_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            large_content = "x" * 1000
            (Path(tmpdir) / "large.py").write_text(large_content, encoding="utf-8")
            agent = self._make_agent_with_repo(tmpdir, max_file_chars=100)

            result = agent._handle_get_file_contents("large.py", observed_files=set())

        # Content should be clipped to max_file_chars
        self.assertLessEqual(len(result), 200)  # clip + truncation marker
        self.assertIn("truncated", result.lower())

    def test_adds_file_to_observed_files(self):
        """get_file_contents should add the path to observed_files so the agent can return it."""
        from src.rag_baseline import RAGAgent
        mock_index = MagicMock()
        mock_index.chunks = [{"file": "src/app.py"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir()
            (Path(tmpdir) / "src" / "app.py").write_text("# app\n", encoding="utf-8")

            agent = RAGAgent(
                rag_index=mock_index,
                gemini_client=MagicMock(),
                symmetric_tools=True,
                repo_dir=tmpdir,
            )

            observed = set()
            agent._handle_get_file_contents("src/app.py", observed_files=observed)

        # The file should be in observed_files after the call
        self.assertTrue(
            any("app" in f for f in observed),
            f"Expected src/app.py in observed_files, got: {observed}",
        )

    def test_returns_error_string_for_path_outside_repo(self):
        """Path traversal attempt should return error, not read outside repo_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self._make_agent_with_repo(tmpdir)
            # Attempt path traversal
            result = agent._handle_get_file_contents("../../etc/passwd", observed_files=set())

        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


if __name__ == "__main__":
    unittest.main()
