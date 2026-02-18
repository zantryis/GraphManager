# 2026-02-18 - Minimal Patching Pipeline (Phase 2)

## Context

- Retrieval evaluation is stable: 11 valid cells, all ci_ready=True, gm_progressive
  consistently outperforms rag_progressive across repos and tracks.
- Next step is an end-to-end anchor: retrieval → patch generation → SWE-bench harness evaluation.
- Goal is to report pass@1 / resolved-rate alongside retrieval F1 and token cost in one run.

## Decision

Added a minimal patching stage as a new optional pipeline layer:

1. `src/patch_agent.py`: `PatchAgent` class.
   - Single/few-turn (default max_turns=3) Gemini-based patch generator.
   - Takes prepared issue text + list of retrieved files with content.
   - Produces a unified diff wrapped in `<patch>...</patch>` tags.
   - `CANNOT_PATCH` signal if the model cannot determine the fix with confidence.
   - Handles API errors gracefully; retries if patch tag is missing from response.

2. `run_patch.py`: CLI pipeline runner.
   - Loads a YAML manifest (dataset, instance_ids, retrieval_method, turns config).
   - Runs retrieval stage (gm_progressive, gm_deterministic, or rag_progressive).
   - Runs PatchAgent for each issue on retrieved files.
   - Saves per-instance patches to `results/patch_runs/<run_id>/patches/`.
   - Writes SWE-bench-compatible `predictions.json`.
   - If `--evaluate` flag is set AND Docker is available: runs swebench harness,
     parses resolved-rate, writes to patch_summary.json.
   - If Docker not available: skips evaluation with clear warning, preserves predictions.

3. `patch_manifests/swebench_verified_requests_v1.yaml`: First fixed manifest.
   - 8 psf/requests instances from SWE-bench Verified.
   - Uses gm_progressive retrieval (best F1 from retrieval evaluation).

## Alternatives Considered

1. Full MAS (multi-agent) patching — rejected per AGENTS.md; too early.
2. Using a dedicated "code editing" agent with read_file / write_file tools — deferred;
   the single-turn diff generation is simpler to validate and cheaper.
3. Integrating patch generation directly into run_experiment.py — rejected; keeps
   retrieval-only and patching pipelines cleanly separated.

## Evidence

- Dry-run confirmed: pipeline builds graph/RAG indices (9018 / 36736 est. tokens for
  requests at snapshot_commit), validates non-empty, loads 8 instances, saves predictions.
- All 16 PatchAgent tests pass (extraction, file reading, token accounting, error handling).
- All 3 runner manifest tests pass.
- Full test suite: 89 tests, all passing.

## Consequences

- End-to-end patching can now be run with:
  ```
  ./.venv/bin/python run_patch.py \
      --manifest patch_manifests/swebench_verified_requests_v1.yaml \
      --evaluate \
      --results-dir results
  ```
- Requires GEMINI_API_KEY and (for evaluation) Docker daemon running.
- Token cost estimate: ~9000 setup + ~4000 retrieval + ~20000-40000 patch per issue
  (rough, depends on file sizes and patch complexity).

## Follow-up

1. Run the actual pipeline (non-dry-run) on requests_v1 manifest.
2. Add `--evaluate-only` flag to re-run harness on existing predictions.json.
3. Add pytest strict + flask manifests for broader coverage.
4. After first resolved-rate results: add to research_report/ and README.
5. Coefficient tuning for gm_deterministic (Phase 1 backlog).
