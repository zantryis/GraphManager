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


if __name__ == "__main__":
    unittest.main()
