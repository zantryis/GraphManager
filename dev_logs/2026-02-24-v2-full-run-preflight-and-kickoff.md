# 2026-02-24 - V2 Full-Run Preflight Hardening and Kickoff

## Context

- Full V2 SWE-bench Verified run kickoff repeatedly failed early due launcher/process issues and a latent repo checkout assumption.
- A non-dry-run full-path sanity check was required before launching 48 manifests.
- A new dashboard already existed, but full-run launch mechanics needed to be made reliable.
- Affected files/modules: `run_patch.py`, `src/patch_dashboard.py`, `tests/test_patch_runner.py`,
  `tests/test_patch_dashboard.py`, run launch scripts/logs under `logs/`.

## Decision

- Add a safe fallback in commit checkout logic: if `git checkout <base_commit>` fails with `reference is not a tree`, fetch missing commit and retry once.
- Keep V2 full run target as SWE-bench Verified test split (48 manifests, 500 instances total across methods).
- Launch runner and dashboard using `setsid` detachment (not `nohup`) for this environment.
- Make dashboard show new active runs before first checkpoint by including empty `patch_runs/<run_id>` dirs.
- Scope boundary: no protocol changes to retrieval/patch method behavior; this change is reliability hardening only.

## Alternatives Considered

1. Manual one-off `git fetch --all` per local repo clone before run.
Tradeoff: no durable guard; brittle to future missing commits.

2. Keep old behavior and retry failed manifests manually.
Tradeoff: avoid code changes, but guarantees recurring failure mode and lost run time.

3. Add checkout-time fetch-and-retry fallback in runner (chosen).
Tradeoff: small behavioral branch in checkout path, but deterministic and testable.

## Evidence

- Failing symptom before fix:
  - `git.exc.GitCommandError: fatal: reference is not a tree: 22623bd8c265...` during Stage 1 checkout.
- Tests added:
- Tests added/updated:
  - `tests/test_patch_runner.py`
    - `test_checkout_issue_commit_fetches_missing_commit_then_retries`
    - `test_checkout_issue_commit_raises_on_non_missing_ref_errors`
  - `tests/test_patch_dashboard.py`
    - `test_discover_run_dirs_includes_empty_run_dirs`
- Validation:
  - Targeted tests: `./.venv/bin/python -m unittest tests.test_patch_runner.CommitCheckoutSelectionTests -v` → pass.
  - Full suite: `./.venv/bin/python -m unittest discover -s tests -v` → `204` passing.
- Modal full-path smoke (real patch generation):
  - `results/v2_smoke/patch_runs/20260223_222230/patch_summary.json`
  - Outcome: patched `1/1`, resolved `1/1`, harness executed via `--modal`.
- Full run kickoff artifacts:
  - Manifest list: `logs/v2_full_manifests_20260223_222457.txt` (`48` entries)
  - Runner log: `logs/v2_full_run_20260223_222457.log`
  - Kickoff metadata: `logs/v2_full_kickoff_20260223_222457.txt`
  - Dashboard endpoint: `http://127.0.0.1:5051/api/status`

## Consequences

- Expected benefits:
  - Full-run no longer aborts on missing local base commits.
  - Launches are resilient in this shell environment with detached runner/dashboard.
- Known risks:
  - Full run remains long; first manifest can take substantial time before status artifacts appear.
  - If a method-specific runtime error occurs mid-queue, runner exits at that manifest and requires relaunch.
- Monitoring signals:
  - Runner liveness PID from kickoff file.
  - Tail of `logs/v2_full_run_20260223_222457.log` for `DONE/FAIL` markers.
  - Dashboard `run_count` and per-run status transitions.

## Follow-up

1. Monitor active queue and capture first failure (if any) with manifest + traceback.
2. If interrupted, restart same runner script/list; completed manifests are skipped by manifest path.
3. After queue completion, generate method-level scorecard from `results/v2_full_runs/patch_runs/*/patch_summary.json`.
