"""Tests for BM25 retrieval baseline (src/bm25_baseline.py).

TDD: these tests are written before the implementation.

Covers:
  - build on temp dir with 3 files → query returns most relevant file first
  - embedding_tokens_estimate is always 0
  - empty repo returns empty list, no crash
  - include_prefixes correctly filters files
  - duplicate-file deduplication in results (file-level index → not applicable, but
    verified via top-k > n_files returning at most n_files)
  - find_relevant_files returns (list[str], dict) matching RawRAG interface
"""

import tempfile
import unittest
from pathlib import Path


class BM25IndexBuildTests(unittest.TestCase):
    def _make_repo(self, tmpdir: str) -> Path:
        """Create a small fake Python repo with 3 files."""
        repo = Path(tmpdir)
        src = repo / "src"
        src.mkdir()

        # File 1: about authentication
        (src / "auth.py").write_text(
            "def authenticate(user, password):\n"
            "    '''Authenticate a user with password validation.'''\n"
            "    return check_credentials(user, password)\n\n"
            "def check_credentials(user, password):\n"
            "    return True\n",
            encoding="utf-8",
        )

        # File 2: about database
        (src / "database.py").write_text(
            "def connect_database(host, port):\n"
            "    '''Connect to the database server.'''\n"
            "    return Connection(host, port)\n\n"
            "class Connection:\n"
            "    def query(self, sql):\n"
            "        return []\n",
            encoding="utf-8",
        )

        # File 3: about rendering/templates
        (src / "render.py").write_text(
            "def render_template(template_name, context):\n"
            "    '''Render an HTML template with context variables.'''\n"
            "    return template_name.format(**context)\n",
            encoding="utf-8",
        )

        return repo

    def test_query_returns_most_relevant_file_first(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            results = idx.query("authenticate user password login", top_k=3)

        self.assertTrue(len(results) > 0, "Expected at least one result")
        # auth.py should score highest for authentication query
        self.assertIn("auth", results[0], f"Expected auth.py first, got: {results}")

    def test_query_database_file_ranks_highest_for_database_query(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            results = idx.query("database connect host port SQL query", top_k=3)

        self.assertTrue(len(results) > 0)
        self.assertIn("database", results[0], f"Expected database.py first, got: {results}")

    def test_embedding_tokens_estimate_is_always_zero(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_repo(tmpdir)
            idx = BM25Index(str(repo))
            # Before build
            self.assertEqual(idx.embedding_tokens_estimate, 0)
            idx.build()
            # After build
            self.assertEqual(idx.embedding_tokens_estimate, 0)

    def test_empty_repo_returns_empty_list(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            idx = BM25Index(tmpdir)
            idx.build()
            results = idx.query("anything at all", top_k=10)

        self.assertEqual(results, [])

    def test_include_prefixes_filters_files(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            # Files in src/ (included)
            src = repo / "src"
            src.mkdir()
            (src / "main.py").write_text("def main(): pass\n", encoding="utf-8")

            # Files in tests/ (excluded)
            tests = repo / "tests"
            tests.mkdir()
            (tests / "test_main.py").write_text(
                "def test_main(): assert main() is None\n", encoding="utf-8"
            )

            idx = BM25Index(str(repo), include_prefixes=("src/",))
            idx.build()
            results = idx.query("main function", top_k=10)

        # Only src/main.py should be indexed
        for path in results:
            self.assertFalse(
                path.startswith("tests/") or "test_main" in path,
                f"Expected no test files in results, got: {path}",
            )
        self.assertTrue(any("main" in path for path in results), f"Expected main.py in results: {results}")

    def test_top_k_limits_results(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            # Repo has 3 files; top_k=2 should return at most 2
            results = idx.query("python code", top_k=2)

        self.assertLessEqual(len(results), 2)

    def test_results_contain_no_duplicates(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            results = idx.query("function def class", top_k=10)

        self.assertEqual(len(results), len(set(results)), f"Duplicates found: {results}")

    def test_only_py_files_are_indexed(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "main.py").write_text("def hello(): return 'hello'\n", encoding="utf-8")
            (repo / "README.md").write_text("hello is a function that returns hello\n", encoding="utf-8")
            (repo / "config.yaml").write_text("hello: world\n", encoding="utf-8")

            idx = BM25Index(str(repo))
            idx.build()
            results = idx.query("hello function", top_k=10)

        for path in results:
            self.assertTrue(path.endswith(".py"), f"Non-.py file in results: {path}")

    def test_query_with_no_matching_tokens_returns_empty_or_all(self):
        """BM25 with no overlap returns scores, not an error."""
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "file.py").write_text("def foo(): pass\n", encoding="utf-8")
            idx = BM25Index(str(repo))
            idx.build()
            # Completely unrelated query — BM25 should handle this gracefully
            results = idx.query("zzzzquux_unmatched_token", top_k=5)

        # Should not crash; may return empty (all zero scores) or all files
        self.assertIsInstance(results, list)


class BM25FindRelevantFilesTests(unittest.TestCase):
    """Test the find_relevant_files interface matches RawRAG's contract."""

    def _make_simple_repo(self, tmpdir: str) -> Path:
        repo = Path(tmpdir)
        (repo / "alpha.py").write_text(
            "def alpha_function(): return 'alpha'\n", encoding="utf-8"
        )
        (repo / "beta.py").write_text(
            "def beta_function(): return 'beta'\n", encoding="utf-8"
        )
        return repo

    def test_find_relevant_files_returns_tuple_of_list_and_dict(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_simple_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            result = idx.find_relevant_files("alpha function", top_k=5)

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        files, token_usage = result
        self.assertIsInstance(files, list)
        self.assertIsInstance(token_usage, dict)

    def test_find_relevant_files_token_usage_has_zero_costs(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_simple_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            _, token_usage = idx.find_relevant_files("alpha function", top_k=5)

        # BM25 has zero LLM cost
        self.assertEqual(token_usage.get("total_tokens", 0), 0)
        self.assertEqual(token_usage.get("query_embedding_tokens", 0), 0)

    def test_find_relevant_files_returns_alpha_first(self):
        from src.bm25_baseline import BM25Index

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._make_simple_repo(tmpdir)
            idx = BM25Index(str(repo))
            idx.build()
            files, _ = idx.find_relevant_files("alpha function return", top_k=5)

        self.assertTrue(len(files) > 0)
        self.assertIn("alpha", files[0])


if __name__ == "__main__":
    unittest.main()
