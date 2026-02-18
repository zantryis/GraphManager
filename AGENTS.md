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

High-level:
- Workstream A: run `gm_deterministic` on Flask, Requests, Pytest
- Workstream B: run clean 8-instance patching baseline, then oracle, then 30-instance pilot
- Workstream C: blocked on B results; fill gm_deterministic rows in Table 1 when A is done

---

## Key Commands

```bash
# Retrieval experiment
./.venv/bin/python run_experiment.py --repo-name pallets/flask \
  --source-prefix src/flask --n-issues 10 --manager-max-turns 6 --rag-max-turns 6

# Patching run
./.venv/bin/python run_patch.py patch_manifests/swebench_verified_requests_v1.yaml \
  --evaluate

# Test suite
./.venv/bin/python -m unittest discover -s tests -v
```
