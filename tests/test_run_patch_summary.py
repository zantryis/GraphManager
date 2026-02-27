"""Regression tests for run_patch.py patch_summary.json structure.

Full integration tests for run_patch_stage1() would require mocking the entire
retrieval and patching pipeline. These source-structure tests guard against
required fields being silently dropped from the summary dict.
"""
import pathlib
import re
import unittest


class PatchSummaryStructureTests(unittest.TestCase):
    def _get_stage1_summary_dict_text(self) -> str:
        """Extract the Stage-1 summary dict literal from run_patch.py source."""
        source = (
            pathlib.Path(__file__).parent.parent / "run_patch.py"
        ).read_text(encoding="utf-8")
        # The Stage-1 summary dict starts with "run_id" / "dataset_name" / "n_instances"
        # and ends just before "**cost_fields".  Use DOTALL to span multiple lines.
        match = re.search(
            r'summary\s*=\s*\{.*?"run_id".*?"dataset_name".*?"n_instances".*?\*\*cost_fields',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "Could not locate the Stage-1 summary dict in run_patch.py — "
            "did the dict structure change?",
        )
        return match.group(0)

    def test_stage1_summary_dict_includes_repo_name(self):
        """run_patch_stage1 summary dict must include 'repo_name'.

        Stage-1-only runs (--evaluate-mode stage1_only) previously omitted this
        field, causing aggregate_v2_results.py to discard every patching run.
        """
        dict_text = self._get_stage1_summary_dict_text()
        self.assertIn(
            '"repo_name"',
            dict_text,
            "patch_summary.json missing 'repo_name': add it to the Stage-1 summary dict "
            "in run_patch_stage1()",
        )

    def test_stage1_summary_dict_includes_retrieval_method(self):
        """Sanity-check that retrieval_method is present (existing field, must not regress)."""
        dict_text = self._get_stage1_summary_dict_text()
        self.assertIn('"retrieval_method"', dict_text)


if __name__ == "__main__":
    unittest.main()
