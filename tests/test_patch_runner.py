"""Tests for run_patch.py manifest loading and dry-run pipeline."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx


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
        supported = {"gm_progressive", "gm_deterministic", "rag_progressive", "oracle", "none"}
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
        self.assertIn("instance_wall_clock_cap_s", data)
        self.assertIn("rate_limit_max_retries", data)
        self.assertIn("patch_redact_paths_in_issue_text", data)
        self.assertIn("retrieval_redact_paths_in_issue_text", data)


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

    def test_run_with_rate_limit_backoff_honors_deadline(self):
        from run_patch import _run_with_rate_limit_backoff

        calls = {"n": 0}

        def should_not_run():
            calls["n"] += 1
            return "ok"

        with self.assertRaises(TimeoutError):
            _run_with_rate_limit_backoff(
                should_not_run,
                label="retrieval",
                deadline_monotonic=time.monotonic() - 0.01,
            )
        self.assertEqual(calls["n"], 0)

    def test_run_with_rate_limit_backoff_times_out_blocking_callable(self):
        from run_patch import _run_with_rate_limit_backoff

        def slow_call():
            time.sleep(0.2)
            return "ok"

        with self.assertRaises(TimeoutError):
            _run_with_rate_limit_backoff(
                slow_call,
                label="patch",
                max_retries=0,
                deadline_monotonic=time.monotonic() + 0.05,
            )


class RetrievalMethodTests(unittest.TestCase):
    def _make_graph(self):
        graph = nx.Graph()
        graph.add_node("requests/models.py", type="file")
        graph.add_node("requests/sessions.py", type="file")
        graph.add_node("README.md", type="file")
        return graph

    def test_run_retrieval_none_returns_empty_files(self):
        from run_patch import _run_retrieval

        files, tokens = _run_retrieval(
            {"problem_statement": "issue text", "patch": ""},
            graph=self._make_graph(),
            graph_index=None,
            rag_index=None,
            client=None,
            method="none",
            manager_model="unused",
            manager_max_turns=1,
            deterministic_config={},
        )

        self.assertEqual(files, [])
        self.assertEqual(tokens.get("total_tokens"), 0)
        self.assertEqual(tokens.get("stop_reason"), "no_retrieval")

    def test_run_retrieval_oracle_uses_patch_diff_files(self):
        from run_patch import _run_retrieval

        issue = {
            "problem_statement": "issue text",
            "patch": (
                "diff --git a/requests/models.py b/requests/models.py\n"
                "@@ -1,1 +1,1 @@\n"
                "-x=1\n"
                "+x=2\n"
                "diff --git a/docs/changelog.rst b/docs/changelog.rst\n"
                "@@ -1,1 +1,1 @@\n"
                "-a\n"
                "+b\n"
            ),
        }
        files, tokens = _run_retrieval(
            issue,
            graph=self._make_graph(),
            graph_index=None,
            rag_index=None,
            client=None,
            method="oracle",
            manager_model="unused",
            manager_max_turns=1,
            deterministic_config={},
            repo_dir="/tmp/unused",
            valid_file_paths={"requests/models.py", "requests/sessions.py"},
        )

        self.assertEqual(files, ["requests/models.py"])
        self.assertEqual(tokens.get("total_tokens"), 0)
        self.assertEqual(tokens.get("stop_reason"), "oracle")

    def test_run_retrieval_agentic_cold_start_is_supported(self):
        from run_patch import _run_retrieval

        with patch("src.agentic_cold_start.AgenticColdStartAgent") as agent_cls:
            agent = agent_cls.return_value
            agent.find_relevant_files.return_value = (
                ["requests/models.py", "requests/sessions.py"],
                {"total_tokens": 123, "stop_reason": "sufficient_confidence"},
            )

            files, tokens = _run_retrieval(
                {"problem_statement": "issue text", "patch": ""},
                graph=None,
                graph_index=None,
                rag_index=None,
                bm25_index=None,
                client=object(),
                method="agentic_cold_start",
                manager_model="gemini-test",
                manager_max_turns=3,
                deterministic_config={},
                repo_dir="/tmp/repo",
                include_prefixes=("requests",),
                valid_file_paths={"requests/models.py", "requests/sessions.py"},
            )

        self.assertEqual(files, ["requests/models.py", "requests/sessions.py"])
        self.assertEqual(tokens.get("total_tokens"), 123)
        agent_cls.assert_called_once()

    def test_run_retrieval_raw_rag_function_is_supported(self):
        from run_patch import _run_retrieval

        with patch("src.rag_baseline.RawRAG") as raw_cls:
            raw_agent = raw_cls.return_value
            raw_agent.find_relevant_files.return_value = (
                ["requests/models.py", "requests/sessions.py"],
                {"query_embedding_tokens": 12, "total_tokens": 0},
            )

            files, tokens = _run_retrieval(
                {"problem_statement": "issue text", "patch": ""},
                graph=None,
                graph_index=None,
                rag_index=object(),
                bm25_index=None,
                client=object(),
                method="raw_rag_function",
                manager_model="gemini-test",
                manager_max_turns=3,
                deterministic_config={},
                repo_dir="/tmp/repo",
                valid_file_paths={"requests/models.py", "requests/sessions.py"},
            )

        self.assertEqual(files, ["requests/models.py", "requests/sessions.py"])
        self.assertEqual(tokens.get("query_embedding_tokens"), 12)
        raw_cls.assert_called_once()

    def test_run_retrieval_rag_baseline_is_supported(self):
        from run_patch import _run_retrieval

        with patch("src.rag_baseline.RAGAgent") as rag_cls:
            rag_agent = rag_cls.return_value
            rag_agent.find_relevant_files.return_value = (
                ["requests/models.py"],
                {"total_tokens": 77, "tool_calls": 2},
            )

            files, tokens = _run_retrieval(
                {"problem_statement": "issue text", "patch": ""},
                graph=None,
                graph_index=None,
                rag_index=object(),
                bm25_index=None,
                client=object(),
                method="rag_baseline",
                manager_model="gemini-test",
                manager_max_turns=3,
                deterministic_config={},
                repo_dir="/tmp/repo",
                valid_file_paths={"requests/models.py"},
            )

        self.assertEqual(files, ["requests/models.py"])
        self.assertEqual(tokens.get("total_tokens"), 77)
        rag_cls.assert_called_once()
        self.assertEqual(rag_cls.call_args.kwargs.get("retrieval_mode"), "baseline")

    def test_run_retrieval_repomap_like_is_supported(self):
        from run_patch import _run_retrieval

        with patch("src.repomap_like.RepoMapLikeRetriever") as retriever_cls:
            retriever = retriever_cls.return_value
            retriever.find_relevant_files.return_value = (
                ["requests/models.py"],
                {"total_tokens": 0, "repomap_meta": {"map_tokens_used": 100}},
            )
            files, tokens = _run_retrieval(
                {"problem_statement": "issue text", "patch": ""},
                graph=self._make_graph(),
                graph_index=None,
                rag_index=None,
                bm25_index=None,
                client=object(),
                method="repomap_like",
                manager_model="gemini-test",
                manager_max_turns=3,
                deterministic_config={},
                repo_dir="/tmp/repo",
                valid_file_paths={"requests/models.py"},
                repomap_config={"top_k_files": 1},
            )

        self.assertEqual(files, ["requests/models.py"])
        self.assertEqual(tokens.get("total_tokens"), 0)
        retriever_cls.assert_called_once()

    def test_run_retrieval_agentless_like_is_supported(self):
        from run_patch import _run_retrieval

        with patch("src.agentless_like_localization.AgentlessLikeLocalizer") as retriever_cls:
            retriever = retriever_cls.return_value
            retriever.find_relevant_files.return_value = (
                ["requests/models.py", "requests/sessions.py"],
                {"total_tokens": 99, "agentless_like_meta": {"stage1_candidate_pool_size": 10}},
            )
            files, tokens = _run_retrieval(
                {"problem_statement": "issue text", "patch": ""},
                graph=self._make_graph(),
                graph_index=None,
                rag_index=object(),
                bm25_index=None,
                client=object(),
                method="agentless_like_localization",
                manager_model="gemini-test",
                manager_max_turns=3,
                deterministic_config={},
                repo_dir="/tmp/repo",
                valid_file_paths={"requests/models.py", "requests/sessions.py"},
                agentless_like_config={"stage2_enabled": False},
            )

        self.assertEqual(files, ["requests/models.py", "requests/sessions.py"])
        self.assertEqual(tokens.get("total_tokens"), 99)
        retriever_cls.assert_called_once()


class RetrievalFileCapTests(unittest.TestCase):
    def test_cap_retrieved_files_applies_global_limit(self):
        from run_patch import _cap_retrieved_files

        files = [f"pkg/f{i}.py" for i in range(10)]
        capped, pre_count, post_count = _cap_retrieved_files(files, max_files=6)

        self.assertEqual(pre_count, 10)
        self.assertEqual(post_count, 6)
        self.assertEqual(capped, [f"pkg/f{i}.py" for i in range(6)])

    def test_cap_retrieved_files_none_disables_cap(self):
        from run_patch import _cap_retrieved_files

        files = [f"pkg/f{i}.py" for i in range(10)]
        capped, pre_count, post_count = _cap_retrieved_files(files, max_files=None)

        self.assertEqual(pre_count, 10)
        self.assertEqual(post_count, 10)
        self.assertEqual(capped, files)


class HarnessRunIdTests(unittest.TestCase):
    def test_build_harness_run_id_is_deterministic(self):
        from run_patch import _build_harness_run_id

        run_id_1 = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_a"),
        )
        run_id_2 = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_a"),
        )
        self.assertEqual(run_id_1, run_id_2)

    def test_build_harness_run_id_separates_methods(self):
        from run_patch import _build_harness_run_id

        gm = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_a"),
        )
        bm25 = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="bm25",
            results_path=Path("/tmp/run_a"),
        )
        self.assertNotEqual(gm, bm25)

    def test_build_harness_run_id_separates_results_paths(self):
        from run_patch import _build_harness_run_id

        first = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_a"),
        )
        second = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_b"),
        )
        self.assertNotEqual(first, second)

    def test_build_harness_run_id_honors_existing_value(self):
        from run_patch import _build_harness_run_id

        existing = "graphmanager_existing_123"
        run_id = _build_harness_run_id(
            run_id="20260224_010101",
            retrieval_method="gm_progressive",
            results_path=Path("/tmp/run_a"),
            existing_harness_run_id=existing,
        )
        self.assertEqual(run_id, existing)


class RunOutputDirAllocationTests(unittest.TestCase):
    def test_allocate_run_output_dir_uses_timestamp_when_available(self):
        from run_patch import _allocate_run_output_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("run_patch.time.strftime", return_value="20260224_123000"):
                run_id, run_path = _allocate_run_output_dir(tmpdir)

            self.assertEqual(run_id, "20260224_123000")
            self.assertTrue(run_path.exists())
            self.assertEqual(run_path.name, "20260224_123000")

    def test_allocate_run_output_dir_suffixes_on_collision(self):
        from run_patch import _allocate_run_output_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            patch_root = Path(tmpdir) / "patch_runs"
            patch_root.mkdir(parents=True, exist_ok=True)
            (patch_root / "20260224_123000").mkdir()
            (patch_root / "20260224_123000_01").mkdir()

            with patch("run_patch.time.strftime", return_value="20260224_123000"):
                run_id, run_path = _allocate_run_output_dir(tmpdir)

            self.assertEqual(run_id, "20260224_123000_02")
            self.assertTrue(run_path.exists())
            self.assertEqual(run_path.name, "20260224_123000_02")

    def test_allocate_run_output_dir_retries_when_mkdir_races(self):
        from run_patch import _allocate_run_output_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            original_mkdir = Path.mkdir
            race_triggered = {"value": False}

            def flaky_mkdir(path_obj, *args, **kwargs):
                if (
                    not race_triggered["value"]
                    and path_obj.name == "20260224_123000"
                    and path_obj.parent.name == "patch_runs"
                    and kwargs.get("exist_ok") is False
                ):
                    race_triggered["value"] = True
                    raise FileExistsError("simulated concurrent mkdir race")
                return original_mkdir(path_obj, *args, **kwargs)

            with patch("run_patch.time.strftime", return_value="20260224_123000"), patch(
                "pathlib.Path.mkdir",
                autospec=True,
                side_effect=flaky_mkdir,
            ):
                run_id, run_path = _allocate_run_output_dir(tmpdir)

            self.assertTrue(race_triggered["value"])
            self.assertNotEqual(run_id, "20260224_123000")
            self.assertTrue(run_id.startswith("20260224_123000_"))
            self.assertTrue(run_path.exists())
            self.assertEqual(run_path.name, run_id)


class MethodScopedIndexBuildTests(unittest.TestCase):
    class _FakeGraphBuilder:
        init_calls = 0
        build_calls = 0

        def __init__(self, repo_dir, include_prefixes=None):
            MethodScopedIndexBuildTests._FakeGraphBuilder.init_calls += 1
            self.repo_dir = repo_dir
            self.include_prefixes = include_prefixes

        def build(self):
            MethodScopedIndexBuildTests._FakeGraphBuilder.build_calls += 1
            graph = nx.Graph()
            graph.add_node("requests/models.py", type="file")
            return graph

    class _FakeGraphIndex:
        init_calls = 0
        build_calls = 0

        def __init__(self, graph, client):
            MethodScopedIndexBuildTests._FakeGraphIndex.init_calls += 1
            self.graph = graph
            self.client = client
            self.embedding_tokens_estimate = 111

        def build(self):
            MethodScopedIndexBuildTests._FakeGraphIndex.build_calls += 1

    class _FakeRAGIndex:
        init_calls = 0
        build_calls = 0

        def __init__(self, repo_dir, client, chunk_strategy="function", include_prefixes=None):
            MethodScopedIndexBuildTests._FakeRAGIndex.init_calls += 1
            self.repo_dir = repo_dir
            self.client = client
            self.chunk_strategy = chunk_strategy
            self.include_prefixes = include_prefixes
            self.embedding_tokens_estimate = 222
            self.chunks = [{"file": "requests/models.py"}]

        def build(self):
            MethodScopedIndexBuildTests._FakeRAGIndex.build_calls += 1

    def setUp(self):
        MethodScopedIndexBuildTests._FakeGraphBuilder.init_calls = 0
        MethodScopedIndexBuildTests._FakeGraphBuilder.build_calls = 0
        MethodScopedIndexBuildTests._FakeGraphIndex.init_calls = 0
        MethodScopedIndexBuildTests._FakeGraphIndex.build_calls = 0
        MethodScopedIndexBuildTests._FakeRAGIndex.init_calls = 0
        MethodScopedIndexBuildTests._FakeRAGIndex.build_calls = 0

    def test_method_scoped_context_gm_builds_graph_only(self):
        from run_patch import _build_method_scoped_commit_context

        validated = {"count": 0}

        def validate_fn(_context, required_methods=None):
            validated["count"] += 1
            self.assertEqual(required_methods, ("gm_progressive",))

        context = _build_method_scoped_commit_context(
            retrieval_method="gm_progressive",
            repo_dir="/tmp/repo",
            prefixes=("requests",),
            client=object(),
            graph_builder_cls=self._FakeGraphBuilder,
            graph_index_cls=self._FakeGraphIndex,
            rag_index_cls=self._FakeRAGIndex,
            validate_commit_context_fn=validate_fn,
        )

        self.assertEqual(self._FakeGraphBuilder.build_calls, 1)
        self.assertEqual(self._FakeGraphIndex.build_calls, 1)
        self.assertEqual(self._FakeRAGIndex.build_calls, 0)
        self.assertIsNotNone(context["graph"])
        self.assertIsNotNone(context["graph_index"])
        self.assertIsNone(context["rag_index"])
        self.assertEqual(context["retrieval_setup_tokens"], 111)
        self.assertEqual(context["setup_tokens_graph_built"], 111)
        self.assertEqual(context["setup_tokens_rag_built"], 0)
        self.assertEqual(context["setup_tokens_method_accounted"], 111)
        self.assertEqual(validated["count"], 1)

    def test_method_scoped_context_rag_builds_rag_only(self):
        from run_patch import _build_method_scoped_commit_context

        validated = {"count": 0}

        def validate_fn(_context, required_methods=None):
            validated["count"] += 1
            self.assertEqual(required_methods, ("rag_progressive",))

        context = _build_method_scoped_commit_context(
            retrieval_method="rag_progressive",
            repo_dir="/tmp/repo",
            prefixes=("requests",),
            client=object(),
            graph_builder_cls=self._FakeGraphBuilder,
            graph_index_cls=self._FakeGraphIndex,
            rag_index_cls=self._FakeRAGIndex,
            validate_commit_context_fn=validate_fn,
        )

        self.assertEqual(self._FakeGraphBuilder.build_calls, 0)
        self.assertEqual(self._FakeGraphIndex.build_calls, 0)
        self.assertEqual(self._FakeRAGIndex.build_calls, 1)
        self.assertIsNone(context["graph"])
        self.assertIsNone(context["graph_index"])
        self.assertIsNotNone(context["rag_index"])
        self.assertEqual(context["retrieval_setup_tokens"], 222)
        self.assertEqual(context["setup_tokens_graph_built"], 0)
        self.assertEqual(context["setup_tokens_rag_built"], 222)
        self.assertEqual(context["setup_tokens_method_accounted"], 222)
        self.assertEqual(validated["count"], 1)

    def test_method_scoped_context_none_and_oracle_build_neither(self):
        from run_patch import _build_method_scoped_commit_context

        for method in ("none", "oracle"):
            context = _build_method_scoped_commit_context(
                retrieval_method=method,
                repo_dir="/tmp/repo",
                prefixes=("requests",),
                client=object(),
                graph_builder_cls=self._FakeGraphBuilder,
                graph_index_cls=self._FakeGraphIndex,
                rag_index_cls=self._FakeRAGIndex,
                validate_commit_context_fn=lambda _ctx, required_methods=None: None,
            )
            self.assertEqual(context["retrieval_setup_tokens"], 0)
            self.assertEqual(context["setup_tokens_graph_built"], 0)
            self.assertEqual(context["setup_tokens_rag_built"], 0)
            self.assertEqual(context["setup_tokens_method_accounted"], 0)

        self.assertEqual(self._FakeGraphBuilder.build_calls, 0)
        self.assertEqual(self._FakeGraphIndex.build_calls, 0)
        self.assertEqual(self._FakeRAGIndex.build_calls, 0)

    def test_method_scoped_context_repomap_builds_graph_without_index(self):
        from run_patch import _build_method_scoped_commit_context

        context = _build_method_scoped_commit_context(
            retrieval_method="repomap_like",
            repo_dir="/tmp/repo",
            prefixes=("requests",),
            client=object(),
            graph_builder_cls=self._FakeGraphBuilder,
            graph_index_cls=self._FakeGraphIndex,
            rag_index_cls=self._FakeRAGIndex,
            validate_commit_context_fn=lambda _ctx, required_methods=None: None,
        )

        self.assertEqual(self._FakeGraphBuilder.build_calls, 1)
        self.assertEqual(self._FakeGraphIndex.build_calls, 0)
        self.assertEqual(self._FakeRAGIndex.build_calls, 0)
        self.assertIsNotNone(context["graph"])
        self.assertIsNone(context["graph_index"])
        self.assertEqual(context["retrieval_setup_tokens"], 0)
        self.assertEqual(context["setup_tokens_method_accounted"], 0)

    def test_method_scoped_context_gm_passes_graph_file_paths_to_validate(self):
        """Regression: validate_commit_context_fn must receive actual graph_file_paths,
        not an empty set. Bug: line 594 previously passed set() unconditionally."""
        from run_patch import _build_method_scoped_commit_context

        captured = {}

        def validate_fn(context, required_methods=None):
            captured["graph_file_paths"] = context.get("graph_file_paths")

        for method in ("gm_progressive", "gm_deterministic", "gm_baseline"):
            captured.clear()
            MethodScopedIndexBuildTests._FakeGraphBuilder.build_calls = 0
            MethodScopedIndexBuildTests._FakeGraphIndex.build_calls = 0
            _build_method_scoped_commit_context(
                retrieval_method=method,
                repo_dir="/tmp/repo",
                prefixes=("requests",),
                client=object(),
                graph_builder_cls=self._FakeGraphBuilder,
                graph_index_cls=self._FakeGraphIndex,
                rag_index_cls=self._FakeRAGIndex,
                validate_commit_context_fn=validate_fn,
            )
            # _FakeGraphBuilder.build() adds "requests/models.py" as a file node,
            # so validate_fn must see a non-empty set containing that path.
            self.assertIn(
                "requests/models.py",
                captured.get("graph_file_paths", set()),
                f"{method}: validate_fn received empty graph_file_paths (bug regression)",
            )

    def test_method_scoped_context_agentless_builds_graph_and_rag(self):
        from run_patch import _build_method_scoped_commit_context

        validated = {"count": 0}

        def validate_fn(_context, required_methods=None):
            validated["count"] += 1
            self.assertEqual(required_methods, ("rag_progressive",))

        context = _build_method_scoped_commit_context(
            retrieval_method="agentless_like_localization",
            repo_dir="/tmp/repo",
            prefixes=("requests",),
            client=object(),
            graph_builder_cls=self._FakeGraphBuilder,
            graph_index_cls=self._FakeGraphIndex,
            rag_index_cls=self._FakeRAGIndex,
            validate_commit_context_fn=validate_fn,
        )

        self.assertEqual(self._FakeGraphBuilder.build_calls, 1)
        self.assertEqual(self._FakeGraphIndex.build_calls, 0)
        self.assertEqual(self._FakeRAGIndex.build_calls, 1)
        self.assertIsNotNone(context["graph"])
        self.assertIsNotNone(context["rag_index"])
        self.assertEqual(context["retrieval_setup_tokens"], 222)
        self.assertEqual(context["setup_tokens_rag_built"], 222)
        self.assertEqual(validated["count"], 1)


class ModelSelectionTests(unittest.TestCase):
    def test_resolve_model_config_uses_defaults(self):
        from run_patch import _resolve_model_config

        manager_model, patch_model = _resolve_model_config({})
        self.assertEqual(manager_model, "gemini-3-flash-preview")
        self.assertEqual(patch_model, "gemini-3-flash-preview")

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


class PatchCostSummaryTests(unittest.TestCase):
    def test_compute_cost_summary_fields_with_resolved(self):
        from run_patch import _compute_cost_summary_fields

        per_instance = [
            {"retrieval_tokens": {"total_tokens": 10}, "patch_tokens": {"total_tokens": 20}},
            {"retrieval_tokens": {"total_tokens": 5}, "patch_tokens": {"total_tokens": 15}},
        ]
        harness_results = {
            "n_resolved": 2,
            "resolved_instances": ["i1", "i2"],
        }

        fields = _compute_cost_summary_fields(
            per_instance_results=per_instance,
            retrieval_setup_tokens=50,
            harness_results=harness_results,
        )

        self.assertEqual(fields["retrieval_setup_tokens"], 50)
        self.assertEqual(fields["retrieval_runtime_tokens"], 15)
        self.assertEqual(fields["patch_runtime_tokens"], 35)
        self.assertEqual(fields["total_cost_tokens"], 100)
        self.assertEqual(fields["n_resolved"], 2)
        self.assertEqual(fields["resolved_instances"], ["i1", "i2"])
        self.assertAlmostEqual(fields["cost_per_resolved_issue"], 50.0, places=6)

    def test_compute_cost_summary_fields_with_zero_resolved(self):
        from run_patch import _compute_cost_summary_fields

        per_instance = [
            {"retrieval_tokens": {"total_tokens": 8}, "patch_tokens": {"total_tokens": 12}},
        ]
        harness_results = {
            "n_resolved": 0,
            "resolved_instances": [],
        }

        fields = _compute_cost_summary_fields(
            per_instance_results=per_instance,
            retrieval_setup_tokens=20,
            harness_results=harness_results,
        )

        self.assertEqual(fields["total_cost_tokens"], 40)
        self.assertEqual(fields["n_resolved"], 0)
        self.assertIsNone(fields["cost_per_resolved_issue"])

    def test_compute_cost_summary_fields_includes_split_setup_fields(self):
        from run_patch import _compute_cost_summary_fields

        fields = _compute_cost_summary_fields(
            per_instance_results=[
                {"retrieval_tokens": {"total_tokens": 2}, "patch_tokens": {"total_tokens": 3}},
            ],
            retrieval_setup_tokens=7,
            harness_results=None,
            setup_tokens_graph_built=11,
            setup_tokens_rag_built=13,
            setup_tokens_method_accounted=7,
        )

        self.assertEqual(fields["setup_tokens_graph_built"], 11)
        self.assertEqual(fields["setup_tokens_rag_built"], 13)
        self.assertEqual(fields["setup_tokens_method_accounted"], 7)
        self.assertEqual(fields["retrieval_setup_tokens"], 7)
        self.assertEqual(fields["total_cost_tokens"], 12)

    def test_compute_cost_summary_fields_defaults_method_accounted_tokens(self):
        from run_patch import _compute_cost_summary_fields

        fields = _compute_cost_summary_fields(
            per_instance_results=[],
            retrieval_setup_tokens=19,
            harness_results=None,
        )

        self.assertEqual(fields["setup_tokens_graph_built"], 0)
        self.assertEqual(fields["setup_tokens_rag_built"], 0)
        self.assertEqual(fields["setup_tokens_method_accounted"], 19)


class PredictionsBuildingTests(unittest.TestCase):
    """Tests for model_patch field in SWE-bench predictions (B7 fix).

    The harness is the ground truth evaluator.  Patches that fail our local
    git-apply check should still be submitted so the harness can try them — our
    local check is only a diagnostic used in the repair-retry loop.
    """

    def test_apply_failed_patch_included_in_predictions(self):
        """apply_failed patches must appear in model_patch, not as empty string."""
        from run_patch import _make_swebench_prediction

        patch_text = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n"
        pred = _make_swebench_prediction(
            instance_id="repo__pkg-1",
            retrieval_method="oracle",
            patch_text=patch_text,
            patch_status="apply_failed",
        )
        self.assertEqual(pred["model_patch"], patch_text)

    def test_no_patch_yields_empty_model_patch(self):
        """no_patch (model returned nothing) must submit empty string to harness."""
        from run_patch import _make_swebench_prediction

        pred = _make_swebench_prediction(
            instance_id="repo__pkg-2",
            retrieval_method="oracle",
            patch_text=None,
            patch_status="no_patch",
        )
        self.assertEqual(pred["model_patch"], "")

    def test_patched_status_included_in_predictions(self):
        """patched (local apply-check passed) must also be submitted correctly."""
        from run_patch import _make_swebench_prediction

        patch_text = "--- a/g.py\n+++ b/g.py\n@@ -1 +1 @@\n-x\n+y\n"
        pred = _make_swebench_prediction(
            instance_id="repo__pkg-3",
            retrieval_method="gm_progressive",
            patch_text=patch_text,
            patch_status="patched",
        )
        self.assertEqual(pred["model_patch"], patch_text)


class CommitCheckoutSelectionTests(unittest.TestCase):
    class _FakeGit:
        def __init__(self):
            self.checkouts = []
            self.fetches = []
            self._checkout_failures = []

        def queue_checkout_failure(self, exc: Exception):
            self._checkout_failures.append(exc)

        def checkout(self, commit, force=False):
            if self._checkout_failures:
                raise self._checkout_failures.pop(0)
            self.checkouts.append((commit, force))

        def fetch(self, *args):
            self.fetches.append(args)

    class _FakeRepo:
        def __init__(self):
            self.git = CommitCheckoutSelectionTests._FakeGit()

    def test_checkout_issue_commit_changes_per_issue(self):
        from run_patch import _checkout_issue_commit

        fake_repo = self._FakeRepo()
        current_commit = None
        issues = [
            {"instance_id": "i1", "base_commit": "abc111"},
            {"instance_id": "i2", "base_commit": "def222"},
            {"instance_id": "i3", "base_commit": "abc111"},
        ]

        for issue in issues:
            current_commit = _checkout_issue_commit(
                repo_git=fake_repo,
                snapshot_commit=None,
                issue=issue,
                current_commit=current_commit,
            )

        self.assertEqual(
            fake_repo.git.checkouts,
            [("abc111", True), ("def222", True), ("abc111", True)],
        )

    def test_checkout_issue_commit_fetches_missing_commit_then_retries(self):
        from run_patch import _checkout_issue_commit

        fake_repo = self._FakeRepo()
        fake_repo.git.queue_checkout_failure(RuntimeError("fatal: reference is not a tree: deadbeef"))

        current_commit = _checkout_issue_commit(
            repo_git=fake_repo,
            snapshot_commit=None,
            issue={"instance_id": "i1", "base_commit": "deadbeef"},
            current_commit=None,
        )

        self.assertEqual(current_commit, "deadbeef")
        self.assertEqual(fake_repo.git.fetches, [("origin", "deadbeef")])
        self.assertEqual(fake_repo.git.checkouts, [("deadbeef", True)])

    def test_checkout_issue_commit_raises_on_non_missing_ref_errors(self):
        from run_patch import _checkout_issue_commit

        fake_repo = self._FakeRepo()
        fake_repo.git.queue_checkout_failure(RuntimeError("fatal: detached HEAD"))

        with self.assertRaises(RuntimeError):
            _checkout_issue_commit(
                repo_git=fake_repo,
                snapshot_commit=None,
                issue={"instance_id": "i1", "base_commit": "abc111"},
                current_commit=None,
            )

        self.assertEqual(fake_repo.git.fetches, [])
        self.assertEqual(fake_repo.git.checkouts, [])


if __name__ == "__main__":
    unittest.main()
