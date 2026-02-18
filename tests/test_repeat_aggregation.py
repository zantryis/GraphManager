import unittest

from run_experiment import aggregate_repeat_summaries


class RepeatAggregationTests(unittest.TestCase):
    def test_repeat_aggregate_includes_pairwise_bootstrap_ci_and_gates(self):
        summaries = [
            {
                "gm_progressive": {"mean_f1": 0.70, "total_cost_tokens": 1000},
                "rag_progressive": {"mean_f1": 0.65, "total_cost_tokens": 1200},
                "_meta": {"run_id": "r1"},
            },
            {
                "gm_progressive": {"mean_f1": 0.68, "total_cost_tokens": 1050},
                "rag_progressive": {"mean_f1": 0.66, "total_cost_tokens": 1210},
                "_meta": {"run_id": "r2"},
            },
            {
                "gm_progressive": {"mean_f1": 0.72, "total_cost_tokens": 990},
                "rag_progressive": {"mean_f1": 0.64, "total_cost_tokens": 1190},
                "_meta": {"run_id": "r3"},
            },
        ]

        aggregate = aggregate_repeat_summaries(summaries)

        self.assertIn("pairwise_deltas", aggregate)
        key = "gm_progressive__minus__rag_progressive__mean_f1"
        self.assertIn(key, aggregate["pairwise_deltas"])
        payload = aggregate["pairwise_deltas"][key]
        self.assertIn("mean_delta", payload)
        self.assertIn("bootstrap_ci_95", payload)
        self.assertEqual(len(payload["bootstrap_ci_95"]), 2)
        self.assertTrue(aggregate["gates"]["min_repeats_met"])
        self.assertTrue(aggregate["gates"]["pairwise_bootstrap_available"])

    def test_repeat_aggregate_includes_amortization_rollup(self):
        summaries = [
            {
                "_meta": {"run_id": "r1"},
                "_amortization": {
                    "track_name": "same_snapshot_amortized",
                    "n_issues": 8,
                    "n_unique_commits": 1,
                    "commit_repeat_ratio": 0.875,
                    "cache_hit_rate": 0.875,
                },
            },
            {
                "_meta": {"run_id": "r2"},
                "_amortization": {
                    "track_name": "same_snapshot_amortized",
                    "n_issues": 8,
                    "n_unique_commits": 1,
                    "commit_repeat_ratio": 0.875,
                    "cache_hit_rate": 0.875,
                },
            },
        ]

        aggregate = aggregate_repeat_summaries(summaries)
        self.assertIn("_amortization", aggregate)
        amort = aggregate["_amortization"]
        self.assertEqual(amort["track_name"], "same_snapshot_amortized")
        self.assertEqual(amort["n_issues"], 8)
        self.assertEqual(amort["n_unique_commits"], 1)
        self.assertAlmostEqual(amort["commit_repeat_ratio"], 0.875)
        self.assertAlmostEqual(amort["cache_hit_rate"], 0.875)


if __name__ == "__main__":
    unittest.main()
