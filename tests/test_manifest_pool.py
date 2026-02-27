import inspect
import json
import os
import tempfile
import time
import unittest
from pathlib import Path


class ManifestPoolTests(unittest.TestCase):
    def test_build_run_patch_cmd_includes_modal_flag_in_modal_mode(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=0,
            resume_run_dir=None,
            execution_mode="modal",
            evaluate_mode="stage12",
            run_workers=1,
        )
        self.assertIn("--modal", cmd)

    def test_build_run_patch_cmd_omits_modal_flag_in_local_mode(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=0,
            resume_run_dir=None,
            execution_mode="local",
            evaluate_mode="stage12",
            run_workers=1,
        )
        self.assertNotIn("--modal", cmd)

    def test_build_run_patch_cmd_stage1_only_skips_evaluate_and_modal(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=0,
            resume_run_dir=None,
            execution_mode="modal",
            evaluate_mode="stage1_only",
            run_workers=1,
        )
        self.assertNotIn("--evaluate", cmd)
        self.assertNotIn("--modal", cmd)

    def test_build_run_patch_cmd_disables_timeout_when_zero(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=0,
            resume_run_dir=None,
            execution_mode="modal",
            evaluate_mode="stage12",
            run_workers=1,
        )
        self.assertNotIn("timeout", cmd)
        self.assertIn("--manifest", cmd)
        self.assertIn(str(manifest), cmd)
        self.assertIn("--results-dir", cmd)
        self.assertIn(str(results_dir), cmd)

    def test_build_run_patch_cmd_uses_timeout_when_positive(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=7200,
            resume_run_dir=None,
            execution_mode="modal",
            evaluate_mode="stage12",
            run_workers=1,
        )
        self.assertEqual(cmd[:4], ["timeout", "--signal=TERM", "--kill-after=30s", "7200s"])

    def test_build_run_patch_cmd_forwards_workers_flag(self):
        from tools.run_manifest_pool import _build_run_patch_cmd

        root = Path("/tmp/repo")
        manifest = Path("/tmp/repo/patch_manifests/x.yaml")
        results_dir = Path("/tmp/repo/results/v2")
        cmd = _build_run_patch_cmd(
            root=root,
            manifest=manifest,
            results_dir=results_dir,
            manifest_timeout_s=0,
            resume_run_dir=None,
            execution_mode="local",
            evaluate_mode="stage1_only",
            run_workers=8,
        )
        self.assertIn("--workers", cmd)
        workers_idx = cmd.index("--workers")
        self.assertEqual(cmd[workers_idx + 1], "8")

    def test_find_latest_incomplete_run_dir_prefers_newer_run(self):
        from tools.run_manifest_pool import _find_latest_incomplete_run_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_dir = root / "results"
            patch_runs = results_dir / "patch_runs"
            patch_runs.mkdir(parents=True, exist_ok=True)
            manifest = root / "patch_manifests" / "m.yaml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("repo_name: demo/repo\n", encoding="utf-8")

            older = patch_runs / "20260101_000001"
            newer = patch_runs / "20260101_000002"
            older.mkdir()
            newer.mkdir()

            (older / "run_meta.json").write_text(
                json.dumps({"manifest": str(manifest.resolve())}),
                encoding="utf-8",
            )
            (newer / "run_meta.json").write_text(
                json.dumps({"manifest": str(manifest.resolve())}),
                encoding="utf-8",
            )

            # Ensure newer has later mtime by explicit utime skew.
            old_meta = older / "run_meta.json"
            new_meta = newer / "run_meta.json"
            now = time.time()
            old_ts = now - 120
            new_ts = now - 10
            old_meta.touch()
            new_meta.touch()
            os.utime(old_meta, (old_ts, old_ts))
            os.utime(new_meta, (new_ts, new_ts))

            run_dir = _find_latest_incomplete_run_dir(manifest, results_dir)
            self.assertEqual(run_dir, newer)

    def test_find_latest_incomplete_run_dir_ignores_completed_runs(self):
        from tools.run_manifest_pool import _find_latest_incomplete_run_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_dir = root / "results"
            patch_runs = results_dir / "patch_runs"
            patch_runs.mkdir(parents=True, exist_ok=True)
            manifest = root / "patch_manifests" / "m.yaml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("repo_name: demo/repo\n", encoding="utf-8")

            run_dir = patch_runs / "20260101_000003"
            run_dir.mkdir()
            (run_dir / "run_meta.json").write_text(
                json.dumps({"manifest": str(manifest.resolve())}),
                encoding="utf-8",
            )
            (run_dir / "patch_summary.json").write_text("{}", encoding="utf-8")

            self.assertIsNone(_find_latest_incomplete_run_dir(manifest, results_dir))


    # ── T2 design gap: evaluate_mode-aware completion checks ──────────────────

    def _make_manifest_and_summary(self, tmpdir: str, *, harness_run_id=None):
        """Helper: create a manifest file and a patch_summary.json that references it."""
        root = Path(tmpdir)
        results_dir = root / "results"
        patch_runs = results_dir / "patch_runs"
        patch_runs.mkdir(parents=True, exist_ok=True)
        manifest = root / "patch_manifests" / "m.yaml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("repo_name: demo/repo\n", encoding="utf-8")

        run_dir = patch_runs / "20260101_000001"
        run_dir.mkdir()
        (run_dir / "run_meta.json").write_text(
            json.dumps({"manifest": str(manifest.resolve())}),
            encoding="utf-8",
        )
        summary = {
            "manifest": str(manifest.resolve()),
            "harness_run_id": harness_run_id,
        }
        (run_dir / "patch_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        return manifest, results_dir, run_dir

    def test_is_manifest_completed_stage12_returns_false_when_harness_run_id_null(self):
        """T2 gap: stage12 mode must NOT treat Stage-1-only runs as complete."""
        from tools.run_manifest_pool import _is_manifest_completed

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, results_dir, _ = self._make_manifest_and_summary(
                tmpdir, harness_run_id=None
            )
            self.assertFalse(
                _is_manifest_completed(manifest, results_dir, evaluate_mode="stage12"),
                "Stage-1-only run (harness_run_id=null) must not be complete for stage12",
            )

    def test_is_manifest_completed_stage12_returns_true_when_harness_run_id_set(self):
        """T2 gap: stage12 mode treats runs with harness_run_id set as complete."""
        from tools.run_manifest_pool import _is_manifest_completed

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, results_dir, _ = self._make_manifest_and_summary(
                tmpdir, harness_run_id="graphmanager_20260227_gm_progressive_abc123"
            )
            self.assertTrue(
                _is_manifest_completed(manifest, results_dir, evaluate_mode="stage12"),
                "Stage-1+2 run (harness_run_id set) must be complete for stage12",
            )

    def test_is_manifest_completed_stage1only_true_regardless_of_harness_run_id(self):
        """Backward compat: stage1_only mode treats any patch_summary.json as complete."""
        from tools.run_manifest_pool import _is_manifest_completed

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, results_dir, _ = self._make_manifest_and_summary(
                tmpdir, harness_run_id=None
            )
            self.assertTrue(
                _is_manifest_completed(manifest, results_dir, evaluate_mode="stage1_only"),
                "Stage-1-only run must be complete for stage1_only mode (backward compat)",
            )

    def test_find_incomplete_stage12_returns_stage1_complete_dir(self):
        """T2 gap: stage12 mode must surface Stage-1-complete dirs for Stage-2 resumption."""
        from tools.run_manifest_pool import _find_latest_incomplete_run_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, results_dir, run_dir = self._make_manifest_and_summary(
                tmpdir, harness_run_id=None
            )
            result = _find_latest_incomplete_run_dir(
                manifest, results_dir, evaluate_mode="stage12"
            )
            self.assertEqual(
                result,
                run_dir,
                "stage12 mode must return Stage-1-complete dir so Stage 2 can run",
            )

    def test_find_incomplete_stage1only_skips_stage1_complete_dir(self):
        """Backward compat: stage1_only mode skips dirs with patch_summary.json."""
        from tools.run_manifest_pool import _find_latest_incomplete_run_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, results_dir, _ = self._make_manifest_and_summary(
                tmpdir, harness_run_id=None
            )
            result = _find_latest_incomplete_run_dir(
                manifest, results_dir, evaluate_mode="stage1_only"
            )
            self.assertIsNone(
                result,
                "stage1_only mode must not return Stage-1-complete dir (backward compat)",
            )

    def test_run_repo_issue_batch_closes_git_repo(self):
        """Git hang: _run_repo_issue_batch must call repo_git.close() in its finally block."""
        import run_patch

        src = inspect.getsource(run_patch.run_patch_pipeline)
        self.assertIn(
            "repo_git.close()",
            src,
            "repo_git.close() must appear in run_patch_pipeline source to prevent "
            "git cat-file subprocess leaks (see dev_logs/2026-02-27-t1-monitoring-stall-recovery.md)",
        )


if __name__ == "__main__":
    unittest.main()
