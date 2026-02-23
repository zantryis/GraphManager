import unittest

from src.deterministic_tuning import (
    build_candidate_leaderboard,
    build_selection_artifact,
    passes_stability_guard,
    sample_candidate_configs,
    select_best_candidate,
)


class DeterministicTuningTests(unittest.TestCase):
    def test_sample_candidate_configs_is_deterministic(self):
        a = sample_candidate_configs(5, seed=17)
        b = sample_candidate_configs(5, seed=17)
        self.assertEqual(a, b)
        for row in a:
            total = (
                row["deterministic_w_sem"]
                + row["deterministic_w_graph"]
                + row["deterministic_w_conf"]
                + row["deterministic_w_hint"]
                + row["deterministic_w_pen"]
            )
            self.assertAlmostEqual(total, 1.0, places=6)
            self.assertLessEqual(max(
                row["deterministic_w_sem"],
                row["deterministic_w_graph"],
                row["deterministic_w_conf"],
                row["deterministic_w_hint"],
                row["deterministic_w_pen"],
            ), 0.7)

    def test_passes_stability_guard(self):
        self.assertTrue(
            passes_stability_guard(
                holdout_scores={"psf/requests": 0.41, "pytest-dev/pytest": 0.44},
                baseline_scores={"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
                max_drop=0.03,
            )
        )
        self.assertFalse(
            passes_stability_guard(
                holdout_scores={"psf/requests": 0.37, "pytest-dev/pytest": 0.44},
                baseline_scores={"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
                max_drop=0.03,
            )
        )

    def test_select_best_candidate_uses_tie_breakers(self):
        results = [
            {
                "config_id": "cfg-1",
                "train_mean_f1": 0.60,
                "train_f1_std": 0.02,
                "train_runtime_tokens": 3000,
                "holdout_scores": {"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
            },
            {
                "config_id": "cfg-2",
                "train_mean_f1": 0.60,
                "train_f1_std": 0.01,
                "train_runtime_tokens": 3500,
                "holdout_scores": {"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
            },
        ]
        selected = select_best_candidate(
            candidate_results=results,
            baseline_scores={"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
            max_drop=0.03,
        )
        self.assertEqual(selected["config_id"], "cfg-2")

    def test_build_candidate_leaderboard_enriches_and_orders(self):
        leaderboard = build_candidate_leaderboard(
            candidate_results=[
                {
                    "config_id": "cfg-1",
                    "train_mean_f1": 0.55,
                    "train_f1_std": 0.02,
                    "train_runtime_tokens": 2000,
                    "holdout_scores": {"psf/requests": 0.42, "pytest-dev/pytest": 0.44},
                },
                {
                    "config_id": "cfg-2",
                    "train_mean_f1": 0.60,
                    "train_f1_std": 0.03,
                    "train_runtime_tokens": 1800,
                    "holdout_scores": {"psf/requests": 0.35, "pytest-dev/pytest": 0.44},
                },
            ],
            baseline_scores={"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
            max_drop=0.03,
        )
        self.assertEqual(leaderboard[0]["config_id"], "cfg-2")
        self.assertFalse(leaderboard[0]["passes_stability_guard"])
        self.assertTrue(leaderboard[1]["passes_stability_guard"])
        self.assertAlmostEqual(leaderboard[1]["holdout_deltas"]["psf/requests"], 0.0)

    def test_build_selection_artifact_selects_guard_passing_top_candidate(self):
        artifact = build_selection_artifact(
            candidate_results=[
                {
                    "config_id": "cfg-1",
                    "config": {"deterministic_seed_k": 8},
                    "train_mean_f1": 0.61,
                    "train_f1_std": 0.03,
                    "train_runtime_tokens": 2200,
                    "holdout_scores": {"psf/requests": 0.37, "pytest-dev/pytest": 0.45},
                },
                {
                    "config_id": "cfg-2",
                    "config": {"deterministic_seed_k": 10},
                    "train_mean_f1": 0.60,
                    "train_f1_std": 0.01,
                    "train_runtime_tokens": 2100,
                    "holdout_scores": {"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
                },
            ],
            baseline_scores={"psf/requests": 0.42, "pytest-dev/pytest": 0.45},
            max_drop=0.03,
        )
        self.assertEqual(artifact["selected"]["config_id"], "cfg-2")
        self.assertEqual(artifact["n_candidates"], 2)
        self.assertEqual(artifact["n_guard_passing"], 1)
        self.assertTrue(any(not row["passes_stability_guard"] for row in artifact["leaderboard"]))


if __name__ == "__main__":
    unittest.main()
