import json
import os
import tempfile
import time
import unittest
from pathlib import Path


class PatchDashboardTests(unittest.TestCase):
    def _write_partial_entry(
        self,
        run_dir: Path,
        instance_id: str,
        status: str,
        *,
        filename: str = "predictions_partial.jsonl",
    ) -> None:
        entry = {
            "instance_id": instance_id,
            "prediction": {
                "instance_id": instance_id,
                "model_name_or_path": "graphmanager-bm25",
            },
            "per_instance": {
                "instance_id": instance_id,
                "patch_status": status,
            },
        }
        with (run_dir / filename).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_run_meta(
        self,
        run_dir: Path,
        *,
        run_id: str,
        manifest: str,
        retrieval_method: str,
        n_instances_planned: int,
        pid: int | None = None,
    ) -> None:
        payload = {
            "run_id": run_id,
            "manifest": manifest,
            "retrieval_method": retrieval_method,
            "n_instances_planned": n_instances_planned,
        }
        if pid is not None:
            payload["pid"] = pid
        (run_dir / "run_meta.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_discover_run_dirs_finds_nested_patch_runs(self):
        from src.patch_dashboard import discover_run_dirs

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "results"
            run_a = root / "patch_runs" / "20260224_010101"
            run_a.mkdir(parents=True, exist_ok=True)
            (run_a / "predictions_partial.jsonl").write_text("", encoding="utf-8")

            run_b = root / "v2_pilot_parallel" / "pilot_bm25" / "patch_runs" / "20260224_010102"
            run_b.mkdir(parents=True, exist_ok=True)
            (run_b / "patch_summary.json").write_text("{}", encoding="utf-8")

            found = discover_run_dirs(root)
            found_set = {p.resolve() for p in found}
            self.assertIn(run_a.resolve(), found_set)
            self.assertIn(run_b.resolve(), found_set)

    def test_discover_run_dirs_includes_empty_run_dirs(self):
        from src.patch_dashboard import discover_run_dirs

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "results"
            empty_run = root / "patch_runs" / "20260224_010200"
            empty_run.mkdir(parents=True, exist_ok=True)

            found = discover_run_dirs(root)
            self.assertIn(empty_run.resolve(), {p.resolve() for p in found})

    def test_build_run_record_uses_summary_when_present(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010103"
            run_dir.mkdir(parents=True, exist_ok=True)
            summary = {
                "run_id": "20260224_010103",
                "retrieval_method": "gm_progressive",
                "n_instances": 8,
                "n_patched": 7,
                "harness_results": {"n_resolved": 5, "resolved_rate": 0.625},
                "total_cost_tokens": 366129,
                "cost_per_resolved_issue": 73225.8,
            }
            (run_dir / "patch_summary.json").write_text(json.dumps(summary), encoding="utf-8")

            record = build_run_record(run_dir)
            self.assertEqual(record["run_id"], "20260224_010103")
            self.assertEqual(record["retrieval_method"], "gm_progressive")
            self.assertEqual(record["status"], "complete")
            self.assertEqual(record["n_instances"], 8)
            self.assertEqual(record["n_patched"], 7)
            self.assertEqual(record["n_resolved"], 5)

    def test_build_run_record_marks_running_without_summary_when_recent(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010104"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010104",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
            )
            self._write_partial_entry(run_dir, "i-1", "patched")
            self._write_partial_entry(run_dir, "i-2", "apply_failed")

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "running")
            self.assertEqual(record["n_instances"], 8)
            self.assertEqual(record["n_completed"], 2)
            self.assertEqual(record["n_patched"], 1)
            self.assertEqual(record["n_apply_failed"], 1)
            self.assertEqual(record["retrieval_method"], "bm25")

    def test_build_run_record_counts_worker_checkpoint_progress(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010204"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010204",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
            )
            self._write_partial_entry(run_dir, "i-1", "patched", filename="predictions_worker_0.jsonl")
            self._write_partial_entry(run_dir, "i-2", "apply_failed", filename="predictions_worker_1.jsonl")

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "running")
            self.assertEqual(record["n_completed"], 2)
            self.assertEqual(record["n_patched"], 1)
            self.assertEqual(record["n_apply_failed"], 1)

    def test_build_run_record_marks_stalled_when_partial_is_old(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010105"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010105",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
            )
            self._write_partial_entry(run_dir, "i-1", "patched")
            partial = run_dir / "predictions_partial.jsonl"
            old_time = time.time() - (30 * 60)
            partial.touch()
            os.utime(partial, (old_time, old_time))

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "stalled")

    def test_build_run_record_marks_stalled_when_not_started_meta_is_old(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010115"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010115",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
            )
            meta = run_dir / "run_meta.json"
            old_time = time.time() - (40 * 60)
            os.utime(meta, (old_time, old_time))

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "stalled")

    def test_build_run_record_marks_stalled_when_run_pid_is_dead_before_progress(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010113"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010113",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
                pid=999999,
            )

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "stalled")
            self.assertEqual(record["meta_pid"], 999999)
            self.assertFalse(record["meta_pid_alive"])

    def test_build_run_record_marks_not_started_when_run_pid_is_alive_before_progress(self):
        from src.patch_dashboard import build_run_record

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "patch_runs" / "20260224_010114"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(
                run_dir,
                run_id="20260224_010114",
                manifest="/tmp/manifest.yaml",
                retrieval_method="bm25",
                n_instances_planned=8,
                pid=os.getpid(),
            )

            record = build_run_record(run_dir, stale_after_minutes=15)
            self.assertEqual(record["status"], "not_started")
            self.assertEqual(record["meta_pid"], os.getpid())
            self.assertTrue(record["meta_pid_alive"])

    def test_collect_dashboard_status_dedupes_same_manifest_to_freshest(self):
        from src.patch_dashboard import collect_dashboard_status

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "results"
            old_run = root / "patch_runs" / "20260224_010106"
            new_run = root / "patch_runs" / "20260224_010107"
            old_run.mkdir(parents=True, exist_ok=True)
            new_run.mkdir(parents=True, exist_ok=True)

            manifest = "/tmp/same_manifest.yaml"
            self._write_run_meta(
                old_run,
                run_id="20260224_010106",
                manifest=manifest,
                retrieval_method="agentic_cold_start",
                n_instances_planned=22,
            )
            self._write_run_meta(
                new_run,
                run_id="20260224_010107",
                manifest=manifest,
                retrieval_method="agentic_cold_start",
                n_instances_planned=22,
            )
            self._write_partial_entry(old_run, "i-1", "patched")
            self._write_partial_entry(new_run, "i-1", "patched")

            old_partial = old_run / "predictions_partial.jsonl"
            new_partial = new_run / "predictions_partial.jsonl"
            old_time = time.time() - (20 * 60)
            now_time = time.time()
            os.utime(old_partial, (old_time, old_time))
            os.utime(new_partial, (now_time, now_time))

            rows = collect_dashboard_status(root, stale_after_minutes=15)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "20260224_010107")

    def test_collect_dashboard_status_prefers_new_attempt_over_old_complete(self):
        from src.patch_dashboard import collect_dashboard_status

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "results"
            complete_run = root / "patch_runs" / "20260224_010108"
            new_attempt = root / "patch_runs" / "20260224_010109"
            complete_run.mkdir(parents=True, exist_ok=True)
            new_attempt.mkdir(parents=True, exist_ok=True)

            manifest = "/tmp/same_manifest.yaml"
            self._write_run_meta(
                complete_run,
                run_id="20260224_010108",
                manifest=manifest,
                retrieval_method="bm25",
                n_instances_planned=22,
            )
            self._write_run_meta(
                new_attempt,
                run_id="20260224_010109",
                manifest=manifest,
                retrieval_method="bm25",
                n_instances_planned=22,
            )
            summary = {
                "run_id": "20260224_010108",
                "manifest": manifest,
                "retrieval_method": "bm25",
                "n_instances": 22,
                "n_patched": 10,
                "harness_results": {"n_resolved": 3, "resolved_rate": 3 / 22},
            }
            (complete_run / "patch_summary.json").write_text(json.dumps(summary), encoding="utf-8")

            old_time = time.time() - (20 * 60)
            now_time = time.time()
            os.utime(complete_run / "patch_summary.json", (old_time, old_time))
            os.utime(new_attempt / "run_meta.json", (now_time, now_time))

            rows = collect_dashboard_status(
                root,
                stale_after_minutes=15,
                active_only=True,
                include_complete=False,
                include_stale=False,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "20260224_010109")
            self.assertEqual(rows[0]["status"], "not_started")

    def test_collect_dashboard_status_active_only_hides_stale_and_old_pending(self):
        from src.patch_dashboard import collect_dashboard_status

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "results"
            running_run = root / "patch_runs" / "20260224_010110"
            stalled_run = root / "patch_runs" / "20260224_010111"
            old_pending = root / "patch_runs" / "20260224_010112"
            running_run.mkdir(parents=True, exist_ok=True)
            stalled_run.mkdir(parents=True, exist_ok=True)
            old_pending.mkdir(parents=True, exist_ok=True)

            self._write_run_meta(
                running_run,
                run_id="20260224_010110",
                manifest="/tmp/running.yaml",
                retrieval_method="bm25",
                n_instances_planned=10,
            )
            self._write_run_meta(
                stalled_run,
                run_id="20260224_010111",
                manifest="/tmp/stalled.yaml",
                retrieval_method="bm25",
                n_instances_planned=10,
            )
            self._write_run_meta(
                old_pending,
                run_id="20260224_010112",
                manifest="/tmp/old_pending.yaml",
                retrieval_method="bm25",
                n_instances_planned=10,
            )
            self._write_partial_entry(running_run, "i-1", "patched")
            self._write_partial_entry(stalled_run, "i-2", "patched")

            now_time = time.time()
            running_ts = now_time - (2 * 60)
            stalled_ts = now_time - (40 * 60)
            old_pending_ts = now_time - (90 * 60)
            os.utime(running_run / "predictions_partial.jsonl", (running_ts, running_ts))
            os.utime(stalled_run / "predictions_partial.jsonl", (stalled_ts, stalled_ts))
            os.utime(old_pending / "run_meta.json", (old_pending_ts, old_pending_ts))

            rows = collect_dashboard_status(
                root,
                stale_after_minutes=15,
                active_only=True,
                include_complete=False,
                include_stale=False,
                pending_grace_minutes=30,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "20260224_010110")
            self.assertEqual(rows[0]["status"], "running")

    def test_summarize_dashboard_runs_reports_patched_over_total(self):
        from src.patch_dashboard import summarize_dashboard_runs

        runs = [
            {"status": "running", "n_instances": 10, "n_completed": 4, "n_patched": 3},
            {"status": "complete", "n_instances": 8, "n_completed": 8, "n_patched": 5},
            {"status": "not_started", "n_instances": 12, "n_completed": 0, "n_patched": 0},
        ]

        summary = summarize_dashboard_runs(runs)
        self.assertEqual(summary["run_count"], 3)
        self.assertEqual(summary["n_instances_total"], 30)
        self.assertEqual(summary["n_completed_total"], 12)
        self.assertEqual(summary["n_patched_total"], 8)
        self.assertAlmostEqual(summary["patched_rate_total"], 8 / 30, places=6)

    def test_load_manifest_plan_summary_counts_instances_and_methods(self):
        from src.patch_dashboard import load_manifest_plan_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifests = root / "patch_manifests" / "v2_verified"
            manifests.mkdir(parents=True, exist_ok=True)
            m1 = manifests / "repo_a_bm25.yaml"
            m2 = manifests / "repo_b_oracle.yaml"
            m1.write_text(
                json.dumps(
                    {
                        "retrieval_method": "bm25",
                        "instance_ids": ["a1", "a2", "a3"],
                    }
                ),
                encoding="utf-8",
            )
            m2.write_text(
                json.dumps(
                    {
                        "retrieval_method": "oracle",
                        "instance_ids": ["b1", "b2"],
                    }
                ),
                encoding="utf-8",
            )
            manifest_list = root / "manifest_list.txt"
            manifest_list.write_text(
                "patch_manifests/v2_verified/repo_a_bm25.yaml\n"
                "patch_manifests/v2_verified/repo_b_oracle.yaml\n",
                encoding="utf-8",
            )

            summary = load_manifest_plan_summary(manifest_list, root_dir=root)
            self.assertTrue(summary["exists"])
            self.assertEqual(summary["n_manifests_planned"], 2)
            self.assertEqual(summary["n_instances_planned"], 5)
            self.assertEqual(summary["n_load_failed"], 0)
            self.assertEqual(summary["per_method"]["bm25"]["n_instances"], 3)
            self.assertEqual(summary["per_method"]["oracle"]["n_instances"], 2)


if __name__ == "__main__":
    unittest.main()
