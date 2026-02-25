# GraphManager — Agent Instructions (Claude Code)

## Start of every session

Read these files in order before doing anything else:

1. `STATE.md` — what is done, what is next, known risks
2. `TASKS.md` — task backlog; find your assigned task
3. `RESEARCH_INTENT.md` — paper scope, claims, what NOT to build
4. `CLAIMS_LOCK.md` — permitted claim strength

If STATE.md and RESEARCH_INTENT.md conflict: RESEARCH_INTENT.md wins on scope;
STATE.md wins on execution status.

Run `make verify` before touching any code.

## End of every session

1. Update `STATE.md`: mark completed items, record run IDs / metrics, update "Next action"
2. Update `TASKS.md`: mark your task `[DONE]` if acceptance criteria are met
3. Write a dev log in `dev_logs/YYYY-MM-DD-<slug>.md` for non-trivial changes

---

## Development Policy

### TDD for all behavior changes
1. Write a failing test that captures the intended behavior.
2. Implement the minimal fix.
3. Run the full test suite: `make test`
4. All tests must pass before committing.

Do not skip tests because "it's a small change." The patch pipeline has had multiple
silent regressions from untested changes.

### One task at a time
Find the single `[ACTIVE]` task in TASKS.md. Work only on that.
Do not self-assign tasks. Only the researcher promotes tasks to `[ACTIVE]`.

If you notice a new task or problem, append it to the **Parking Lot** section of
`STATE.md` and stop. Do not act on it unless your prompt explicitly assigns it.

### Do not re-run valid experiments
Retrieval experiment cells that already have valid results are frozen. Do not
re-run them. Check `STATE.md` before running anything.

### Reproduce before expanding
For patching: run on 8 instances (requests manifest) and confirm numbers make sense
before expanding to 30 instances across 3 repos. Never expand a broken pipeline.

### Commit hygiene
- Never commit `*_repo/` directories, `results/`, or `graphmanager-*.json` (all gitignored)
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
run_experiment.py           retrieval evaluation runner
run_suite.py                multi-repo suite runner
run_patch.py                patching pipeline runner
src/
  manager_agent.py          graph-guided retrieval agent
  rag_baseline.py           RAG retrieval baseline (+ symmetric tools)
  graph_builder.py          AST graph construction (tree-sitter)
  evaluation.py             metrics, dataset loading, commit checkout
  patch_agent.py            patch generation agent
  bm25_baseline.py          BM25Plus file-level retrieval
  agentic_cold_start.py     agent with filesystem tools, no index
  repomap_like.py           PageRank on file-level graph
  agentless_like_localization.py  3-stage hierarchical localization
  deterministic_retrieval.py     zero-LLM-runtime retrieval scorer
tools/
  run_manifest_pool.py      parallel manifest pool runner
  patch_dashboard.py        web dashboard for run monitoring
patch_manifests/            YAML manifests for patch runs
  v2_verified/              V2 campaign manifests (12 repos x 8 methods)
experiments_matrix_v2.yaml  retrieval experiment matrix
tests/                      unit tests (run before every commit)
research_report/            LaTeX paper draft
dev_logs/                   decision logs (one file per session/decision)
docs/                       design docs and reference material
  archive/                  superseded planning docs (read-only)
results/                    gitignored — experiment outputs
```

## Key commands

```bash
# Health check (must pass before any work)
make verify

# Retrieval experiment (single repo)
./.venv/bin/python run_experiment.py --repo-name pallets/flask \
  --source-prefix src/flask --n-issues 10

# Retrieval suite (parallel across repos)
./.venv/bin/python run_suite.py experiments_retrieval_expansion_v2.yaml --max-parallel 3

# Patching — Stage 1 only (no Docker needed)
./.venv/bin/python run_patch.py --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml

# Patching — Stage 1+2 (requires Docker or --modal)
./.venv/bin/python run_patch.py --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml \
  --evaluate --modal

# Batch pool (parallel across repos)
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list <list.txt> --results-dir results/v2_full_runs \
  --max-parallel-repos 8 --resume-incomplete

# Full test suite
make test
```
