# 2026-02-19 - N100 Unattended Supervisor

## Context

- User requested long-running execution without manual monitoring.
- N=100 queue had repeated interruptions (OOM/harness failures), and manual session runners were fragile.
- Workstream affected: B (patching execution orchestration only).

## Decision

- Launch a detached unattended supervisor to continue all remaining N=100 manifests.
- Keep experiment policy frozen; no changes to patching parameters or manifests.
- Enforce global method order across repos: `oracle` first for all repos, then `gm_progressive`, `rag_progressive`, `none`.

## Alternatives Considered

1. Continue manual session-only execution.
Main tradeoff: simple, but high risk of interruptions and idle gaps.

2. Restart from first manifest each time a crash occurs.
Main tradeoff: robust completion eventually, but wasteful and noisy run history.

3. Detached supervisor with completion checks (chosen).
Main tradeoff: adds orchestration complexity, but minimizes babysitting and retries only incomplete manifests.

## Evidence

- Active user-facing run before supervisor start:
  - `results/patch_runs/20260219_124650`
  - process `run_patch.py --manifest patch_manifests/n100_verified/scikit_learn_scikit_learn_oracle_v1.yaml --evaluate`
- Detached supervisor launch:
  - pid: `341`
  - log: `logs/n100_unattended_20260219_132505.log`
  - status file: `logs/n100_unattended_status.txt`
- Supervisor waits on currently running manifest and resumes queue automatically.

## Consequences

- Queue can continue unattended across session interruptions.
- Completed manifests are not re-run; incomplete manifests are retried in subsequent cycles.
- Remaining risk: infra-level OOM can still interrupt individual runs; supervisor handles this by retrying incomplete manifests later.

## Follow-up

1. Monitor `logs/n100_unattended_20260219_132505.log` and `logs/n100_unattended_status.txt`.
2. Once oracle manifests are complete, validate `patch_summary.json` coverage before moving to analysis tables.
3. Keep `CURRENT_STATE.md` updated with newly completed manifest summaries.
