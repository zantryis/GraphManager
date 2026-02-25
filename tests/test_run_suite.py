"""Tests for run_suite.py parallel execution helpers."""

import unittest

from run_suite import _group_by_repo


class TestGroupByRepo(unittest.TestCase):
    """Test _group_by_repo groups experiments correctly."""

    def test_single_repo(self):
        experiments = [
            (0, {"repo": "pallets/flask", "n_issues": 10}),
            (1, {"repo": "pallets/flask", "n_issues": 5}),
        ]
        groups = _group_by_repo(experiments)
        self.assertEqual(len(groups), 1)
        self.assertIn("pallets/flask", groups)
        self.assertEqual(len(groups["pallets/flask"]), 2)

    def test_multiple_repos(self):
        experiments = [
            (0, {"repo": "pallets/flask", "n_issues": 10}),
            (1, {"repo": "django/django", "n_issues": 10}),
            (2, {"repo": "pallets/flask", "n_issues": 5}),
            (3, {"repo": "sympy/sympy", "n_issues": 10}),
        ]
        groups = _group_by_repo(experiments)
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(groups["pallets/flask"]), 2)
        self.assertEqual(len(groups["django/django"]), 1)
        self.assertEqual(len(groups["sympy/sympy"]), 1)

    def test_preserves_order_within_repo(self):
        experiments = [
            (0, {"repo": "a/a", "n_issues": 1}),
            (1, {"repo": "a/a", "n_issues": 2}),
            (2, {"repo": "a/a", "n_issues": 3}),
        ]
        groups = _group_by_repo(experiments)
        indices = [idx for idx, _ in groups["a/a"]]
        self.assertEqual(indices, [0, 1, 2])

    def test_empty(self):
        groups = _group_by_repo([])
        self.assertEqual(len(groups), 0)


if __name__ == "__main__":
    unittest.main()
