import unittest
from unittest.mock import patch

from src.datasets import SWEPolyBenchIssueAdapter, SWEBenchIssueAdapter, build_issue_adapter
from src.evaluation import group_issues_by_base_commit


class DatasetAdapterTests(unittest.TestCase):
    @patch("src.datasets.adapters.load_dataset")
    def test_swe_bench_adapter_normalizes_schema_and_gold_files(self, mock_load_dataset):
        split_rows = {
            "test": [
                {
                    "instance_id": "i1",
                    "repo": "org/repo",
                    "problem_statement": "Bug in path handling",
                    "patch": "diff --git a/a.py b/a.py\n@@\n-d\n+e\n",
                    "base_commit": "abc123",
                },
            ],
            "train": [
                {
                    "instance_id": "i2",
                    "repo": "org/repo",
                    "problem_statement": "Another issue",
                    "patch": "",
                    "base_commit": "def456",
                    "gold_files": ["src/x.py", "./src/x.py", "src/y.py"],
                },
                {
                    "instance_id": "i1",
                    "repo": "org/repo",
                    "problem_statement": "duplicate row should be deduped",
                    "patch": "diff --git a/a.py b/a.py\n",
                    "base_commit": "abc123",
                },
            ],
            "dev": [],
        }
        mock_load_dataset.side_effect = lambda dataset_name, split: split_rows[split]

        adapter = SWEBenchIssueAdapter(dataset_name="SWE-bench/SWE-bench")
        issues = adapter.load_issues(repo="org/repo", n=10)

        self.assertEqual([issue["instance_id"] for issue in issues], ["i1", "i2"])
        self.assertEqual(issues[0]["repo"], "org/repo")
        self.assertEqual(issues[0]["base_commit"], "abc123")
        self.assertEqual(issues[0]["gold_files"], ["a.py"])
        self.assertEqual(issues[1]["gold_files"], ["src/x.py", "src/y.py"])

    @patch("src.datasets.adapters.load_dataset")
    def test_swe_polybench_adapter_normalizes_retrieval_schema(self, mock_load_dataset):
        split_rows = {
            "test": [
                {
                    "id": "pb-1",
                    "repo": "org/repo",
                    "prompt": "Find files",
                    "base_sha": "c0ffee",
                    "gold_files": "src/a.py\nsrc/b.py",
                },
                {
                    "id": "pb-2",
                    "repo": "org/other",
                    "prompt": "ignored",
                    "base_sha": "deadbeef",
                    "gold_files": ["x.py"],
                },
            ],
            "validation": [],
            "dev": [],
            "train": [],
        }
        mock_load_dataset.side_effect = lambda dataset_name, split: split_rows[split]

        adapter = SWEPolyBenchIssueAdapter(dataset_name="AmazonScience/SWE-PolyBench_Verified")
        issues = adapter.load_issues(repo="org/repo", n=5)

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["instance_id"], "pb-1")
        self.assertEqual(issue["repo"], "org/repo")
        self.assertEqual(issue["base_commit"], "c0ffee")
        self.assertEqual(issue["gold_files"], ["src/a.py", "src/b.py"])

    def test_build_issue_adapter_selects_family(self):
        swe_adapter = build_issue_adapter(
            task_family="swe-bench",
            dataset_name="SWE-bench/SWE-bench",
        )
        poly_adapter = build_issue_adapter(
            task_family="swe-polybench",
            dataset_name="AmazonScience/SWE-PolyBench_Verified",
        )
        self.assertIsInstance(swe_adapter, SWEBenchIssueAdapter)
        self.assertIsInstance(poly_adapter, SWEPolyBenchIssueAdapter)

    def test_grouping_regression_with_normalized_base_commit(self):
        issues = [
            {"instance_id": "i1", "base_commit": "abc"},
            {"instance_id": "i2", "base_commit": "def"},
            {"instance_id": "i3", "base_commit": "abc"},
        ]
        grouped = group_issues_by_base_commit(issues)
        self.assertEqual(
            [(commit, [item["instance_id"] for item in bucket]) for commit, bucket in grouped],
            [("abc", ["i1", "i3"]), ("def", ["i2"])],
        )

    @patch("src.datasets.adapters.load_dataset")
    def test_swe_bench_adapter_supports_manifest_instance_order(self, mock_load_dataset):
        split_rows = {
            "test": [
                {
                    "instance_id": "i1",
                    "repo": "org/repo",
                    "problem_statement": "Issue 1",
                    "patch": "diff --git a/a.py b/a.py\n",
                    "base_commit": "abc123",
                },
                {
                    "instance_id": "i2",
                    "repo": "org/repo",
                    "problem_statement": "Issue 2",
                    "patch": "diff --git a/b.py b/b.py\n",
                    "base_commit": "def456",
                },
                {
                    "instance_id": "i3",
                    "repo": "org/repo",
                    "problem_statement": "Issue 3",
                    "patch": "diff --git a/c.py b/c.py\n",
                    "base_commit": "123456",
                },
            ],
            "train": [],
            "dev": [],
        }
        mock_load_dataset.side_effect = lambda dataset_name, split: split_rows[split]

        adapter = SWEBenchIssueAdapter(dataset_name="SWE-bench/SWE-bench")
        issues = adapter.load_issues(
            repo="org/repo",
            n=10,
            instance_ids=["i3", "i1", "missing", "i3"],
        )

        self.assertEqual(
            [issue["instance_id"] for issue in issues],
            ["i3", "i1"],
        )


if __name__ == "__main__":
    unittest.main()
