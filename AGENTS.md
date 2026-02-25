# AGENTS.md -- How to operate in this repo

## On session start

Read these files in this order:

1. **`STATE.md`** -- what is done, what is next, known risks
2. **`TASKS.md`** -- the task backlog; find your assigned task
3. **`RESEARCH_INTENT.md`** -- paper scope and claims (do not violate)
4. **`CLAIMS_LOCK.md`** -- permitted claim strength

If STATE.md and RESEARCH_INTENT.md conflict: RESEARCH_INTENT.md wins on scope;
STATE.md wins on execution status.

## Rules

1. **One task at a time.** Find the single `[ACTIVE]` task in TASKS.md. Work only on that.
2. **TDD for all behavior changes.** Write a failing test -> implement -> run `make verify`.
3. **Do not re-run frozen experiments.** Check STATE.md before running anything.
4. **Do not create new tasks.** Append ideas to the Parking Lot in STATE.md.
5. **Do not change RESEARCH_INTENT.md or CLAIMS_LOCK.md.** Only the researcher does that.
6. **Do not commit results/ or logs/.** Both are gitignored.
7. **Record provenance.** Every patch run produces `run_meta.json` with git SHA, manifest hash, dep versions.

## Health check

```bash
make verify    # 242 tests + import lint -- must pass before ANY code change
make smoke     # quick pipeline plumbing test (no API key needed)
```

## On session end

1. Update STATE.md: mark completed items, record run IDs / metrics, update "Next action"
2. Update TASKS.md: mark your task `[DONE]` if acceptance criteria are met
3. Write a dev log in `dev_logs/YYYY-MM-DD-<slug>.md` for non-trivial changes

## Key commands

```bash
# Retrieval experiment
./.venv/bin/python run_experiment.py --repo-name pallets/flask \
  --source-prefix src/flask --n-issues 10

# Patching -- Stage 1 only (no Docker needed)
./.venv/bin/python run_patch.py --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml

# Patching -- Stage 1+2 (requires Docker or --modal)
./.venv/bin/python run_patch.py --manifest patch_manifests/v2_verified/pilot_oracle_v1.yaml \
  --evaluate --modal

# Batch pool (parallel across repos)
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list <list.txt> --results-dir results/v2_full_runs \
  --max-parallel-repos 8 --resume-incomplete

# Full test suite
make test
```

## What NOT to do

- Do not build MAS orchestration (Paper 2 scope)
- Do not modify V1 frozen results or the archived paper
- Do not skip the pilot before a full run
- Do not compare against external systems by running their code
- Do not add features not needed for the current experiment
