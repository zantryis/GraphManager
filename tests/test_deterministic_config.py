import json
import tempfile
import unittest
from pathlib import Path

from src.deterministic_config import (
    load_deterministic_config,
    validate_deterministic_config,
)


class DeterministicConfigTests(unittest.TestCase):
    def test_loads_yaml_with_nested_deterministic_block(self):
        config_text = """
deterministic_retrieval:
  seed_k: 8
  depth: 2
  neighbor_cap: 12
  min_return_files: 1
  score_ratio_cutoff: 0.7
  min_score_cutoff: 0.0
  hub_degree_threshold: 20
  hub_penalty_scale: 0.35
  w_sem: 0.35
  w_graph: 0.30
  w_conf: 0.20
  w_hint: 0.10
  w_pen: 0.05
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.yaml"
            path.write_text(config_text, encoding="utf-8")
            loaded = load_deterministic_config(path)

        self.assertEqual(loaded["deterministic_seed_k"], 8)
        self.assertEqual(loaded["deterministic_depth"], 2)
        self.assertAlmostEqual(loaded["deterministic_w_sem"], 0.35)
        self.assertAlmostEqual(sum(loaded[k] for k in (
            "deterministic_w_sem",
            "deterministic_w_graph",
            "deterministic_w_conf",
            "deterministic_w_hint",
            "deterministic_w_pen",
        )), 1.0, places=6)

    def test_loads_json_with_prefixed_keys(self):
        payload = {
            "deterministic_seed_k": 10,
            "deterministic_depth": 3,
            "deterministic_neighbor_cap": 16,
            "deterministic_min_return_files": 1,
            "deterministic_score_ratio_cutoff": 0.62,
            "deterministic_min_score_cutoff": 0.05,
            "deterministic_hub_degree_threshold": 16,
            "deterministic_hub_penalty_scale": 0.2,
            "deterministic_w_sem": 0.4,
            "deterministic_w_graph": 0.2,
            "deterministic_w_conf": 0.2,
            "deterministic_w_hint": 0.1,
            "deterministic_w_pen": 0.1,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_deterministic_config(path)

        self.assertEqual(loaded["deterministic_seed_k"], 10)
        self.assertAlmostEqual(loaded["deterministic_score_ratio_cutoff"], 0.62)

    def test_rejects_weight_sum_not_equal_to_one(self):
        with self.assertRaises(ValueError):
            validate_deterministic_config(
                {
                    "deterministic_w_sem": 0.3,
                    "deterministic_w_graph": 0.3,
                    "deterministic_w_conf": 0.2,
                    "deterministic_w_hint": 0.1,
                    "deterministic_w_pen": 0.05,
                }
            )

    def test_rejects_weight_out_of_range(self):
        with self.assertRaises(ValueError):
            validate_deterministic_config({"deterministic_w_sem": 0.8})


if __name__ == "__main__":
    unittest.main()

