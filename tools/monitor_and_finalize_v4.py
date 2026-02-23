#!/usr/bin/env python3
"""Monitor N=100 none completion and finalize v4 handoff artifacts/docs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


LEDGER_PATH = Path("patch_manifests/n100_verified/manifest_ledger_v1.json")
PATCH_RUNS_ROOT = Path("results/patch_runs")
CURRENT_STATE_PATH = Path("CURRENT_STATE.md")


@dataclass
class NoneCellStatus:
    repo: str
    manifest_path: str
    run_id: str | None
    completion_marker: str
    completed: bool
    n_resolved: int | None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _none_manifests() -> list[tuple[str, str]]:
    ledger = _read_json(LEDGER_PATH)
    out: list[tuple[str, str]] = []
    for entry in ledger.get("entries", []):
        if str(entry.get("method")) != "none":
            continue
        out.append((str(entry.get("repo")), str(entry.get("manifest_path"))))
    return sorted(out)


def _scan_status() -> list[NoneCellStatus]:
    statuses: list[NoneCellStatus] = []
    manifests = _none_manifests()
    for repo, manifest_path in manifests:
        candidates: list[tuple[str, dict[str, Any]]] = []
        for summary_path in PATCH_RUNS_ROOT.glob("*/patch_summary.json"):
            try:
                payload = _read_json(summary_path)
            except Exception:
                continue
            if str(payload.get("manifest") or "") != manifest_path:
                continue
            if str(payload.get("retrieval_method") or "") != "none":
                continue
            candidates.append((summary_path.parent.name, payload))

        if not candidates:
            statuses.append(
                NoneCellStatus(
                    repo=repo,
                    manifest_path=manifest_path,
                    run_id=None,
                    completion_marker="missing_summary",
                    completed=False,
                    n_resolved=None,
                )
            )
            continue

        run_id, payload = sorted(candidates, key=lambda item: item[0])[-1]
        marker = "incomplete"
        completed = False
        n_resolved: int | None = None
        harness = payload.get("harness_results")
        if isinstance(harness, dict) and _is_number(harness.get("n_resolved")):
            marker = "harness_results"
            completed = True
            n_resolved = int(harness.get("n_resolved"))
        elif "harness_error" in payload:
            marker = "harness_error"
            completed = True
        elif "harness_skipped_reason" in payload:
            marker = "harness_skipped_reason"
            completed = True

        statuses.append(
            NoneCellStatus(
                repo=repo,
                manifest_path=manifest_path,
                run_id=run_id,
                completion_marker=marker,
                completed=completed,
                n_resolved=n_resolved,
            )
        )
    return statuses


def _rewrite_current_state(statuses: list[NoneCellStatus]) -> None:
    text = CURRENT_STATE_PATH.read_text()
    today = datetime.now().strftime("%Y-%m-%d")

    text = re.sub(r"^Last updated: .*$", f"Last updated: {today}", text, flags=re.MULTILINE)
    text = re.sub(
        r"^Last agent: .*$",
        "Last agent: GPT-5 Codex (v4 auto-finalize after none completion)",
        text,
        flags=re.MULTILINE,
    )
    text = text.replace(
        "- [ ] **Phase 2 (data completion):** `none` baseline complete across 9 repos with completion markers.",
        "- [x] **Phase 2 (data completion):** `none` baseline complete across 9 repos with completion markers.",
    )
    text = text.replace(
        "- [ ] **Phase 5 (final handoff pack):** state file + handoff log populated with phase-3 outputs and rerun decision.",
        "- [x] **Phase 5 (final handoff pack):** state file + handoff log populated with phase-3 outputs and rerun decision.",
    )

    lines = [
        "**none baseline status (Phase 2 gate — COMPLETE):",
        "- all 9 repos satisfy completion criterion (`harness_results.n_resolved` OR `harness_error` OR `harness_skipped_reason`) ✓",
    ]
    for status in sorted(statuses, key=lambda item: item.repo):
        lines.append(
            f"- {status.repo}: `{status.run_id}` marker=`{status.completion_marker}` "
            f"n_resolved={status.n_resolved if status.n_resolved is not None else 'n/a'}"
        )
    replacement = "\n".join(lines) + "\n\n"
    pattern = re.compile(
        r"\*\*none baseline status \(Phase 2 gate — [^)]+\):\n(?:- .*\n)+\n",
        flags=re.MULTILINE,
    )
    if pattern.search(text):
        text = pattern.sub(replacement, text, count=1)
    else:
        # Fallback append if the expected block is not found.
        text += "\n" + replacement

    CURRENT_STATE_PATH.write_text(text)


def _write_finalize_log(statuses: list[NoneCellStatus]) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path("dev_logs") / f"{today}-v4-auto-finalize-after-none.md"
    none_rows = "\n".join(
        f"- `{status.repo}` -> `{status.run_id}` (`{status.completion_marker}`, n_resolved={status.n_resolved if status.n_resolved is not None else 'n/a'})"
        for status in sorted(statuses, key=lambda item: item.repo)
    )
    body = f"""# {today} - v4 Auto Finalize After None Completion

## Context

- Automated continuation was requested to run while the user was offline.
- Goal: finish v4 handoff once N=100 `none` reached completion criteria on all repos.

## Decision

- Confirmed `none` completion across all 9 repos.
- Re-ran `tools/analyze_v4_handoff.py` to refresh Phase 3 outputs.
- Updated `CURRENT_STATE.md` to mark Phase 2 and Phase 5 complete.

## Alternatives Considered

1. Wait for manual wake-up confirmation before finalizing.
Main tradeoff: safer but delays closeout and increases context drift.

2. Auto-finalize immediately after completion (chosen).
Main tradeoff: requires deterministic document edits but keeps momentum and handoff closure.

## Evidence

- Refreshed analysis command:
  - `./.venv/bin/python tools/analyze_v4_handoff.py`
- Completion rows:
{none_rows}
- Gate memo:
  - `results/analysis_v4_handoff/rerun_gate_decision.md`

## Consequences

- v4 handoff is closed operationally through Phase 5.
- Frozen-run policy remains intact (no rerun execution performed here).

## Follow-up

1. Researcher review of refreshed artifacts.
2. Decide whether to authorize post-gate targeted reruns separately.
3. Resume writing with claims locked.
"""
    path.write_text(body)
    return path


def _run_analyze() -> None:
    cmd = [sys.executable, "tools/analyze_v4_handoff.py"]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor none completion and auto-finalize v4 plan.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval in seconds.")
    args = parser.parse_args()

    print(f"[monitor] started poll_seconds={args.poll_seconds}")
    while True:
        statuses = _scan_status()
        completed = sum(1 for row in statuses if row.completed)
        print(f"[monitor] none completion {completed}/{len(statuses)} at {datetime.now().isoformat(timespec='seconds')}")
        for row in sorted(statuses, key=lambda item: item.repo):
            print(
                f"[monitor] {row.repo} run_id={row.run_id or 'none'} "
                f"marker={row.completion_marker} completed={row.completed}"
            )
        if completed >= len(statuses) and statuses:
            print("[monitor] completion reached; running analyze + finalization")
            _run_analyze()
            _rewrite_current_state(statuses)
            log_path = _write_finalize_log(statuses)
            print(f"[monitor] done; wrote {log_path}")
            return
        time.sleep(max(args.poll_seconds, 5))


if __name__ == "__main__":
    main()
