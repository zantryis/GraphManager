# SESSION_PLAYBOOK.md -- Canonical loop for continuing work

## Before you touch any code

```
1. make verify              # must pass
2. Read STATE.md            # understand current position
3. Read TASKS.md            # find the [ACTIVE] task
4. Read RESEARCH_INTENT.md  # know the scope boundaries
```

## Decide: what is the next action?

- If TASKS.md has an `[ACTIVE]` task: work on it.
- If no active task: read STATE.md "Next action" section. Do NOT self-assign; ask the researcher.
- If blocked: document the blocker in STATE.md and stop.

## Work loop

```
1. Write a failing test for the intended behavior change
2. Implement the minimal fix
3. make verify              # all 242+ tests must pass
4. If running an experiment:
   a. Use an existing manifest from patch_manifests/v2_verified/
   b. Run pilot first (8 instances), verify gates, THEN expand
   c. Check run_meta.json for provenance after run completes
5. Update STATE.md with results (run IDs, metrics)
6. Update TASKS.md (mark [DONE] if acceptance criteria met)
```

## Recording decisions

For any non-trivial decision (parameter change, method addition, scope adjustment):

1. Write a dev log: `dev_logs/YYYY-MM-DD-<slug>.md`
2. Include: context, options considered, decision, evidence, risks

## End of session checklist

- [ ] `make verify` passes
- [ ] STATE.md updated with what you did
- [ ] TASKS.md updated with task status
- [ ] Dev log written for non-trivial changes
- [ ] No uncommitted results/ or logs/ files staged

## Emergency: something is broken

1. Do NOT delete data or force-push
2. Record the error in STATE.md under "Known Issues"
3. If tests fail: fix the test or the code, never skip the test
4. If a run is stuck: check `tools/patch_dashboard.py` or inspect `predictions_partial.jsonl`

## Key invariants (never violate)

- `make verify` must always pass on main
- V1 frozen results are read-only
- Every patch run must produce `run_meta.json` with provenance
- Retrieval and patching populations are documented separately (not conflated)
- Single repair sample per instance (document this in any paper table)
