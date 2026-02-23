import json
import unittest
from pathlib import Path

import yaml


class N100ManifestFreezeTests(unittest.TestCase):
    def setUp(self):
        self.split_path = Path("patch_manifests/verified_n100_split_v1.json")
        self.ledger_path = Path("patch_manifests/n100_verified/manifest_ledger_v1.json")
        self.assertTrue(self.split_path.exists(), f"Missing split file: {self.split_path}")
        self.assertTrue(self.ledger_path.exists(), f"Missing ledger file: {self.ledger_path}")
        self.split = json.loads(self.split_path.read_text(encoding="utf-8"))
        self.ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def test_split_has_fixed_target_n_and_anchor_continuity(self):
        selected = self.split["selected_instance_ids"]
        total = sum(len(ids) for ids in selected.values())
        self.assertEqual(self.split["target_n"], 100)
        self.assertEqual(total, 100)
        self.assertEqual(len(selected.get("psf/requests", [])), 8)
        self.assertEqual(len(selected.get("pytest-dev/pytest", [])), 19)
        self.assertEqual(len(selected.get("pallets/flask", [])), 1)

    def test_ledger_covers_all_methods_per_repo(self):
        by_repo = {}
        for entry in self.ledger["entries"]:
            by_repo.setdefault(entry["repo"], set()).add(entry["method"])
        expected_methods = {"oracle", "gm_progressive", "rag_progressive", "none"}
        self.assertEqual(set(by_repo), set(self.split["selected_instance_ids"]))
        for repo, methods in by_repo.items():
            self.assertEqual(methods, expected_methods, f"Missing method entries for {repo}")

    def test_instance_ids_identical_across_methods_for_each_repo(self):
        by_repo = {}
        for entry in self.ledger["entries"]:
            repo = entry["repo"]
            manifest_path = Path(entry["manifest_path"])
            self.assertTrue(manifest_path.exists(), f"Missing manifest: {manifest_path}")
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            ids = tuple(payload["instance_ids"])
            by_repo.setdefault(repo, set()).add(ids)
        for repo, id_sets in by_repo.items():
            self.assertEqual(len(id_sets), 1, f"Instance IDs differ across methods for {repo}")

    def test_manifests_pin_study_runtime_policy(self):
        expected = {
            "patch_max_turns": 1,
            "patch_apply_repair_retries": 1,
            "patch_retrieval_retry_max": 0,
            "rate_limit_max_retries": 2,
            "rate_limit_initial_delay_s": 0.5,
            "rate_limit_backoff_multiplier": 1.7,
            "rate_limit_max_delay_s": 5.0,
            "rate_limit_jitter_s": 0.2,
            "instance_wall_clock_cap_s": 480,
            "patch_redact_paths_in_issue_text": False,
            "retrieval_redact_paths_in_issue_text": True,
        }
        for entry in self.ledger["entries"]:
            payload = yaml.safe_load(Path(entry["manifest_path"]).read_text(encoding="utf-8"))
            for key, value in expected.items():
                self.assertEqual(
                    payload.get(key), value, f"{entry['manifest_path']} has unexpected {key}"
                )


if __name__ == "__main__":
    unittest.main()
