"""Tests for run_patch.py manifest loading and dry-run pipeline."""

import json
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
