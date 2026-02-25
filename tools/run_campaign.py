#!/usr/bin/env python3
"""Sequential campaign runner.

Reads a YAML campaign config and runs steps in order, tracking state in a JSON
file alongside the YAML. Resumable: on restart with --resume, skips completed steps.

Usage:
    python tools/run_campaign.py campaigns/v2_full.yaml
    python tools/run_campaign.py campaigns/v2_full.yaml --resume
    python tools/run_campaign.py campaigns/v2_full.yaml --step t0_pass1_zero_llm
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import yaml


def _load_campaign(campaign_path: Path) -> dict:
    data = yaml.safe_load(campaign_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid campaign YAML (expected dict): {campaign_path}")
    return data


def _state_path(campaign_path: Path) -> Path:
    return campaign_path.parent / (campaign_path.stem + "_state.json")


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state_path: Path, campaign_name: str, steps: list[dict]) -> None:
    data = {
        "campaign_name": campaign_name,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "steps": steps,
    }
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_step_list(campaign: dict, prior_state: dict) -> list[dict]:
    """Merge YAML step definitions with saved state."""
    prior_steps = {
        s["name"]: s
        for s in prior_state.get("steps", [])
        if isinstance(s, dict) and "name" in s
    }
    steps: list[dict] = []
    for raw in campaign.get("steps", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        prior = prior_steps.get(name, {})
        steps.append({
            "name": name,
            "description": str(raw.get("description") or ""),
            "command": str(raw.get("command") or ""),
            "status": str(prior.get("status") or "pending"),
            "started_at": prior.get("started_at"),
            "completed_at": prior.get("completed_at"),
            "elapsed_s": prior.get("elapsed_s"),
            "returncode": prior.get("returncode"),
        })
    return steps


def _resolve_command(raw_cmd: str, root: Path) -> str:
    """Replace leading 'python ' with the venv python path."""
    venv_python = str(root / ".venv" / "bin" / "python")
    if raw_cmd.startswith("python "):
        return venv_python + " " + raw_cmd[len("python "):]
    return raw_cmd


def _ensure_manifests_list(root: Path) -> None:
    """Auto-generate campaigns/v2_manifests.txt if it doesn't exist."""
    manifests_txt = root / "campaigns" / "v2_manifests.txt"
    if manifests_txt.exists():
        return
    manifest_paths = sorted((root / "patch_manifests" / "v2_verified").glob("*.yaml"))
    if not manifest_paths:
        return
    manifests_txt.parent.mkdir(parents=True, exist_ok=True)
    manifests_txt.write_text(
        "\n".join(str(p) for p in manifest_paths) + "\n",
        encoding="utf-8",
    )
    print(f"Auto-generated {manifests_txt} ({len(manifest_paths)} manifests)")


def run_campaign(
    campaign_path: Path,
    *,
    resume: bool = False,
    only_step: str | None = None,
    root: Path,
) -> int:
    """Run the campaign. Returns 0 on success, non-zero on failure."""
    campaign = _load_campaign(campaign_path)
    campaign_name = str(campaign.get("name") or campaign_path.stem)
    state_path = _state_path(campaign_path)
    prior_state = _load_state(state_path) if resume else {}
    steps = _build_step_list(campaign, prior_state)

    _ensure_manifests_list(root)

    print(f"Campaign: {campaign_name}")
    print(f"Steps: {len(steps)} | Resume: {resume}")
    if only_step:
        print(f"Running only step: {only_step}")

    for step in steps:
        name = step["name"]

        if step["status"] == "done":
            print(f"  [SKIP] {name} — already done ({step.get('elapsed_s', '?')}s)")
            continue

        if only_step is not None and name != only_step:
            continue

        print(f"\n{'='*60}")
        print(f"[STEP] {name}")
        if step["description"]:
            print(f"       {step['description']}")
        print(f"{'='*60}")

        step["status"] = "running"
        step["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _save_state(state_path, campaign_name, steps)

        cmd = _resolve_command(step["command"], root)
        env = {"PYTHONUNBUFFERED": "1", **os.environ}
        t0 = time.time()

        try:
            proc = subprocess.run(cmd, shell=True, cwd=str(root), env=env)
            rc = proc.returncode
        except Exception as exc:
            print(f"  ERROR executing step: {exc}")
            rc = 1

        elapsed = time.time() - t0
        step["elapsed_s"] = round(elapsed, 1)
        step["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        step["returncode"] = rc

        if rc == 0:
            step["status"] = "done"
            print(f"  [DONE] {name} in {elapsed:.0f}s")
        else:
            step["status"] = "failed"
            print(f"  [FAIL] {name} rc={rc} after {elapsed:.0f}s — stopping campaign")
            _save_state(state_path, campaign_name, steps)
            return rc

        _save_state(state_path, campaign_name, steps)

    all_done = all(s["status"] == "done" for s in steps if only_step is None or s["name"] == only_step)
    if all_done:
        print(f"\nCampaign '{campaign_name}' complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sequential campaign from YAML config")
    parser.add_argument("campaign", help="Path to campaign YAML file")
    parser.add_argument("--resume", action="store_true", help="Skip steps marked done in state file")
    parser.add_argument("--step", default=None, help="Run only this named step")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    return run_campaign(Path(args.campaign), resume=args.resume, only_step=args.step, root=root)


if __name__ == "__main__":
    raise SystemExit(main())
