"""Tests for Stage 1 checkpoint/resume (E3).

Covers:
  - _load_partial_checkpoint: reads predictions_partial.jsonl, returns completed instances
  - _flush_instance_to_checkpoint: appends one entry atomically
  - round-trip correctness (flush then load recovers same data)
  - malformed-line tolerance
  - merge_worker_predictions: combines N worker partial files (E2 prerequisite)
"""

import json
import tempfile
import unittest
from pathlib import Path


class LoadPartialCheckpointTests(unittest.TestCase):
    def test_returns_empty_dict_when_no_checkpoint_file(self):
        from run_patch import _load_partial_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_partial_checkpoint(Path(tmpdir))

        self.assertEqual(result, {})

    def test_returns_entries_from_checkpoint_file(self):
        from run_patch import _load_partial_checkpoint

        entry1 = {
            "instance_id": "repo__pkg-1",
            "prediction": {"instance_id": "repo__pkg-1", "model_patch": "diff ..."},
            "per_instance": {"instance_id": "repo__pkg-1", "patch_status": "patched", "total_tokens": 100},
        }
        entry2 = {
            "instance_id": "repo__pkg-2",
            "prediction": {"instance_id": "repo__pkg-2", "model_patch": ""},
            "per_instance": {"instance_id": "repo__pkg-2", "patch_status": "no_patch", "total_tokens": 50},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            partial_path = Path(tmpdir) / "predictions_partial.jsonl"
            partial_path.write_text(
                json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n",
                encoding="utf-8",
            )
            result = _load_partial_checkpoint(Path(tmpdir))

        self.assertIn("repo__pkg-1", result)
        self.assertIn("repo__pkg-2", result)
        self.assertEqual(result["repo__pkg-1"]["prediction"]["model_patch"], "diff ...")
        self.assertEqual(result["repo__pkg-2"]["per_instance"]["patch_status"], "no_patch")

    def test_skips_malformed_lines(self):
        from run_patch import _load_partial_checkpoint

        good_entry = {
            "instance_id": "repo__pkg-3",
            "prediction": {"instance_id": "repo__pkg-3", "model_patch": "x"},
            "per_instance": {"instance_id": "repo__pkg-3", "patch_status": "patched"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            partial_path = Path(tmpdir) / "predictions_partial.jsonl"
            partial_path.write_text(
                "{not valid json\n" +           # malformed
                json.dumps(good_entry) + "\n" + # good
                "\n",                           # blank line
                encoding="utf-8",
            )
            result = _load_partial_checkpoint(Path(tmpdir))

        self.assertEqual(list(result.keys()), ["repo__pkg-3"])

    def test_skips_entries_missing_instance_id(self):
        from run_patch import _load_partial_checkpoint

        bad_entry = {"prediction": {}, "per_instance": {}}  # no instance_id

        with tempfile.TemporaryDirectory() as tmpdir:
            partial_path = Path(tmpdir) / "predictions_partial.jsonl"
            partial_path.write_text(json.dumps(bad_entry) + "\n", encoding="utf-8")
            result = _load_partial_checkpoint(Path(tmpdir))

        self.assertEqual(result, {})

    def test_load_merges_worker_and_partial_with_partial_precedence(self):
        from run_patch import _load_partial_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            worker_entry = {
                "instance_id": "repo__pkg-1",
                "prediction": {"instance_id": "repo__pkg-1", "model_patch": "old_worker_patch"},
                "per_instance": {"instance_id": "repo__pkg-1", "patch_status": "no_patch"},
            }
            partial_entry = {
                "instance_id": "repo__pkg-1",
                "prediction": {"instance_id": "repo__pkg-1", "model_patch": "new_partial_patch"},
                "per_instance": {"instance_id": "repo__pkg-1", "patch_status": "patched"},
            }
            (run_dir / "predictions_worker_0.jsonl").write_text(json.dumps(worker_entry) + "\n", encoding="utf-8")
            (run_dir / "predictions_partial.jsonl").write_text(json.dumps(partial_entry) + "\n", encoding="utf-8")

            result = _load_partial_checkpoint(run_dir)

        self.assertEqual(result["repo__pkg-1"]["prediction"]["model_patch"], "new_partial_patch")
        self.assertEqual(result["repo__pkg-1"]["per_instance"]["patch_status"], "patched")


class FlushInstanceToCheckpointTests(unittest.TestCase):
    def test_creates_file_and_appends_entry(self):
        from run_patch import _flush_instance_to_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            partial_path = run_dir / "predictions_partial.jsonl"

            self.assertFalse(partial_path.exists())

            _flush_instance_to_checkpoint(
                run_dir=run_dir,
                instance_id="repo__pkg-10",
                prediction={"instance_id": "repo__pkg-10", "model_patch": "patch text"},
                per_instance={"instance_id": "repo__pkg-10", "patch_status": "patched"},
            )

            self.assertTrue(partial_path.exists())
            lines = [l for l in partial_path.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["instance_id"], "repo__pkg-10")
            self.assertEqual(entry["prediction"]["model_patch"], "patch text")

    def test_multiple_flushes_produce_multiple_lines(self):
        from run_patch import _flush_instance_to_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            for i in range(3):
                _flush_instance_to_checkpoint(
                    run_dir=run_dir,
                    instance_id=f"repo__pkg-{i}",
                    prediction={"instance_id": f"repo__pkg-{i}", "model_patch": ""},
                    per_instance={"instance_id": f"repo__pkg-{i}", "patch_status": "no_patch"},
                )

            lines = [l for l in (run_dir / "predictions_partial.jsonl").read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 3)
            ids = [json.loads(l)["instance_id"] for l in lines]
            self.assertEqual(ids, ["repo__pkg-0", "repo__pkg-1", "repo__pkg-2"])

    def test_flush_is_append_not_overwrite(self):
        """Calling flush on a pre-existing file appends, not overwrites."""
        from run_patch import _flush_instance_to_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            partial_path = run_dir / "predictions_partial.jsonl"
            # Pre-populate one entry
            partial_path.write_text(
                json.dumps({"instance_id": "existing", "prediction": {}, "per_instance": {}}) + "\n",
                encoding="utf-8",
            )

            _flush_instance_to_checkpoint(
                run_dir=run_dir,
                instance_id="new_entry",
                prediction={},
                per_instance={},
            )

            lines = [l for l in partial_path.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)
            ids = [json.loads(l)["instance_id"] for l in lines]
            self.assertIn("existing", ids)
            self.assertIn("new_entry", ids)

    def test_flush_supports_custom_checkpoint_filename(self):
        from run_patch import _flush_instance_to_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _flush_instance_to_checkpoint(
                run_dir=run_dir,
                instance_id="repo__pkg-10",
                prediction={"instance_id": "repo__pkg-10", "model_patch": "patch text"},
                per_instance={"instance_id": "repo__pkg-10", "patch_status": "patched"},
                checkpoint_filename="predictions_worker_3.jsonl",
            )
            worker_file = run_dir / "predictions_worker_3.jsonl"
            self.assertTrue(worker_file.exists())
            lines = [l for l in worker_file.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)


class CheckpointRoundTripTests(unittest.TestCase):
    def test_flush_then_load_recovers_data(self):
        from run_patch import _flush_instance_to_checkpoint, _load_partial_checkpoint

        instances = [
            {
                "instance_id": f"repo__pkg-{i}",
                "prediction": {"instance_id": f"repo__pkg-{i}", "model_patch": f"patch_{i}"},
                "per_instance": {
                    "instance_id": f"repo__pkg-{i}",
                    "patch_status": "patched",
                    "total_tokens": i * 100,
                },
            }
            for i in range(5)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            for inst in instances:
                _flush_instance_to_checkpoint(
                    run_dir=run_dir,
                    instance_id=inst["instance_id"],
                    prediction=inst["prediction"],
                    per_instance=inst["per_instance"],
                )

            recovered = _load_partial_checkpoint(run_dir)

        self.assertEqual(len(recovered), 5)
        for i in range(5):
            iid = f"repo__pkg-{i}"
            self.assertIn(iid, recovered)
            self.assertEqual(recovered[iid]["prediction"]["model_patch"], f"patch_{i}")
            self.assertEqual(recovered[iid]["per_instance"]["total_tokens"], i * 100)


class MergeWorkerPredictionsTests(unittest.TestCase):
    """Tests for E2 worker merge step (needed before E2 implementation)."""

    def test_merge_combines_all_worker_files(self):
        from run_patch import _merge_worker_predictions

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Simulate 3 workers each with 2 instances
            for worker_id in range(3):
                worker_file = run_dir / f"predictions_worker_{worker_id}.jsonl"
                for inst_idx in range(2):
                    iid = f"repo__pkg-w{worker_id}_i{inst_idx}"
                    entry = {
                        "instance_id": iid,
                        "prediction": {"instance_id": iid, "model_patch": f"patch_{worker_id}_{inst_idx}"},
                        "per_instance": {"instance_id": iid, "patch_status": "patched", "total_tokens": 10},
                    }
                    with worker_file.open("a") as f:
                        f.write(json.dumps(entry) + "\n")

            predictions, per_instance_list = _merge_worker_predictions(run_dir, n_workers=3)

        self.assertEqual(len(predictions), 6)
        self.assertEqual(len(per_instance_list), 6)
        # All instance IDs present
        for w in range(3):
            for i in range(2):
                iid = f"repo__pkg-w{w}_i{i}"
                self.assertIn(iid, predictions)
                self.assertEqual(predictions[iid]["model_patch"], f"patch_{w}_{i}")

    def test_merge_handles_empty_worker_files(self):
        from run_patch import _merge_worker_predictions

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Worker 0 has entries, workers 1 and 2 are empty
            worker_0 = run_dir / "predictions_worker_0.jsonl"
            entry = {
                "instance_id": "repo__pkg-1",
                "prediction": {"instance_id": "repo__pkg-1", "model_patch": "p"},
                "per_instance": {"instance_id": "repo__pkg-1", "patch_status": "patched"},
            }
            worker_0.write_text(json.dumps(entry) + "\n")
            (run_dir / "predictions_worker_1.jsonl").write_text("")
            (run_dir / "predictions_worker_2.jsonl").write_text("")

            predictions, per_instance_list = _merge_worker_predictions(run_dir, n_workers=3)

        self.assertEqual(len(predictions), 1)
        self.assertIn("repo__pkg-1", predictions)

    def test_merge_handles_missing_worker_files(self):
        """If a worker file doesn't exist (worker crashed before writing), skip it."""
        from run_patch import _merge_worker_predictions

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Only worker 0 exists
            entry = {
                "instance_id": "repo__pkg-sole",
                "prediction": {"instance_id": "repo__pkg-sole", "model_patch": ""},
                "per_instance": {"instance_id": "repo__pkg-sole", "patch_status": "no_patch"},
            }
            (run_dir / "predictions_worker_0.jsonl").write_text(json.dumps(entry) + "\n")
            # workers 1, 2 files are absent

            predictions, per_instance_list = _merge_worker_predictions(run_dir, n_workers=3)

        self.assertEqual(len(predictions), 1)

    def test_merge_preserves_per_instance_order_across_workers(self):
        """per_instance_list order follows instance order within each worker file."""
        from run_patch import _merge_worker_predictions

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Worker 0: instance A, B; Worker 1: instance C
            for worker_id, iids in enumerate([["A", "B"], ["C"]]):
                worker_file = run_dir / f"predictions_worker_{worker_id}.jsonl"
                for iid in iids:
                    entry = {
                        "instance_id": iid,
                        "prediction": {"instance_id": iid, "model_patch": ""},
                        "per_instance": {"instance_id": iid, "patch_status": "patched"},
                    }
                    with worker_file.open("a") as f:
                        f.write(json.dumps(entry) + "\n")

            predictions, per_instance_list = _merge_worker_predictions(run_dir, n_workers=2)

        result_ids = [r["instance_id"] for r in per_instance_list]
        # A and B must appear before C (worker 0 before worker 1)
        self.assertLess(result_ids.index("A"), result_ids.index("C"))
        self.assertLess(result_ids.index("B"), result_ids.index("C"))


class DistributeInstancesTests(unittest.TestCase):
    """Tests for E2 instance distribution across workers."""

    def test_distributes_evenly_when_divisible(self):
        from run_patch import _distribute_instances

        instances = list(range(9))
        chunks = _distribute_instances(instances, n_workers=3)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(sum(len(c) for c in chunks), 9)
        # Each chunk has exactly 3 items
        self.assertTrue(all(len(c) == 3 for c in chunks))

    def test_distributes_remainder_to_earlier_workers(self):
        from run_patch import _distribute_instances

        instances = list(range(10))
        chunks = _distribute_instances(instances, n_workers=3)

        # 10 / 3 → 3 workers get [4, 3, 3]
        self.assertEqual(sum(len(c) for c in chunks), 10)
        self.assertEqual(len(chunks), 3)
        self.assertGreaterEqual(len(chunks[0]), len(chunks[-1]))

    def test_all_instances_present_exactly_once(self):
        from run_patch import _distribute_instances

        instances = [f"id_{i}" for i in range(17)]
        chunks = _distribute_instances(instances, n_workers=4)

        all_ids = [item for chunk in chunks for item in chunk]
        self.assertEqual(sorted(all_ids), sorted(instances))

    def test_single_worker_returns_all_instances_in_one_chunk(self):
        from run_patch import _distribute_instances

        instances = list(range(5))
        chunks = _distribute_instances(instances, n_workers=1)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], instances)

    def test_more_workers_than_instances_gives_non_empty_chunks(self):
        from run_patch import _distribute_instances

        instances = ["a", "b"]
        chunks = _distribute_instances(instances, n_workers=5)

        non_empty = [c for c in chunks if c]
        self.assertEqual(len(non_empty), 2)
        self.assertEqual(sorted(item for c in non_empty for item in c), ["a", "b"])

    def test_empty_instances_returns_empty_chunks(self):
        from run_patch import _distribute_instances

        chunks = _distribute_instances([], n_workers=3)

        self.assertTrue(all(c == [] for c in chunks))
        self.assertEqual(len(chunks), 3)


if __name__ == "__main__":
    unittest.main()
