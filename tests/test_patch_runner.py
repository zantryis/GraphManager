"""Tests for run_patch.py manifest loading and dry-run pipeline."""

import json
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


if __name__ == "__main__":
    unittest.main()
