import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.report_artifacts import generate_report_artifacts


class ReportArtifactTests(unittest.TestCase):
    def test_generate_report_artifacts_writes_manifest_and_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs_dir = root / "results" / "runs"
            run_a = runs_dir / "20260211_111111"
            run_b = runs_dir / "20260211_222222"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)

            summary_a = {
                "_meta": {"run_id": "20260211_111111", "repo_name": "pallets/flask"},
                "gm_deterministic": {"mean_f1": 0.72, "total_cost_tokens": 900},
                "gm_progressive": {"mean_f1": 0.71, "total_cost_tokens": 1000},
                "rag_baseline": {"mean_f1": 0.69, "total_cost_tokens": 1200},
            }
            summary_b = {
                "_meta": {"run_id": "20260211_222222", "repo_name": "psf/requests"},
                "gm_deterministic": {"mean_f1": 0.66, "total_cost_tokens": 920},
                "gm_progressive": {"mean_f1": 0.64, "total_cost_tokens": 980},
                "rag_baseline": {"mean_f1": 0.66, "total_cost_tokens": 1100},
            }
            (run_a / "summary.json").write_text(json.dumps(summary_a), encoding="utf-8")
            (run_b / "summary.json").write_text(json.dumps(summary_b), encoding="utf-8")

            output_root = root / "research_report" / "artifacts"
            artifact_dir = generate_report_artifacts(
                run_paths=[str(run_a), str(run_b)],
                output_root=str(output_root),
                artifact_id="frozen-20260211",
            )

            manifest_path = artifact_dir / "manifest.json"
            csv_path = artifact_dir / "tables" / "method_comparison.csv"
            tex_path = artifact_dir / "tables" / "method_comparison.tex"
            self.assertTrue(manifest_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(tex_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_id"], "frozen-20260211")
            self.assertEqual(len(manifest["runs"]), 2)
            self.assertEqual(manifest["runs"][0]["run_id"], "20260211_111111")

            with csv_path.open("r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertTrue(any(row["method"] == "gm_deterministic" for row in rows))
            self.assertTrue(any(row["method"] == "gm_progressive" for row in rows))
            self.assertTrue(any(row["method"] == "rag_baseline" for row in rows))


if __name__ == "__main__":
    unittest.main()
