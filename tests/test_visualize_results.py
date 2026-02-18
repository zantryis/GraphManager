import json
import tempfile
import unittest
from pathlib import Path

from visualize_results import (
    build_global_method_points,
    build_html,
    load_all_runs,
    load_repeat_set,
    load_run,
)


class VisualizeResultsTests(unittest.TestCase):
    def test_load_run_preserves_amortization_and_track_meta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "20260211_999999"
            run_dir.mkdir(parents=True)
            summary = {
                "_meta": {
                    "run_id": "20260211_999999",
                    "repo_name": "org/repo",
                    "evaluation_track": "same_snapshot_amortized",
                    "snapshot_commit": "feedbeef",
                },
                "_amortization": {
                    "track_name": "same_snapshot_amortized",
                    "commit_repeat_ratio": 0.8,
                    "cache_hit_rate": 0.7,
                },
                "gm_progressive": {"mean_f1": 0.7},
                "gm_baseline": {"mean_f1": 0.6},
                "rag_progressive": {"mean_f1": 0.5},
                "rag_baseline": {"mean_f1": 0.55},
                "raw_rag_function": {"mean_f1": 0.3},
                "raw_rag_fixed": {"mean_f1": 0.25},
            }
            (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (run_dir / "detailed_results.json").write_text("[]", encoding="utf-8")

            run = load_run(run_dir)

        self.assertIsNotNone(run)
        self.assertEqual(run["meta"]["evaluation_track"], "same_snapshot_amortized")
        self.assertEqual(run["meta"]["snapshot_commit"], "feedbeef")
        self.assertEqual(run["amortization"]["cache_hit_rate"], 0.7)

    def test_load_repeat_set_preserves_pairwise_and_gates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "repeat.json"
            payload = {
                "_meta": {"repo_name": "org/repo"},
                "n_runs": 3,
                "run_ids": ["r1", "r2", "r3"],
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.7, "std": 0.1}},
                    "gm_baseline": {"mean_f1": {"mean": 0.6, "std": 0.1}},
                    "rag_progressive": {"mean_f1": {"mean": 0.65, "std": 0.1}},
                    "rag_baseline": {"mean_f1": {"mean": 0.66, "std": 0.1}},
                    "raw_rag_function": {"mean_f1": {"mean": 0.3, "std": 0.1}},
                    "raw_rag_fixed": {"mean_f1": {"mean": 0.2, "std": 0.1}},
                },
                "pairwise_deltas": {
                    "gm_progressive__minus__rag_progressive__mean_f1": {
                        "mean_delta": 0.05,
                        "bootstrap_ci_95": [0.01, 0.09],
                    }
                },
                "gates": {"min_repeats_met": True, "ci_ready": True},
                "_amortization": {
                    "track_name": "same_snapshot_amortized",
                    "n_issues": 8,
                    "n_unique_commits": 1,
                    "commit_repeat_ratio": 0.875,
                    "cache_hit_rate": 0.875,
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            run = load_repeat_set(path)

        self.assertIsNotNone(run)
        self.assertIn("pairwise_deltas", run)
        self.assertIn("gates", run)
        self.assertTrue(run["gates"]["ci_ready"])
        self.assertAlmostEqual(run["amortization"]["commit_repeat_ratio"], 0.875)

    def test_build_html_contains_cross_task_frontier_views(self):
        runs = [
            {
                "run_id": "repeat_x",
                "meta": {
                    "run_id": "repeat_x",
                    "repo_name": "org/repo",
                    "run_type": "repeat_aggregate",
                    "evaluation_track": "strict_commit_fidelity",
                },
                "summary": {
                    "gm_deterministic": {"mean_f1": 0.72},
                    "gm_progressive": {"mean_f1": 0.7},
                    "gm_baseline": {"mean_f1": 0.6},
                    "rag_progressive": {"mean_f1": 0.65},
                    "rag_baseline": {"mean_f1": 0.66},
                    "raw_rag_function": {"mean_f1": 0.3},
                    "raw_rag_fixed": {"mean_f1": 0.2},
                },
                "issues": [],
                "component_run_ids": ["r1", "r2", "r3"],
                "pairwise_deltas": {
                    "gm_progressive__minus__rag_progressive__mean_f1": {
                        "mean_delta": 0.05,
                        "bootstrap_ci_95": [0.01, 0.09],
                    }
                },
                "gates": {"min_repeats_met": True, "ci_ready": True},
                "amortization": {
                    "track_name": "strict_commit_fidelity",
                    "commit_repeat_ratio": 0.4,
                    "cache_hit_rate": 0.3,
                },
            }
        ]

        html = build_html(runs, config=None)
        self.assertIn("GM (deterministic)", html)
        self.assertIn("Global Cost-Quality Frontier", html)
        self.assertIn("Tradeoff Outliers", html)
        self.assertIn("Regime Shift Detector", html)
        self.assertIn("benchmarkFilter", html)
        self.assertIn("domainFilter", html)

    def test_build_global_method_points_marks_pareto_frontier(self):
        runs = [
            {
                "run_id": "r1",
                "meta": {
                    "repo_name": "org/repo",
                    "dataset_name": "dataset-x",
                    "domain": "library",
                    "evaluation_track": "strict_commit_fidelity",
                },
                "summary": {
                    "gm_progressive": {
                        "mean_f1": 0.70,
                        "avg_total_cost_tokens_per_issue_amortized_setup": 1000,
                    },
                    "rag_progressive": {
                        "mean_f1": 0.60,
                        "avg_total_cost_tokens_per_issue_amortized_setup": 1200,
                    },
                },
            }
        ]

        points = build_global_method_points(runs)
        points_by_method = {point["method"]: point for point in points}

        self.assertTrue(points_by_method["gm_progressive"]["is_pareto_frontier"])
        self.assertFalse(points_by_method["rag_progressive"]["is_pareto_frontier"])

    def test_load_all_runs_excludes_stale_legacy_runs_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            repeat_dir = results_dir / "repeat_sets"
            repeat_dir.mkdir(parents=True)

            stale_payload = {
                "_meta": {
                    "created_at": "2026-02-10 11:00:00",
                    "repo_name": "org/repo",
                    "issue_set_id": "issues_old",
                },
                "n_runs": 3,
                "run_ids": ["s1", "s2", "s3"],
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.5, "std": 0.1}},
                    "gm_baseline": {"mean_f1": {"mean": 0.4, "std": 0.1}},
                    "rag_progressive": {"mean_f1": {"mean": 0.45, "std": 0.1}},
                    "rag_baseline": {"mean_f1": {"mean": 0.43, "std": 0.1}},
                    "raw_rag_function": {"mean_f1": {"mean": 0.2, "std": 0.1}},
                    "raw_rag_fixed": {"mean_f1": {"mean": 0.2, "std": 0.1}},
                },
            }
            fresh_payload = {
                "_meta": {
                    "created_at": "2026-02-11 11:00:00",
                    "repo_name": "org/repo",
                    "issue_set_id": "issues_new",
                    "evaluation_track": "strict_commit_fidelity",
                },
                "_amortization": {"track_name": "strict_commit_fidelity"},
                "n_runs": 3,
                "run_ids": ["r1", "r2", "r3"],
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.6, "std": 0.1}},
                    "gm_baseline": {"mean_f1": {"mean": 0.5, "std": 0.1}},
                    "rag_progressive": {"mean_f1": {"mean": 0.55, "std": 0.1}},
                    "rag_baseline": {"mean_f1": {"mean": 0.54, "std": 0.1}},
                    "raw_rag_function": {"mean_f1": {"mean": 0.25, "std": 0.1}},
                    "raw_rag_fixed": {"mean_f1": {"mean": 0.24, "std": 0.1}},
                },
            }
            (repeat_dir / "stale.json").write_text(json.dumps(stale_payload), encoding="utf-8")
            (repeat_dir / "fresh.json").write_text(json.dumps(fresh_payload), encoding="utf-8")

            visible = load_all_runs(results_dir)
            all_runs = load_all_runs(results_dir, include_stale=True)

        self.assertEqual(len(visible), 1)
        self.assertEqual(len(all_runs), 2)
        self.assertEqual(visible[0]["meta"]["evaluation_track"], "strict_commit_fidelity")

    def test_load_repeat_set_returns_none_for_invalid_cell(self):
        """Repeat sets with valid:false must be silently skipped by the loader."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            payload = {
                "valid": False,
                "invalid_reason": "empty_graph_and_rag_index_source_prefix_mismatch",
                "_meta": {"repo_name": "langchain-ai/langchain"},
                "n_runs": 3,
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.0, "std": 0.0}},
                    "rag_progressive": {"mean_f1": {"mean": 0.0, "std": 0.0}},
                },
                "gates": {"ci_ready": True},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = load_repeat_set(path)
        self.assertIsNone(result)

    def test_load_all_runs_keeps_only_latest_superseded_run_per_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            repeat_dir = results_dir / "repeat_sets"
            repeat_dir.mkdir(parents=True)

            old_payload = {
                "_meta": {
                    "created_at": "2026-02-11 10:00:00",
                    "repo_name": "org/repo",
                    "issue_set_id": "issues_x",
                    "dataset_name": "dataset",
                    "evaluation_track": "strict_commit_fidelity",
                    "snapshot_commit": None,
                    "n_issues_evaluated": 8,
                },
                "_amortization": {"track_name": "strict_commit_fidelity"},
                "n_runs": 3,
                "run_ids": ["o1", "o2", "o3"],
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.50, "std": 0.1}},
                    "gm_baseline": {"mean_f1": {"mean": 0.40, "std": 0.1}},
                    "rag_progressive": {"mean_f1": {"mean": 0.45, "std": 0.1}},
                    "rag_baseline": {"mean_f1": {"mean": 0.44, "std": 0.1}},
                    "raw_rag_function": {"mean_f1": {"mean": 0.20, "std": 0.1}},
                    "raw_rag_fixed": {"mean_f1": {"mean": 0.20, "std": 0.1}},
                },
            }
            new_payload = {
                "_meta": {
                    "created_at": "2026-02-11 12:00:00",
                    "repo_name": "org/repo",
                    "issue_set_id": "issues_x",
                    "dataset_name": "dataset",
                    "evaluation_track": "strict_commit_fidelity",
                    "snapshot_commit": None,
                    "n_issues_evaluated": 8,
                },
                "_amortization": {"track_name": "strict_commit_fidelity"},
                "n_runs": 3,
                "run_ids": ["n1", "n2", "n3"],
                "methods": {
                    "gm_progressive": {"mean_f1": {"mean": 0.60, "std": 0.1}},
                    "gm_baseline": {"mean_f1": {"mean": 0.50, "std": 0.1}},
                    "rag_progressive": {"mean_f1": {"mean": 0.55, "std": 0.1}},
                    "rag_baseline": {"mean_f1": {"mean": 0.54, "std": 0.1}},
                    "raw_rag_function": {"mean_f1": {"mean": 0.25, "std": 0.1}},
                    "raw_rag_fixed": {"mean_f1": {"mean": 0.24, "std": 0.1}},
                },
            }
            (repeat_dir / "older.json").write_text(json.dumps(old_payload), encoding="utf-8")
            (repeat_dir / "newer.json").write_text(json.dumps(new_payload), encoding="utf-8")

            runs = load_all_runs(results_dir)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["summary"]["gm_progressive"]["mean_f1"], 0.6)


if __name__ == "__main__":
    unittest.main()
