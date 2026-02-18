"""Tests for run_patch.py manifest loading and dry-run pipeline."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ManifestLoadingTests(unittest.TestCase):
    def test_manifest_is_valid_yaml(self):
        import yaml
        p = Path("patch_manifests/swebench_verified_requests_v1.yaml")
        self.assertTrue(p.exists(), f"Manifest not found: {p}")
        data = yaml.safe_load(p.read_text())
        self.assertIn("dataset_name", data)
        self.assertIn("instance_ids", data)
        self.assertGreater(len(data["instance_ids"]), 0)
        self.assertIn("retrieval_method", data)
        self.assertIn("repo_name", data)

    def test_manifest_retrieval_method_is_supported(self):
        import yaml
        p = Path("patch_manifests/swebench_verified_requests_v1.yaml")
        data = yaml.safe_load(p.read_text())
        supported = {"gm_progressive", "gm_deterministic", "rag_progressive"}
        self.assertIn(data["retrieval_method"], supported)

    def test_manifest_instance_ids_are_unique(self):
        import yaml
        p = Path("patch_manifests/swebench_verified_requests_v1.yaml")
        data = yaml.safe_load(p.read_text())
        ids = data["instance_ids"]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate instance_ids in manifest")

    def test_manifest_exposes_patch_and_manager_knobs(self):
        import yaml
        p = Path("patch_manifests/swebench_verified_requests_v1.yaml")
        data = yaml.safe_load(p.read_text())
        self.assertIn("manager_max_turns", data)
        self.assertIn("patch_max_output_tokens", data)
        self.assertIn("patch_max_file_chars", data)


class DockerCheckTests(unittest.TestCase):
    def test_check_docker_returns_bool(self):
        from run_patch import _check_docker
        result = _check_docker()
        self.assertIsInstance(result, bool)


class RetryPolicyTests(unittest.TestCase):
    def test_run_with_rate_limit_backoff_retries_transient_errors(self):
        from run_patch import _run_with_rate_limit_backoff

        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return "ok"

        with patch("run_patch.time.sleep") as sleep_mock, patch("run_patch.random.uniform", return_value=0.0):
            out = _run_with_rate_limit_backoff(
                flaky,
                label="retrieval",
                max_retries=4,
                initial_delay_s=2.0,
                backoff_multiplier=2.0,
                max_delay_s=30.0,
                jitter_s=0.5,
            )

        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 2.0)
        self.assertEqual(sleep_mock.call_args_list[1].args[0], 4.0)

    def test_run_with_rate_limit_backoff_raises_non_transient_error(self):
        from run_patch import _run_with_rate_limit_backoff

        def boom():
            raise ValueError("syntax problem")

        with patch("run_patch.time.sleep") as sleep_mock:
            with self.assertRaises(ValueError):
                _run_with_rate_limit_backoff(boom, label="patch")
        sleep_mock.assert_not_called()

    def test_run_with_rate_limit_backoff_exhausts_retries(self):
        from run_patch import _run_with_rate_limit_backoff

        def always_429():
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        with patch("run_patch.time.sleep"), patch("run_patch.random.uniform", return_value=0.0):
            with self.assertRaises(RuntimeError):
                _run_with_rate_limit_backoff(
                    always_429,
                    label="retrieval",
                    max_retries=2,
                    initial_delay_s=1.0,
                    backoff_multiplier=2.0,
                    max_delay_s=10.0,
                    jitter_s=0.0,
                )


class ModelSelectionTests(unittest.TestCase):
    def test_resolve_model_config_uses_defaults(self):
        from run_patch import _resolve_model_config

        manager_model, patch_model = _resolve_model_config({})
        self.assertEqual(manager_model, "gemini-3-flash-preview")
        self.assertEqual(patch_model, "gemini-2.5-pro")

    def test_resolve_model_config_honors_manifest_overrides(self):
        from run_patch import _resolve_model_config

        manager_model, patch_model = _resolve_model_config(
            {"manager_model": "gemini-2.5-flash", "patch_model": "gemini-3-pro-preview"}
        )
        self.assertEqual(manager_model, "gemini-2.5-flash")
        self.assertEqual(patch_model, "gemini-3-pro-preview")


class PatchApplyCheckTests(unittest.TestCase):
    def _init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True)
        (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.py"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

    def test_apply_check_passes_on_valid_diff(self):
        from run_patch import _git_apply_check

        valid_diff = (
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def f():\n"
            "-    return 1\n"
            "+    return 2\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            self._init_repo(repo)
            ok, stderr = _git_apply_check(str(repo), valid_diff)

        self.assertTrue(ok)
        self.assertEqual(stderr, "")

    def test_apply_check_fails_on_truncated_diff(self):
        from run_patch import _git_apply_check

        truncated_diff = (
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def f():\n"
            "-    return 1\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            self._init_repo(repo)
            ok, stderr = _git_apply_check(str(repo), truncated_diff)

        self.assertFalse(ok)
        self.assertTrue(stderr.strip())

    def test_apply_check_fails_on_wrong_path(self):
        from run_patch import _git_apply_check

        wrong_path_diff = (
            "--- a/missing.py\n"
            "+++ b/missing.py\n"
            "@@ -1 +1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            self._init_repo(repo)
            ok, stderr = _git_apply_check(str(repo), wrong_path_diff)

        self.assertFalse(ok)
        self.assertTrue(stderr.strip())


class PatchRetryFlowTests(unittest.TestCase):
    def test_repair_retry_on_apply_failure(self):
        from run_patch import _generate_patch_with_retries

        contexts = []

        def patch_generate_fn(*, retrieved_files, correction_context):
            contexts.append(correction_context)
            if len(contexts) == 1:
                return "bad patch", {"total_tokens": 10}
            return "good patch", {"total_tokens": 20}

        def apply_check_fn(patch_text):
            if patch_text == "bad patch":
                return False, "error: patch failed"
            return True, ""

        def retrieval_retry_fn(*, previous_files, failure_hint):
            raise AssertionError("retrieval retry should not be called")

        result = _generate_patch_with_retries(
            issue_text="issue",
            initial_retrieved_files=["a.py"],
            patch_generate_fn=patch_generate_fn,
            apply_check_fn=apply_check_fn,
            retrieval_retry_fn=retrieval_retry_fn,
            max_repair_retries=2,
            max_retrieval_retries=1,
        )

        self.assertEqual(result["patch_status"], "patched")
        self.assertEqual(result["repair_retries_used"], 1)
        self.assertEqual(result["retrieval_retries_used"], 0)
        self.assertEqual(len(contexts), 2)
        self.assertIsNone(contexts[0])
        self.assertIn("patch failed", contexts[1] or "")

    def test_max_repair_retries_respected(self):
        from run_patch import _generate_patch_with_retries

        calls = {"n": 0}

        def patch_generate_fn(*, retrieved_files, correction_context):
            calls["n"] += 1
            return "always bad", {"total_tokens": 5}

        def apply_check_fn(patch_text):
            return False, "error: malformed patch"

        def retrieval_retry_fn(*, previous_files, failure_hint):
            raise AssertionError("retrieval retry should not be called")

        result = _generate_patch_with_retries(
            issue_text="issue",
            initial_retrieved_files=["a.py"],
            patch_generate_fn=patch_generate_fn,
            apply_check_fn=apply_check_fn,
            retrieval_retry_fn=retrieval_retry_fn,
            max_repair_retries=2,
            max_retrieval_retries=0,
        )

        self.assertEqual(result["patch_status"], "apply_failed")
        self.assertEqual(calls["n"], 3)  # initial + 2 repairs
        self.assertEqual(result["repair_retries_used"], 2)

    def test_retrieval_retry_trigger_and_cap_behavior(self):
        from run_patch import _generate_patch_with_retries

        patch_calls = {"n": 0}
        retrieval_calls = {"n": 0}

        def patch_generate_fn(*, retrieved_files, correction_context):
            patch_calls["n"] += 1
            return None, {"total_tokens": 3, "cannot_patch": True, "stop_reason": "cannot_patch"}

        def apply_check_fn(patch_text):
            raise AssertionError("apply check should not run when patch is None")

        def retrieval_retry_fn(*, previous_files, failure_hint):
            retrieval_calls["n"] += 1
            return ["b.py"], {"total_tokens": 2}

        result = _generate_patch_with_retries(
            issue_text="issue",
            initial_retrieved_files=["a.py"],
            patch_generate_fn=patch_generate_fn,
            apply_check_fn=apply_check_fn,
            retrieval_retry_fn=retrieval_retry_fn,
            max_repair_retries=2,
            max_retrieval_retries=1,
        )

        self.assertEqual(result["patch_status"], "no_patch")
        self.assertEqual(retrieval_calls["n"], 1)
        self.assertEqual(result["retrieval_retries_used"], 1)
        self.assertEqual(patch_calls["n"], 2)


class PatchSummaryMetricsTests(unittest.TestCase):
    def test_apply_success_metrics(self):
        from run_patch import _compute_patch_robustness_metrics

        metrics = _compute_patch_robustness_metrics(
            [
                {"patch_status": "patched"},
                {"patch_status": "apply_failed"},
                {"patch_status": "patched"},
                {"patch_status": "no_patch"},
            ]
        )

        self.assertEqual(metrics["n_apply_ok"], 2)
        self.assertEqual(metrics["n_apply_failed"], 1)
        self.assertAlmostEqual(metrics["apply_success_rate"], 2 / 3, places=6)


if __name__ == "__main__":
    unittest.main()
