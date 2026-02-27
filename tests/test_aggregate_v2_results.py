import csv
import json
import unittest
import tempfile
from pathlib import Path


class AggregateV2ResultsTests(unittest.TestCase):
    def _make_retrieval_summary(
        self,
        run_dir: Path,
        repo: str,
        method: str,
        mean_f1: float,
        n_success: int = 10,
    ) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            method: {
                "mean_f1": mean_f1,
                "mean_precision": mean_f1 + 0.02,
                "mean_recall": mean_f1 - 0.02,
                "n_issues": n_success,
                "n_success": n_success,
                "avg_runtime_tokens_per_issue": 1000.0,
                "setup_embedding_tokens": 150000,
                "avg_total_cost_tokens_per_issue": 16000.0,
            },
            "_meta": {
                "repo_name": repo,
                "enabled_methods": [method],
                "run_id": run_dir.name,
            },
        }
        (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def _make_patch_summary(
        self,
        run_dir: Path,
        repo: str,
        method: str,
        n_instances: int,
        n_resolved: int,
    ) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "repo_name": repo,
            "retrieval_method": method,
            "n_instances": n_instances,
            "n_patched": n_instances,
            "harness_results": {
                "n_resolved": n_resolved,
                "resolved_rate": n_resolved / n_instances if n_instances else 0.0,
            },
            "total_cost_tokens": n_instances * 10000,
            "cost_per_resolved_issue": (n_instances * 10000 // n_resolved) if n_resolved else None,
        }
        (run_dir / "patch_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def test_retrieval_csv_from_mock_summaries(self):
        from tools.aggregate_v2_results import collect_retrieval_results, write_retrieval_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_retrieval_summary(
                root / "runs" / "20260218_220114",
                repo="pallets/flask",
                method="gm_deterministic",
                mean_f1=0.679,
            )
            self._make_retrieval_summary(
                root / "runs" / "20260218_220200",
                repo="psf/requests",
                method="bm25",
                mean_f1=0.512,
            )

            retrieval = collect_retrieval_results(root)
            self.assertIn("pallets/flask", retrieval)
            self.assertIn("gm_deterministic", retrieval["pallets/flask"])
            self.assertAlmostEqual(retrieval["pallets/flask"]["gm_deterministic"]["mean_f1"], 0.679, places=3)

            csv_path = root / "retrieval.csv"
            write_retrieval_csv(retrieval, csv_path)
            self.assertTrue(csv_path.exists())

            with csv_path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            flask_gm_rows = [r for r in rows if r["repo"] == "pallets/flask" and r["method"] == "gm_deterministic"]
            self.assertEqual(len(flask_gm_rows), 1)
            self.assertEqual(float(flask_gm_rows[0]["mean_f1"]), 0.679)

            # pending cells should be present with None/empty values
            flask_bm25_rows = [r for r in rows if r["repo"] == "pallets/flask" and r["method"] == "bm25"]
            self.assertEqual(len(flask_bm25_rows), 1)
            self.assertEqual(flask_bm25_rows[0]["mean_f1"], "")

    def test_patching_csv_from_mock_patch_summaries(self):
        from tools.aggregate_v2_results import collect_patching_results, write_patching_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_patch_summary(
                root / "v2_full_runs" / "patch_runs" / "20260225_run1",
                repo="pallets/flask",
                method="gm_progressive",
                n_instances=10,
                n_resolved=4,
            )

            patching = collect_patching_results(root)
            self.assertIn("pallets/flask", patching)
            self.assertIn("gm_progressive", patching["pallets/flask"])

            harness = patching["pallets/flask"]["gm_progressive"].get("harness_results", {})
            self.assertEqual(harness.get("n_resolved"), 4)
            self.assertAlmostEqual(harness.get("resolved_rate"), 0.4, places=3)

            csv_path = root / "patching.csv"
            write_patching_csv(patching, csv_path)
            self.assertTrue(csv_path.exists())

            with csv_path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            flask_gm_rows = [r for r in rows if r["repo"] == "pallets/flask" and r["method"] == "gm_progressive"]
            self.assertEqual(len(flask_gm_rows), 1)
            self.assertEqual(float(flask_gm_rows[0]["resolve_rate"]), 0.4)

    def test_collect_patching_falls_back_to_run_meta_for_repo_name(self):
        """When patch_summary.json has repo_name=null, fall back to run_meta.json."""
        from tools.aggregate_v2_results import collect_patching_results

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "v2_full_runs" / "patch_runs" / "20260226_999999"
            run_dir.mkdir(parents=True)
            # patch_summary.json with null repo_name (as produced by Stage-1-only runs)
            summary = {
                "repo_name": None,
                "retrieval_method": "bm25",
                "n_instances": 8,
                "n_patched": 5,
                "harness_results": {"n_resolved": 3, "resolved_rate": 0.375},
                "total_cost_tokens": 80000,
                "cost_per_resolved_issue": None,
            }
            (run_dir / "patch_summary.json").write_text(json.dumps(summary), encoding="utf-8")
            # run_meta.json carries the correct repo_name
            run_meta = {
                "repo_name": "psf/requests",
                "retrieval_method": "bm25",
                "n_instances_planned": 8,
                "manifest": "psf_requests_bm25_v1.yaml",
            }
            (run_dir / "run_meta.json").write_text(json.dumps(run_meta), encoding="utf-8")

            patching = collect_patching_results(root)
            self.assertIn(
                "psf/requests",
                patching,
                "repo_name from run_meta.json must be used when patch_summary has null",
            )
            self.assertIn("bm25", patching["psf/requests"])

    def test_mcnemar_insufficient_data_does_not_crash(self):
        from tools.aggregate_v2_results import compute_mcnemar

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mcnemar.txt"
            # Empty patching dict → no instance-level data
            compute_mcnemar({}, output_path)

            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            # Should contain "p=null" or note about insufficient data — must not crash
            self.assertIn("p=null", content)


if __name__ == "__main__":
    unittest.main()
