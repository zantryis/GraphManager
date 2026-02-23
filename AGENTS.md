# AGENTS.md — GraphManager Agent Instructions (Codex / OpenAI agents)

## Start of every session

Read these two files before doing anything else:

1. `CURRENT_STATE.md` — what workstream you are on, what is done, what the next action is, known bugs
2. `RESEARCH_INTENT.md` — the paper scope, claims, and what NOT to build

If these files contradict each other, `RESEARCH_INTENT.md` wins on scope decisions;
`CURRENT_STATE.md` wins on execution state.

For full dev policy (TDD requirements, commit hygiene, scope rules), read `CLAUDE.md`.

## End of every session

Update `CURRENT_STATE.md`:
- Mark completed tasks done
- Record run IDs and key metrics
- Update bug fix status
- Update "Next action" for the workstream you touched

Write a dev log entry in `dev_logs/YYYY-MM-DD-<short-slug>.md` for non-trivial changes.
Use `dev_logs/TEMPLATE.md` for the structure.

---

## Must-Follow Workflow

1. **TDD for all behavior changes:** write failing test → implement → run full suite
   `./.venv/bin/python -m unittest discover -s tests -v` — all tests must pass.
2. **One workstream at a time:** A (retrieval), B (patching), C (paper) are separate.
   Do not touch A files while working on B.
3. **Do not re-run frozen experiments.** Check `CURRENT_STATE.md` first.
4. **Do not commit** `*_repo/` directories or `results/` (gitignored).
5. **Scope discipline:** read `RESEARCH_INTENT.md`. No MAS work, no feature creep.

---

## Current Priorities

See `CURRENT_STATE.md` for the authoritative task list.

Current workstream status:
- Workstream A (retrieval eval): [ACTIVE] — retrieval matrix complete; deterministic reruns may still be pending
- Workstream B (patching pipeline): [DONE] — N=100 pilot complete, numbers locked in `CLAIMS_LOCK.md`
- Workstream C (paper writing): [DONE] — 15-page two-column paper, all Table 3 cells filled, clean compile

---

## Key Commands

```bash
# Retrieval experiment
./.venv/bin/python run_experiment.py --repo-name pallets/flask \
  --source-prefix src/flask --n-issues 10 --manager-max-turns 6 --rag-max-turns 6

# Patching — Stage 1: generate patches (no Docker/Modal needed)
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml

# Patching — Stage 1+2 combined (evaluate inline, requires Docker or --modal)
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate [--modal]

# Patching — Stage 2 only: run harness on an existing predictions.json
./.venv/bin/python run_patch.py --manifest patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate-only --run-dir results/patch_runs/<run_id> [--modal]

# Test suite
./.venv/bin/python -m unittest discover -s tests -v
```
