# 2026-02-18 — Handoff: Run Patching Pipeline

## Your Job

Run the end-to-end patch pipeline on `psf/requests` (8 SWE-bench Verified instances),
collect pass@1 results, and record them in `research_report/` and `README.md`.

The retrieval → patch → evaluation infrastructure is **fully built and tested**.
You are picking up at the point of actually running it with live API calls and Docker.

---

## Repo State

- Branch: `main`, commit `8c86d8f` — clean working tree, nothing uncommitted.
- 112 tests passing: `./.venv/bin/python -m unittest discover -s tests -v`
- All retrieval evaluation results are in `results/clean_eval_20260211_201431/`
  (11 valid cells, langchain excluded with `valid:false`).
- Patch pipeline dry-run was already confirmed working (produces empty patches
  because `--dry-run` skips API calls — that's expected).

---

## Prerequisites

### 1. GEMINI_API_KEY
Must be set in `.env` (the file is gitignored):
```
GEMINI_API_KEY=<your key>
```
The pipeline reads it with `python-dotenv` on startup.
Models used: retrieval manager = `gemini-3-flash-preview`, patch agent = `gemini-3-flash-preview` (set in the manifest; see `patch_manifests/swebench_verified_requests_oracle_v1.yaml`).

### 2. Docker daemon
Must be running. The SWE-bench harness pulls and runs Docker containers.
On WSL2: `sudo service docker start` in a separate terminal, then verify with `docker ps`.

### 3. SWE-bench package
Already installed: `swebench==4.1.0` is in `.venv`.

---

## Run Command

```bash
./.venv/bin/python run_patch.py \
    --manifest patch_manifests/swebench_verified_requests_v1.yaml \
    --evaluate \
    --results-dir results
```

This will:
1. Clone/use cached `psf/requests` repo (goes into `requests_repo/`, gitignored).
2. Build graph index (529 nodes, 1110 edges from dry-run) + RAG index (482 chunks).
3. Run `gm_progressive` retrieval for each of the 8 instances.
4. Run `PatchAgent` (Gemini) to generate a unified diff for each instance.
5. Save patches to `results/patch_runs/<run_id>/patches/`.
6. Save `predictions.json` in SWE-bench format.
7. Run SWE-bench harness with Docker → parse resolved-rate.
8. Write `results/patch_runs/<run_id>/patch_summary.json`.

**Without `--evaluate`** (no Docker): steps 1–6 only. You get patches but no pass@1.

---

## Output Files

```
results/patch_runs/<run_id>/
    patch_summary.json          # top-level results + per-instance breakdown
    predictions.json            # SWE-bench harness input format
    patches/
        psf__requests-1142.diff
        psf__requests-1724.diff
        ...
```

### Key fields in `patch_summary.json`:
```json
{
  "n_instances": 8,
  "n_patched": <int>,          // instances where a non-empty patch was produced
  "patch_rate": <float>,       // n_patched / n_instances
  "harness_results": {         // null if --evaluate not used or Docker unavailable
    "resolved": <int>,
    "total": 8,
    "resolved_rate": <float>
  },
  "per_instance": [...]        // per-issue: retrieved_files, patch_status, tokens, timing
}
```

---

## What to Record Afterwards

Once you have results, update two places:

### `README.md`
Find the "End-to-End Patching" section (or create one after "Latest Validated Evidence").
Add a table like:

```markdown
| Repo | Instances | Patch rate | Resolved rate | Retrieval method |
|------|-----------|------------|---------------|-----------------|
| psf/requests | 8 | X/8 | X/8 | gm_progressive |
```

### `research_report/artifacts/frozen-20260212-matrix-v2-clean/summary_bundle.json`
You can append a `"patching"` key with the run summary, or create a new frozen
artifact bundle at `research_report/artifacts/frozen-20260218-patch-v1/`.

### `dev_logs/`
Write a dev log entry following the template in `dev_logs/TEMPLATE.md`.

---

## If Patches Are Generated But Harness Fails

Re-run evaluation only (without re-calling the API):

```bash
# Not yet implemented — add --evaluate-only flag to run_patch.py, or
# call the harness directly:
./.venv/bin/python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --split test \
    --predictions_path results/patch_runs/<run_id>/predictions.json \
    --run_id <run_id> \
    --max_workers 1
```

---

## Key Files

| File | Purpose |
|------|---------|
| `run_patch.py` | Pipeline CLI entry point |
| `src/patch_agent.py` | PatchAgent — Gemini diff generator |
| `src/manager_agent.py` | Retrieval manager (gm_progressive) |
| `src/graph_builder.py` | Graph construction (tree-sitter AST) |
| `src/rag_baseline.py` | RAG index construction |
| `patch_manifests/swebench_verified_requests_v1.yaml` | 8-instance manifest |
| `results/clean_eval_20260211_201431/` | Existing retrieval evaluation results |
| `dev_logs/2026-02-18-patch-pipeline-phase2.md` | Phase 2 design decisions |
| `AGENTS.md` | Repo-level agent instructions (read first) |

---

## Commit Convention

After recording results, commit with:
```
Add psf/requests patch run results (pass@1: X/8)

- patch_summary.json: n_patched=X, resolved_rate=X.XX
- Update README patching table
- [optional] freeze artifact bundle

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## What NOT to Do

- Do not re-run the retrieval-only evaluation (`run_experiment.py`) — those results
  are stable and frozen.
- Do not modify the langchain cells — they are excluded intentionally (`valid:false`).
- Do not tune `gm_deterministic` — deferred to a later phase.
- Do not commit `requests_repo/` or any `*_repo/` directories — gitignored.
- Do not commit `results/` — gitignored.
