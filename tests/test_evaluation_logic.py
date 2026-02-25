import tempfile
import unittest
from pathlib import Path

from src.evaluation import (
    ALL_METHODS,
    _copy_run_artifacts,
    aggregate_results,
    build_issue_groups,
    compute_metrics,
    group_issues_by_base_commit,
    prepare_issue_text,
    redact_issue_paths,
    validate_commit_context,
)


class EvaluationLogicTests(unittest.TestCase):
    def test_prepare_issue_text_strips_template_sections_and_code_fence_noise(self):
        issue = """
### Checklist
- [x] I have searched existing issues

### Describe the bug
Regression appears in yt_dlp/extractor/dplay.py after latest refactor.

### Logs
```text
Traceback (most recent call last):
  File \"yt_dlp/extractor/dplay.py\", line 42, in run
    raise ValueError("boom")
```

### Environment
- OS: Linux
- Python 3.12
"""
        prepared = prepare_issue_text(issue, redact_paths=True, max_chars=400)
        self.assertIn("Describe the bug", prepared)
        self.assertIn("<PY_PATH>", prepared)
        self.assertNotIn("Checklist", prepared)
        self.assertNotIn("Traceback", prepared)
        self.assertNotIn("Environment", prepared)

    def test_prepare_issue_text_truncates_long_payload(self):
        issue = "Summary line\n\n" + ("log line\n" * 2000)
        prepared = prepare_issue_text(issue, redact_paths=False, max_chars=240)
        self.assertLessEqual(len(prepared), 240)
        self.assertIn("Summary line", prepared)

    def test_redact_issue_paths_replaces_python_paths(self):
        text = "Touch yt_dlp/utils.py and yt_dlp/extractor/dplay.py"
        redacted = redact_issue_paths(text)
        self.assertEqual(redacted.count("<PY_PATH>"), 2)

    def test_group_issues_by_base_commit_preserves_first_seen_order(self):
        issues = [
            {"instance_id": "i1", "base_commit": "aaaa"},
            {"instance_id": "i2", "base_commit": "bbbb"},
            {"instance_id": "i3", "base_commit": "aaaa"},
            {"instance_id": "i4", "base_commit": None},
        ]
        grouped = group_issues_by_base_commit(issues)
        self.assertEqual(
            [(commit, [i["instance_id"] for i in group]) for commit, group in grouped],
            [
                ("aaaa", ["i1", "i3"]),
                ("bbbb", ["i2"]),
                (None, ["i4"]),
            ],
        )

    def test_build_issue_groups_supports_strict_and_same_snapshot_tracks(self):
        issues = [
            {"instance_id": "i1", "base_commit": "aaaa"},
            {"instance_id": "i2", "base_commit": "bbbb"},
            {"instance_id": "i3", "base_commit": "aaaa"},
        ]
        strict_groups = build_issue_groups(
            issues,
            evaluation_track="strict_commit_fidelity",
        )
        same_snapshot_groups = build_issue_groups(
            issues,
            evaluation_track="same_snapshot_amortized",
            snapshot_commit="feedbeef",
        )

        self.assertEqual(
            [(commit, [i["instance_id"] for i in group]) for commit, group in strict_groups],
            [("aaaa", ["i1", "i3"]), ("bbbb", ["i2"])],
        )
        self.assertEqual(len(same_snapshot_groups), 1)
        self.assertEqual(same_snapshot_groups[0][0], "feedbeef")
        self.assertEqual(
            [i["instance_id"] for i in same_snapshot_groups[0][1]],
            ["i1", "i2", "i3"],
        )

    def test_aggregate_results_counts_errors_with_equal_denominator(self):
        success_metrics = {"precision": 1.0, "recall": 0.5, "f1": 2.0 / 3.0}
        success_tokens = {
            "prompt_tokens": 7,
            "candidate_tokens": 3,
            "total_tokens": 10,
            "query_embedding_tokens": 2,
        }
        error_metrics = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        error_tokens = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": 0,
        }

        detailed_results = []
        for issue_idx in range(2):
            issue = {"instance_id": f"i{issue_idx + 1}", "methods": {}}
            for method in ALL_METHODS:
                if issue_idx == 0:
                    issue["methods"][method] = {
                        "metrics": success_metrics,
                        "tokens": success_tokens,
                    }
                else:
                    issue["methods"][method] = {
                        "error": "boom",
                        "metrics": error_metrics,
                        "tokens": error_tokens,
                    }
            detailed_results.append(issue)

        setup_costs = {
            method: {"build_time_s": 1.0, "embedding_tokens": 100}
            for method in ALL_METHODS
        }
        summary = aggregate_results(detailed_results, setup_costs=setup_costs)
        sample = summary["gm_progressive"]

        self.assertEqual(sample["n_issues"], 2)
        self.assertEqual(sample["n_success"], 1)
        self.assertEqual(sample["n_errors"], 1)
        self.assertAlmostEqual(sample["error_rate"], 0.5)
        self.assertAlmostEqual(sample["mean_precision"], 0.5)
        self.assertAlmostEqual(sample["mean_recall"], 0.25)
        self.assertAlmostEqual(sample["mean_f1"], (2.0 / 3.0) / 2.0)
        self.assertEqual(sample["total_llm_tokens"], 10)
        self.assertEqual(sample["total_query_embedding_tokens"], 2)
        self.assertEqual(sample["setup_embedding_tokens"], 100)
        self.assertEqual(sample["total_cost_tokens"], 112)

    def test_aggregate_results_includes_amortization_block(self):
        detailed_results = [
            {
                "instance_id": "i1",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 10,
                            "query_embedding_tokens": 5,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
            {
                "instance_id": "i2",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 6,
                            "query_embedding_tokens": 4,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
        ]
        setup_costs = {
            method: {"build_time_s": 0.1, "embedding_tokens": 50}
            for method in ALL_METHODS
        }

        summary = aggregate_results(
            detailed_results,
            setup_costs=setup_costs,
            track_name="strict_commit_fidelity",
            cache_stats={"lookups": 2, "hits": 1},
        )

        self.assertIn("_amortization", summary)
        amort = summary["_amortization"]
        self.assertEqual(amort["track_name"], "strict_commit_fidelity")
        self.assertAlmostEqual(amort["commit_repeat_ratio"], 0.5)
        self.assertAlmostEqual(amort["cache_hit_rate"], 0.5)
        self.assertIn("pairwise_break_even_n", amort)
        self.assertIn("gm_progressive__vs__rag_progressive", amort["pairwise_break_even_n"])

    def test_aggregate_results_rejects_mixed_track_names(self):
        detailed_results = [
            {
                "instance_id": "i1",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {},
            },
            {
                "instance_id": "i2",
                "base_commit": "abc",
                "track_name": "same_snapshot_amortized",
                "methods": {},
            },
        ]
        setup_costs = {
            method: {"build_time_s": 0.0, "embedding_tokens": 0}
            for method in ALL_METHODS
        }
        with self.assertRaises(ValueError):
            aggregate_results(
                detailed_results,
                setup_costs=setup_costs,
                track_name="strict_commit_fidelity",
            )

    def test_aggregate_results_tracks_stop_reasons_and_token_per_f1_delta(self):
        detailed_results = [
            {
                "instance_id": "i1",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 0.5},
                        "tokens": {
                            "prompt_tokens": 1,
                            "candidate_tokens": 1,
                            "total_tokens": 10,
                            "query_embedding_tokens": 2,
                            "stop_reason": "max_turns" if method.startswith("gm_") else "",
                            "manager_telemetry": {
                                "tool_calls": 2 if method.startswith("gm_") else 0,
                                "stop_reason": "max_turns" if method.startswith("gm_") else "",
                            },
                        },
                    }
                    for method in ALL_METHODS
                },
            }
        ]
        setup_costs = {
            method: {"build_time_s": 0.0, "embedding_tokens": 0}
            for method in ALL_METHODS
        }

        summary = aggregate_results(
            detailed_results,
            setup_costs=setup_costs,
            track_name="strict_commit_fidelity",
        )

        gm = summary["gm_progressive"]
        self.assertEqual(gm["total_runtime_tokens"], 12)
        self.assertAlmostEqual(gm["tokens_per_f1"], 24.0)
        self.assertEqual(gm["stop_reason_counts"]["max_turns"], 1)
        self.assertEqual(summary["rag_baseline"]["token_per_f1_delta_vs_rag_baseline"], 0.0)

    def test_aggregate_results_amortization_uses_evaluated_commit_when_available(self):
        detailed_results = [
            {
                "instance_id": "i1",
                "base_commit": "base-a",
                "used_commit": "snapshot-1",
                "track_name": "same_snapshot_amortized",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "query_embedding_tokens": 0,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
            {
                "instance_id": "i2",
                "base_commit": "base-b",
                "used_commit": "snapshot-1",
                "track_name": "same_snapshot_amortized",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "query_embedding_tokens": 0,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
        ]
        setup_costs = {
            method: {"build_time_s": 0.0, "embedding_tokens": 0}
            for method in ALL_METHODS
        }

        summary = aggregate_results(
            detailed_results,
            setup_costs=setup_costs,
            track_name="same_snapshot_amortized",
        )
        amort = summary["_amortization"]

        self.assertEqual(amort["n_unique_commits"], 1)
        self.assertAlmostEqual(amort["commit_repeat_ratio"], 0.5)
        self.assertAlmostEqual(amort["cache_hit_rate"], 0.5)

    def test_aggregate_results_cache_hit_rate_uses_issue_level_reuse_formula(self):
        detailed_results = [
            {
                "instance_id": "i1",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "query_embedding_tokens": 0,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
            {
                "instance_id": "i2",
                "base_commit": "abc",
                "track_name": "strict_commit_fidelity",
                "methods": {
                    method: {
                        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                        "tokens": {
                            "prompt_tokens": 0,
                            "candidate_tokens": 0,
                            "total_tokens": 0,
                            "query_embedding_tokens": 0,
                        },
                    }
                    for method in ALL_METHODS
                },
            },
        ]
        setup_costs = {
            method: {"build_time_s": 0.0, "embedding_tokens": 0}
            for method in ALL_METHODS
        }
        summary = aggregate_results(
            detailed_results,
            setup_costs=setup_costs,
            track_name="strict_commit_fidelity",
            cache_stats={"lookups": 1, "hits": 0},
        )
        self.assertAlmostEqual(summary["_amortization"]["cache_hit_rate"], 0.5)

    def test_all_methods_includes_deterministic_mode(self):
        self.assertIn("gm_deterministic", ALL_METHODS)
        self.assertIn("repomap_like", ALL_METHODS)
        self.assertIn("agentless_like_localization", ALL_METHODS)

    # ------------------------------------------------------------------ #
    # compute_metrics                                                       #
    # ------------------------------------------------------------------ #

    def test_compute_metrics_empty_gold_returns_zero_not_one(self):
        """Empty gold list (data error) must not silently inflate mean F1 to 1.0."""
        result = compute_metrics([], [])
        self.assertEqual(result["f1"], 0.0)
        self.assertEqual(result["precision"], 0.0)
        self.assertEqual(result["recall"], 0.0)
        self.assertTrue(result.get("skipped_empty_gold", False))

    def test_compute_metrics_empty_predicted_nonempty_gold_returns_zero(self):
        result = compute_metrics([], ["src/foo.py"])
        self.assertEqual(result["f1"], 0.0)
        self.assertFalse(result.get("skipped_empty_gold", False))

    def test_compute_metrics_exact_match_returns_one(self):
        result = compute_metrics(["src/foo.py"], ["src/foo.py"])
        self.assertAlmostEqual(result["f1"], 1.0)
        self.assertFalse(result.get("skipped_empty_gold", False))

    def test_compute_metrics_nonempty_predicted_empty_gold_returns_zero_with_flag(self):
        """Predicted files with empty gold is a data error — flag it."""
        result = compute_metrics(["src/foo.py"], [])
        self.assertEqual(result["f1"], 0.0)
        self.assertTrue(result.get("skipped_empty_gold", False))

    # ------------------------------------------------------------------ #
    # validate_commit_context                                              #
    # ------------------------------------------------------------------ #

    def _valid_setup_costs(self, tokens: int = 200) -> dict:
        return {method: {"embedding_tokens": tokens, "build_time_s": 1.0} for method in ALL_METHODS}

    def test_validate_commit_context_passes_on_valid_context(self):
        context = {
            "graph_file_paths": {"some/file.py"},
            "bm25_file_paths": {"some/file.py"},
            "setup_costs": self._valid_setup_costs(200),
        }
        validate_commit_context(context)  # must not raise

    def test_validate_commit_context_raises_on_empty_graph_index(self):
        setup_costs = self._valid_setup_costs(200)
        setup_costs["gm_progressive"]["embedding_tokens"] = 0
        setup_costs["gm_baseline"]["embedding_tokens"] = 0
        setup_costs["gm_deterministic"]["embedding_tokens"] = 0
        context = {
            "graph_file_paths": set(),
            "setup_costs": setup_costs,
        }
        with self.assertRaises(ValueError) as cm:
            validate_commit_context(context)
        self.assertIn("graph", str(cm.exception).lower())

    def test_validate_commit_context_raises_on_empty_rag_function_index(self):
        setup_costs = self._valid_setup_costs(200)
        setup_costs["rag_progressive"]["embedding_tokens"] = 0
        setup_costs["rag_baseline"]["embedding_tokens"] = 0
        setup_costs["raw_rag_function"]["embedding_tokens"] = 0
        setup_costs["agentless_like_localization"]["embedding_tokens"] = 0
        context = {
            "graph_file_paths": {"some/file.py"},
            "setup_costs": setup_costs,
        }
        with self.assertRaises(ValueError) as cm:
            validate_commit_context(context)
        self.assertIn("rag", str(cm.exception).lower())

    def test_validate_commit_context_raises_on_empty_rag_fixed_index(self):
        setup_costs = self._valid_setup_costs(200)
        setup_costs["raw_rag_fixed"]["embedding_tokens"] = 0
        context = {
            "graph_file_paths": {"some/file.py"},
            "setup_costs": setup_costs,
        }
        with self.assertRaises(ValueError) as cm:
            validate_commit_context(context)
        self.assertIn("rag", str(cm.exception).lower())

    def test_validate_commit_context_raises_with_source_prefix_hint(self):
        """Error message should mention source_prefixes to guide the user."""
        setup_costs = self._valid_setup_costs(0)
        context = {
            "graph_file_paths": set(),
            "setup_costs": setup_costs,
        }
        with self.assertRaises(ValueError) as cm:
            validate_commit_context(context)
        self.assertIn("source_prefix", str(cm.exception).lower())

    def test_validate_commit_context_supports_required_methods_subset(self):
        setup_costs = self._valid_setup_costs(0)
        setup_costs["gm_deterministic"]["embedding_tokens"] = 200
        setup_costs["gm_progressive"]["embedding_tokens"] = 200
        context = {
            "graph_file_paths": {"some/file.py"},
            "setup_costs": setup_costs,
        }
        validate_commit_context(
            context,
            required_methods=("gm_deterministic",),
        )

    def test_validate_commit_context_subset_still_checks_required_index(self):
        setup_costs = self._valid_setup_costs(0)
        context = {
            "graph_file_paths": set(),
            "setup_costs": setup_costs,
        }
        with self.assertRaises(ValueError):
            validate_commit_context(
                context,
                required_methods=("gm_deterministic",),
            )

    def test_validate_commit_context_repomap_allows_zero_embedding_tokens(self):
        setup_costs = self._valid_setup_costs(0)
        context = {
            "graph_file_paths": {"some/file.py"},
            "setup_costs": setup_costs,
        }
        validate_commit_context(
            context,
            required_methods=("repomap_like",),
        )

    def test_copy_run_artifacts_skips_missing_graph(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / "runs" / "run1"
            run_path.mkdir(parents=True)
            base_results = root / "results"
            base_results.mkdir(parents=True)

            (run_path / "detailed_results.json").write_text("{}", encoding="utf-8")
            (run_path / "summary.json").write_text("{}", encoding="utf-8")

            _copy_run_artifacts(
                run_path=run_path,
                base_results_path=base_results,
                create_run_subdir=True,
            )

            self.assertTrue((base_results / "latest" / "summary.json").exists())
            self.assertTrue((base_results / "latest" / "detailed_results.json").exists())
            self.assertFalse((base_results / "latest" / "graph.json").exists())

    def test_copy_run_artifacts_copies_graph_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / "runs" / "run1"
            run_path.mkdir(parents=True)
            base_results = root / "results"
            base_results.mkdir(parents=True)

            (run_path / "graph.json").write_text("{}", encoding="utf-8")
            (run_path / "detailed_results.json").write_text("{}", encoding="utf-8")
            (run_path / "summary.json").write_text("{}", encoding="utf-8")

            _copy_run_artifacts(
                run_path=run_path,
                base_results_path=base_results,
                create_run_subdir=True,
            )

            self.assertTrue((base_results / "latest" / "graph.json").exists())
            self.assertTrue((base_results / "graph.json").exists())


if __name__ == "__main__":
    unittest.main()
