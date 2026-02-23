# Modal Support + Two-Stage Patch Pipeline

*Date: 2026-02-22 · Workstream: B (post-DONE addition)*

---

## Context

After the N=100 patching pilot completed, the bottleneck analysis showed:

- **75% of wall-clock time** is the SWE-bench Docker harness (test execution), not retrieval or patch generation.
- Repo choice varies 17×: `psf/requests` ~24s avg vs `matplotlib/matplotlib` ~423s avg per instance.
- Sequential local Docker is the binding constraint; patch generation (LLM calls) and retrieval are secondary.

Two improvements were made:

1. **Modal cloud support** — offload harness execution to Modal Sandboxes (no local Docker needed).
2. **Two-stage pipeline** — separate patch generation (Stage 1) from harness evaluation (Stage 2) so they can be run independently and the harness re-run without regenerating patches.

---

## Changes Made

### `run_patch.py`

**Modal support (`--modal` flag):**
- Added `modal: bool = False` parameter to `run_patch_pipeline()`.
- When `modal=True`: Docker availability check is bypassed (Modal uses its own Sandbox runtime).
- `max_workers` set to `1` for Modal (Modal handles parallelism internally via cloud Sandboxes).
- `modal=modal` threaded through to `swebench_eval()` call.
- `--modal` CLI flag added.

**Two-stage pipeline (`--evaluate-only` + `--run-dir`):**
- Added `_run_evaluate_only(run_dir, modal)` helper function.
  - Loads `patch_summary.json` from an existing run directory.
  - Recovers `dataset_name`, `instance_ids`, `predictions_path` from summary.
  - Recovers `split` from the manifest file (falls back to `"test"`).
  - Runs SWE-bench harness (local Docker or Modal).
  - Recomputes cost fields (`n_resolved`, `cost_per_resolved_issue`, etc.) with harness results.
  - Overwrites `patch_summary.json` in place with updated results.
- Added `evaluate_only: bool = False` and `run_dir: str | None = None` parameters to `run_patch_pipeline()`.
- When `evaluate_only=True`: early return to `_run_evaluate_only()`, all patch generation skipped.
- `--evaluate-only` and `--run-dir` CLI flags added.

**Usage:**

```bash
# Stage 1: generate patches only (no harness, no Docker)
python run_patch.py --manifest patch_manifests/foo.yaml

# Stage 2: evaluate an existing run
python run_patch.py --manifest patch_manifests/foo.yaml \
  --evaluate-only --run-dir results/patch_runs/<run_id> [--modal]

# Combined (old behavior preserved)
python run_patch.py --manifest patch_manifests/foo.yaml --evaluate [--modal]
```

---

## Modal Pilot Run — Results

Tested on `psf/requests` oracle manifest (n=8):

```bash
source .env && ./.venv/bin/python run_patch.py \
  --manifest patch_manifests/n100_verified/psf_requests_oracle_v1.yaml \
  --evaluate --modal
```

Run dir: `results/patch_runs/20260222_210339/`

**Outcome: 4/8 resolved (50%) — matches expected oracle performance on psf/requests.**

| Metric | Value |
|--------|-------|
| Instances | 8 |
| Patched | 8/8 (100% apply rate) |
| Resolved | 4/8 (50%) |
| CPR | 15,373 tokens/resolved |
| Modal harness time | ~4 min (all 8 instances, parallel) |

Resolved: `psf__requests-1142`, `psf__requests-1724`, `psf__requests-1766`, `psf__requests-5414`

Per-instance patch generation times (sequential LLM):

| Instance | Patch time |
|----------|-----------|
| psf__requests-1142 | 110s |
| psf__requests-1724 | 313s |
| psf__requests-1766 | 258s |
| psf__requests-1921 | 432s |
| psf__requests-2317 | 291s |
| psf__requests-2931 | 137s |
| psf__requests-5414 | 123s |
| psf__requests-6028 | 180s |

**Modal parallelism:** Despite `max_workers=1`, Modal Sandboxes ran all instances in parallel (~4 min total harness time vs 7+ min if sequential). Modal's scheduler parallelizes via Sandboxes regardless of `max_workers` — the parameter may control something else in the Modal context. The `max_workers=1 if modal else 4` safeguard is effectively a no-op.

**Sandbox timeout:** `psf__requests-2317` hit the 300s harness timeout (296.67s actual) and its report was lost. Increase `timeout=600` in the `swebench_eval()` call for safety on slower repos.

Note: `HF_TOKEN` must be set in `.env` for HuggingFace dataset download to succeed.
Without it, the download hangs on the unauthenticated request warning.

---

## Doc Audit (same session)

Stale files removed:
- `EXECUTION_PLAN.md` — self-marked "HISTORICAL DOCUMENT" (2026-02-11); all tasks superseded.
- `RESEARCH_COMPARISON.md` — 2026-02-11 intermediate experiment report; superseded by paper + `CURRENT_STATE.md`.

Updated:
- `CLAUDE.md` — fixed `run_patch.py` command (positional arg → `--manifest` flag); added two-stage examples.
- `AGENTS.md` — updated Current Priorities to reflect B/C DONE; updated commands.
- `CURRENT_STATE.md` — fixed Workstream B header ([ACTIVE] → [DONE]); added Modal/two-stage pipeline note.
- `README.md` — full overhaul: final N=100 numbers, correct project structure, updated limitations, two-stage patching workflow.
- `docs/README.md` — removed references to non-existent root files.

---

## Test Suite

All 143 tests pass after changes:
```
./.venv/bin/python -m unittest discover -s tests -v
# Ran 143 tests in 0.440s — OK
```
