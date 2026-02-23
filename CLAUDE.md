# GraphManager — Agent Instructions (Claude Code)

## Start of every session

Read these two files before doing anything else:

1. `CURRENT_STATE.md` — what workstream you are on, what is done, what the next action is, known bugs
2. `RESEARCH_INTENT.md` — the paper scope, claims, and what NOT to build

If these files contradict each other, `RESEARCH_INTENT.md` wins on scope decisions;
`CURRENT_STATE.md` wins on execution state.

## End of every session

Update `CURRENT_STATE.md`:
- Mark completed tasks done
- Record run IDs and key metrics (apply_success_rate, n_resolved, F1, cost)
- Update bug fix status if you fixed something
- Update "Next action" for the workstream you touched

Write a dev log entry in `dev_logs/YYYY-MM-DD-<short-slug>.md` for any non-trivial
change. Use `dev_logs/TEMPLATE.md` for the structure.

---

## Development Policy

### TDD for all behavior changes
1. Write a failing test that captures the intended behavior.
2. Implement the minimal fix.
3. Run the full test suite: `./.venv/bin/python -m unittest discover -s tests -v`
4. All tests must pass before committing.

Do not skip tests because "it's a small change." The patch pipeline has had multiple
silent regressions from untested changes.

### One workstream at a time
Workstreams A (retrieval eval), B (patching pipeline), and C (paper writing) are
intentionally separate. Do not touch A's files while working on B, and vice versa.
Check `CURRENT_STATE.md` to confirm which workstream you are assigned.

### Workstream status rules
- `[ACTIVE]` — in flight. Work here.
- `[DONE]` — all goals met. You may mark a workstream done if verifiably complete.
- `[ARCHIVED]` — retired. Do not resurrect.
- You may **NOT** create new workstreams or change status to `[ACTIVE]`. Only the researcher does that.
- If you notice a new task or problem, append it to the **Parking Lot** section of `CURRENT_STATE.md` and stop. Do not act on it unless your prompt explicitly assigns it.

### Do not re-run valid experiments
Retrieval experiment cells that already have valid results are frozen. Do not
re-run them. Check `CURRENT_STATE.md` → Workstream A status before running anything.

### Reproduce before expanding
For patching: run on 8 instances (requests manifest) and confirm numbers make sense
before expanding to 30 instances across 3 repos. Never expand a broken pipeline.

### Commit hygiene
- Never commit `*_repo/` directories or `results/` (both gitignored — keep it that way)
- Commit manifests and code; never commit raw API outputs or model responses
- Commit message format: short imperative title + blank line + what changed and why

### Scope discipline
Read `RESEARCH_INTENT.md`. Paper 1 has a defined scope. Do not:
- Build MAS orchestration (Paper 2)
- Add features not needed for the current experiment
- Expand beyond 30 patching instances until the pilot is validated
- Refactor working code without a test-backed reason

---

## Project Layout

```
run_experiment.py         retrieval evaluation runner
run_suite.py              multi-repo suite runner
run_patch.py              patching pipeline runner
src/
  manager_agent.py        graph-guided retrieval agent
  rag_baseline.py         RAG retrieval baseline
  graph_builder.py        AST graph construction (tree-sitter)
  evaluation.py           metrics, dataset loading, commit checkout
  patch_agent.py          patch generation agent
  deterministic_retrieval.py  zero-LLM-runtime retrieval scorer
patch_manifests/          YAML manifests for patch runs
experiments_matrix_v2.yaml  retrieval experiment matrix
tests/                    unit tests (run before every commit)
research_report/          LaTeX paper draft
dev_logs/                 decision logs (one file per session/decision)
results/                  gitignored — experiment outputs
```

## Key commands

```bash
# Retrieval experiment (single repo)
./.venv/bin/python run_experiment.py --repo-name pallets/flask \
  --source-prefix src/flask --n-issues 10 --manager-max-turns 6 --rag-max-turns 6

# Patching run — Stage 1: generate patches only (no Docker needed)
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml

# Patching run — Stage 1 + 2 combined (Docker or Modal)
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate [--modal]

# Patching run — Stage 2 only: evaluate an existing predictions.json
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate-only --run-dir results/patch_runs/<run_id> [--modal]

# Full test suite
./.venv/bin/python -m unittest discover -s tests -v

# Visualize retrieval results
./.venv/bin/python visualize_results.py
```
