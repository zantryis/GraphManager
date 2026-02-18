"""Tests for PatchAgent: patch extraction, context building, token accounting."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.patch_agent import PatchAgent, build_patch_prompt, extract_patch


class ExtractPatchTests(unittest.TestCase):
    def test_extracts_valid_patch(self):
        response = """
Here is the fix:

<patch>
--- a/src/module.py
+++ b/src/module.py
@@ -1,3 +1,3 @@
 def foo():
-    return 1
+    return 2
</patch>
"""
        result = extract_patch(response)
        self.assertIsNotNone(result)
        self.assertIn("--- a/src/module.py", result)
        self.assertIn("+    return 2", result)

    def test_returns_none_for_cannot_patch(self):
        response = "<patch>CANNOT_PATCH</patch>"
        self.assertIsNone(extract_patch(response))

    def test_returns_none_when_no_patch_tag(self):
        response = "I think you should change the function but I cannot show the diff."
        self.assertIsNone(extract_patch(response))

    def test_returns_none_for_empty_patch_tag(self):
        response = "<patch>   </patch>"
        self.assertIsNone(extract_patch(response))

    def test_case_insensitive_cannot_patch(self):
        response = "<patch>cannot_patch</patch>"
        self.assertIsNone(extract_patch(response))

    def test_multiline_patch_preserved(self):
        diff = (
            "--- a/a.py\n+++ b/a.py\n"
            "@@ -1,4 +1,4 @@\n"
            " line1\n-line2\n+line2_fixed\n line3\n"
        )
        response = f"<patch>\n{diff}\n</patch>"
        result = extract_patch(response)
        self.assertEqual(result, diff.strip())

    def test_extracts_raw_unified_diff_without_patch_tags(self):
        response = (
            "Here is the patch:\n\n"
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,3 +1,3 @@\n"
            " def f():\n"
            "-    return 1\n"
            "+    return 2\n"
        )
        result = extract_patch(response)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("--- a/src/a.py"))
        self.assertIn("+    return 2", result)

    def test_extracts_raw_diff_inside_markdown_fence(self):
        response = (
            "```diff\n"
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,3 +1,3 @@\n"
            " def f():\n"
            "-    return 1\n"
            "+    return 2\n"
            "```\n"
        )
        result = extract_patch(response)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("--- a/src/a.py"))


class BuildPatchPromptTests(unittest.TestCase):
    def test_includes_issue_and_file_contents(self):
        prompt = build_patch_prompt(
            issue_text="Bug: foo returns wrong value",
            file_contents={"src/foo.py": "def foo():\n    return 1\n"},
        )
        self.assertIn("Bug: foo returns wrong value", prompt)
        self.assertIn("src/foo.py", prompt)
        self.assertIn("def foo():", prompt)

    def test_includes_all_files(self):
        prompt = build_patch_prompt(
            issue_text="issue",
            file_contents={
                "src/a.py": "content_a",
                "src/b.py": "content_b",
            },
        )
        self.assertIn("src/a.py", prompt)
        self.assertIn("src/b.py", prompt)
        self.assertIn("content_a", prompt)
        self.assertIn("content_b", prompt)


class PatchAgentFileReadingTests(unittest.TestCase):
    def test_reads_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "src").mkdir()
            (repo / "src" / "module.py").write_text("def foo(): pass\n")

            agent = PatchAgent(str(repo), client=MagicMock())
            contents = agent._build_file_contents(["src/module.py"])

        self.assertIn("src/module.py", contents)
        self.assertIn("def foo()", contents["src/module.py"])

    def test_skips_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = PatchAgent(tmpdir, client=MagicMock())
            contents = agent._build_file_contents(["does/not/exist.py"])
        self.assertEqual(contents, {})

    def test_truncates_large_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            large = "x" * 20000
            (repo / "big.py").write_text(large)

            agent = PatchAgent(str(repo), client=MagicMock(), max_file_chars=1000)
            contents = agent._build_file_contents(["big.py"])

        self.assertIn("big.py", contents)
        self.assertLessEqual(len(contents["big.py"]), 1100)  # allow truncation marker
        self.assertIn("truncated", contents["big.py"])

    def test_returns_no_patch_when_no_readable_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = PatchAgent(tmpdir, client=MagicMock())
            patch_text, tokens = agent.generate_patch("issue", ["missing.py"])

        self.assertIsNone(patch_text)
        self.assertEqual(tokens["stop_reason"], "no_readable_files")
        self.assertEqual(tokens["total_tokens"], 0)


class PatchAgentGenerationTests(unittest.TestCase):
    def _make_mock_response(self, text: str, prompt_tokens: int = 100, candidate_tokens: int = 50):
        usage = MagicMock()
        usage.prompt_token_count = prompt_tokens
        usage.candidates_token_count = candidate_tokens

        part = MagicMock()
        part.text = text

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content
        candidate.finish_reason = "STOP"

        response = MagicMock()
        response.usage_metadata = usage
        response.candidates = [candidate]
        return response

    def test_returns_patch_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "fix.py").write_text("def f(): return 1\n")

            client = MagicMock()
            diff = "--- a/fix.py\n+++ b/fix.py\n@@ -1 +1 @@\n-def f(): return 1\n+def f(): return 2\n"
            client.models.generate_content.return_value = self._make_mock_response(
                f"<patch>\n{diff}\n</patch>", prompt_tokens=200, candidate_tokens=80
            )

            agent = PatchAgent(str(repo), client=client)
            result_patch, tokens = agent.generate_patch("fix return value", ["fix.py"])

        self.assertIsNotNone(result_patch)
        self.assertIn("--- a/fix.py", result_patch)
        self.assertEqual(tokens["total_tokens"], 280)
        self.assertEqual(tokens["turns_used"], 1)
        self.assertEqual(tokens["files_provided"], 1)

    def test_retries_when_no_patch_tag_on_first_turn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "fix.py").write_text("def f(): return 1\n")

            client = MagicMock()
            diff = "--- a/fix.py\n+++ b/fix.py\n@@ -1 +1 @@\n-def f(): return 1\n+def f(): return 2\n"
            client.models.generate_content.side_effect = [
                self._make_mock_response("No patch here"),
                self._make_mock_response(f"<patch>\n{diff}\n</patch>"),
            ]

            agent = PatchAgent(str(repo), client=client)
            result_patch, tokens = agent.generate_patch("fix return", ["fix.py"], max_turns=3)

        self.assertIsNotNone(result_patch)
        self.assertEqual(tokens["turns_used"], 2)

    def test_returns_none_after_max_turns_without_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "fix.py").write_text("code\n")

            client = MagicMock()
            client.models.generate_content.return_value = self._make_mock_response("no patch")

            agent = PatchAgent(str(repo), client=client)
            result_patch, tokens = agent.generate_patch("issue", ["fix.py"], max_turns=2)

        self.assertIsNone(result_patch)
        self.assertEqual(tokens["turns_used"], 2)
        self.assertIn("error", tokens)

    def test_handles_api_error_gracefully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "fix.py").write_text("code\n")

            client = MagicMock()
            client.models.generate_content.side_effect = RuntimeError("quota exceeded")

            agent = PatchAgent(str(repo), client=client)
            result_patch, tokens = agent.generate_patch("issue", ["fix.py"])

        self.assertIsNone(result_patch)
        self.assertIn("api_error", tokens["stop_reason"])
        self.assertIn("quota exceeded", tokens["error"])


if __name__ == "__main__":
    unittest.main()
