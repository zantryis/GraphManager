import json
import unittest
import tempfile
from pathlib import Path

from run_suite import resolve_experiment


class SuiteConfigTests(unittest.TestCase):
    def test_resolve_experiment_includes_track_and_snapshot_defaults(self):
        defaults = {
            "n_issues": 5,
            "manager_max_turns": 3,
            "rag_max_turns": 4,
            "evaluation_track": "same_snapshot_amortized",
            "snapshot_commit": "feedbeef",
        }
        exp = {"repo": "org/repo"}
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["evaluation_track"], "same_snapshot_amortized")
        self.assertEqual(resolved["snapshot_commit"], "feedbeef")

    def test_resolve_experiment_allows_explicit_track_override(self):
        defaults = {"evaluation_track": "strict_commit_fidelity"}
        exp = {
            "repo": "org/repo",
            "evaluation_track": "same_snapshot_amortized",
            "snapshot_commit": "cafebabe",
        }
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["evaluation_track"], "same_snapshot_amortized")
        self.assertEqual(resolved["snapshot_commit"], "cafebabe")

    def test_resolve_experiment_includes_dataset_family_defaults(self):
        defaults = {
            "task_family": "swe-polybench",
            "dataset_name": "AmazonScience/SWE-PolyBench_Verified",
        }
        exp = {"repo": "yt-dlp/yt-dlp"}
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["task_family"], "swe-polybench")
        self.assertEqual(
            resolved["dataset_name"],
            "AmazonScience/SWE-PolyBench_Verified",
        )

    def test_resolve_experiment_allows_dataset_family_override(self):
        defaults = {
            "task_family": "swe-bench",
            "dataset_name": "SWE-bench/SWE-bench",
        }
        exp = {
            "repo": "yt-dlp/yt-dlp",
            "task_family": "swe-polybench",
            "dataset_name": "AmazonScience/SWE-PolyBench_Verified",
        }
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["task_family"], "swe-polybench")
        self.assertEqual(
            resolved["dataset_name"],
            "AmazonScience/SWE-PolyBench_Verified",
        )

    def test_resolve_experiment_includes_manifest_metadata_and_repeats(self):
        defaults = {
            "repeats": 3,
            "issue_set_id": "issues_default_v1",
            "seed": 17,
            "notes": "matrix-v2",
        }
        exp = {
            "repo": "org/repo",
            "issue_set_id": "issues_repo_v1",
            "instance_ids": ["i1", "i2"],
            "domain": "library",
        }
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["repeats"], 3)
        self.assertEqual(resolved["issue_set_id"], "issues_repo_v1")
        self.assertEqual(resolved["instance_ids"], ["i1", "i2"])
        self.assertEqual(resolved["seed"], 17)
        self.assertEqual(resolved["notes"], "matrix-v2")
        self.assertEqual(resolved["domain"], "library")

    def test_resolve_experiment_includes_deterministic_retrieval_config(self):
        defaults = {
            "deterministic_seed_k": 7,
            "deterministic_depth": 3,
            "deterministic_neighbor_cap": 9,
            "deterministic_min_return_files": 1,
            "deterministic_score_ratio_cutoff": 0.7,
            "deterministic_min_score_cutoff": 0.0,
            "deterministic_hub_degree_threshold": 20,
            "deterministic_hub_penalty_scale": 0.35,
            "deterministic_w_sem": 0.4,
            "deterministic_w_graph": 0.25,
            "deterministic_w_conf": 0.2,
            "deterministic_w_hint": 0.1,
            "deterministic_w_pen": 0.05,
        }
        exp = {
            "repo": "org/repo",
            "deterministic_depth": 1,
            "deterministic_score_ratio_cutoff": 0.62,
            "deterministic_hub_penalty_scale": 0.5,
            "deterministic_w_pen": 0.12,
        }

        resolved = resolve_experiment(exp, defaults)

        self.assertEqual(resolved["deterministic_seed_k"], 7)
        self.assertEqual(resolved["deterministic_depth"], 1)
        self.assertEqual(resolved["deterministic_neighbor_cap"], 9)
        self.assertEqual(resolved["deterministic_min_return_files"], 1)
        self.assertAlmostEqual(resolved["deterministic_score_ratio_cutoff"], 0.62)
        self.assertAlmostEqual(resolved["deterministic_min_score_cutoff"], 0.0)
        self.assertEqual(resolved["deterministic_hub_degree_threshold"], 20)
        self.assertAlmostEqual(resolved["deterministic_hub_penalty_scale"], 0.5)
        self.assertAlmostEqual(resolved["deterministic_w_sem"], 0.4)
        self.assertAlmostEqual(resolved["deterministic_w_graph"], 0.25)
        self.assertAlmostEqual(resolved["deterministic_w_conf"], 0.2)
        self.assertAlmostEqual(resolved["deterministic_w_hint"], 0.1)
        self.assertAlmostEqual(resolved["deterministic_w_pen"], 0.12)

    def test_resolve_experiment_applies_deterministic_config_file_overrides(self):
        cfg = """
deterministic_retrieval:
  seed_k: 10
  depth: 3
  neighbor_cap: 16
  min_return_files: 1
  score_ratio_cutoff: 0.62
  min_score_cutoff: 0.05
  hub_degree_threshold: 24
  hub_penalty_scale: 0.4
  w_sem: 0.40
  w_graph: 0.20
  w_conf: 0.20
  w_hint: 0.10
  w_pen: 0.10
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "det.yaml"
            cfg_path.write_text(cfg, encoding="utf-8")
            resolved = resolve_experiment(
                {
                    "repo": "org/repo",
                    "deterministic_config_path": str(cfg_path),
                },
                defaults={},
            )

        self.assertEqual(resolved["deterministic_config_path"], str(cfg_path))
        self.assertEqual(resolved["deterministic_seed_k"], 10)
        self.assertEqual(resolved["deterministic_depth"], 3)
        self.assertEqual(resolved["deterministic_neighbor_cap"], 16)
        self.assertAlmostEqual(resolved["deterministic_score_ratio_cutoff"], 0.62)
        self.assertAlmostEqual(resolved["deterministic_hub_penalty_scale"], 0.4)
        self.assertAlmostEqual(resolved["deterministic_w_sem"], 0.4)

    def test_resolve_experiment_includes_methods_from_defaults(self):
        defaults = {"methods": ["gm_progressive", "rag_progressive", "bm25"]}
        exp = {"repo": "org/repo"}
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["methods"], ["gm_progressive", "rag_progressive", "bm25"])

    def test_resolve_experiment_methods_default_to_none(self):
        defaults = {}
        exp = {"repo": "org/repo"}
        resolved = resolve_experiment(exp, defaults)
        self.assertIsNone(resolved["methods"])

    def test_resolve_experiment_methods_experiment_override(self):
        defaults = {"methods": ["gm_progressive"]}
        exp = {"repo": "org/repo", "methods": ["bm25"]}
        resolved = resolve_experiment(exp, defaults)
        self.assertEqual(resolved["methods"], ["bm25"])


    def test_find_completed_methods_detects_existing_results(self):
        from run_suite import _find_completed_methods

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "20260218_220114"
            runs_dir.mkdir(parents=True, exist_ok=True)
            summary = {
                "gm_deterministic": {"mean_f1": 0.679, "n_success": 10},
                "_meta": {
                    "repo_name": "pallets/flask",
                    "enabled_methods": ["gm_deterministic"],
                },
            }
            (runs_dir / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            completed = _find_completed_methods("pallets/flask", tmpdir)
            self.assertIn("gm_deterministic", completed)
            # bm25 was not run → not in completed
            self.assertNotIn("bm25", completed)

    def test_find_completed_methods_ignores_other_repos(self):
        from run_suite import _find_completed_methods

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "20260218_220200"
            runs_dir.mkdir(parents=True, exist_ok=True)
            summary = {
                "bm25": {"mean_f1": 0.512, "n_success": 10},
                "_meta": {
                    "repo_name": "psf/requests",
                    "enabled_methods": ["bm25"],
                },
            }
            (runs_dir / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            # Ask for flask — should be empty even though requests/bm25 is done
            completed = _find_completed_methods("pallets/flask", tmpdir)
            self.assertEqual(len(completed), 0)


if __name__ == "__main__":
    unittest.main()
