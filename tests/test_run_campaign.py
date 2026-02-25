import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class RunCampaignTests(unittest.TestCase):
    def _write_campaign_yaml(self, campaigns_dir: Path, steps: list[dict]) -> Path:
        import yaml

        data = {
            "name": "test_campaign",
            "description": "Test campaign",
            "steps": steps,
        }
        path = campaigns_dir / "test_campaign.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        return path

    def test_campaign_runs_steps_in_order(self):
        from tools.run_campaign import run_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            campaigns_dir = root / "campaigns"
            campaigns_dir.mkdir()
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").touch()

            campaign_path = self._write_campaign_yaml(
                campaigns_dir,
                steps=[
                    {"name": "step_a", "description": "Step A", "command": "python -c 'pass'"},
                    {"name": "step_b", "description": "Step B", "command": "python -c 'pass'"},
                ],
            )

            call_order = []

            def mock_run(cmd, **kwargs):
                call_order.append(cmd)
                return MagicMock(returncode=0)

            with patch("tools.run_campaign.subprocess.run", side_effect=mock_run):
                rc = run_campaign(campaign_path, resume=False, only_step=None, root=root)

            self.assertEqual(rc, 0)
            self.assertEqual(len(call_order), 2)

            state_path = campaigns_dir / "test_campaign_state.json"
            self.assertTrue(state_path.exists())
            state = json.loads(state_path.read_text())
            names = [s["name"] for s in state["steps"]]
            self.assertEqual(names, ["step_a", "step_b"])
            statuses = [s["status"] for s in state["steps"]]
            self.assertEqual(statuses, ["done", "done"])

    def test_campaign_resume_skips_completed_steps(self):
        from tools.run_campaign import run_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            campaigns_dir = root / "campaigns"
            campaigns_dir.mkdir()

            campaign_path = self._write_campaign_yaml(
                campaigns_dir,
                steps=[
                    {"name": "step_a", "description": "Step A", "command": "python -c 'pass'"},
                    {"name": "step_b", "description": "Step B", "command": "python -c 'pass'"},
                    {"name": "step_c", "description": "Step C", "command": "python -c 'pass'"},
                ],
            )

            # Pre-populate state with step_a done
            state = {
                "campaign_name": "test_campaign",
                "steps": [
                    {"name": "step_a", "status": "done", "started_at": "...", "completed_at": "...", "elapsed_s": 1.0, "returncode": 0},
                    {"name": "step_b", "status": "pending", "started_at": None, "completed_at": None, "elapsed_s": None, "returncode": None},
                    {"name": "step_c", "status": "pending", "started_at": None, "completed_at": None, "elapsed_s": None, "returncode": None},
                ],
            }
            (campaigns_dir / "test_campaign_state.json").write_text(json.dumps(state), encoding="utf-8")

            call_count = [0]

            def mock_run(cmd, **kwargs):
                call_count[0] += 1
                return MagicMock(returncode=0)

            with patch("tools.run_campaign.subprocess.run", side_effect=mock_run):
                rc = run_campaign(campaign_path, resume=True, only_step=None, root=root)

            self.assertEqual(rc, 0)
            # Only steps b and c should have been run (step_a was done)
            self.assertEqual(call_count[0], 2)

    def test_campaign_stops_on_step_failure(self):
        from tools.run_campaign import run_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            campaigns_dir = root / "campaigns"
            campaigns_dir.mkdir()

            campaign_path = self._write_campaign_yaml(
                campaigns_dir,
                steps=[
                    {"name": "step_a", "description": "Fails", "command": "python -c 'exit(1)'"},
                    {"name": "step_b", "description": "Should not run", "command": "python -c 'pass'"},
                ],
            )

            call_count = [0]

            def mock_run(cmd, **kwargs):
                call_count[0] += 1
                return MagicMock(returncode=1)  # Always fail

            with patch("tools.run_campaign.subprocess.run", side_effect=mock_run):
                rc = run_campaign(campaign_path, resume=False, only_step=None, root=root)

            # Non-zero return code
            self.assertNotEqual(rc, 0)
            # Only step_a was run; step_b was NOT started
            self.assertEqual(call_count[0], 1)

            state_path = campaigns_dir / "test_campaign_state.json"
            state = json.loads(state_path.read_text())
            step_a = next(s for s in state["steps"] if s["name"] == "step_a")
            step_b = next(s for s in state["steps"] if s["name"] == "step_b")
            self.assertEqual(step_a["status"], "failed")
            self.assertEqual(step_b["status"], "pending")


if __name__ == "__main__":
    unittest.main()
