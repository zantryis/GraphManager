# 2026-02-24 - Retrieval-to-Patch Fairness Cap

## Context

- User requested final validation of cross-method comparability before proceeding with V2 baseline rebuild.
- Review found one key confound: methods returned different default file counts into the patch stage
  (e.g., BM25 top-k=10 vs progressive agents typically returning <=6).
- This could bias patch outcomes by context volume rather than retrieval quality.

## Decision

- Add a global post-retrieval cap in patching pipeline:
  - `retrieval_max_files_for_patch` (default `6`; `null` disables).
- Apply cap uniformly before patch generation on:
  - initial retrieval output
  - retrieval-retry output
- Surface cap telemetry in per-instance results and summary metadata.
- Make cap explicit in all V2 manifests.

Scope boundaries:
- No change to retrieval-only evaluation (`run_experiment.py`) behavior.
- No change to patch model or retry policy.

## Alternatives Considered

1. Leave method-native top-k behavior untouched.
   Tradeoff: preserves original behavior but keeps comparability confound.
2. Force each retrieval method to internally return same top-k.
   Tradeoff: invasive across multiple agents and modes.
3. Apply one global post-retrieval cap at patch boundary.
   Tradeoff: simple and auditable; chosen.

## Evidence

- Code changes:
  - `run_patch.py`
    - new `_cap_retrieved_files(...)`
    - manifest parsing + print for `retrieval_max_files_for_patch`
    - cap applied in initial/retry retrieval paths
    - per-instance fields added: pre/post cap counts + cap value
    - summary field added: `retrieval_max_files_for_patch`
  - `tools/generate_v2_verified_manifests.py`
    - emits `retrieval_max_files_for_patch: 6`
  - `patch_manifests/v2_verified/*.yaml`
    - all manifests now include explicit cap key
- Tests:
  - Added `RetrievalFileCapTests` in `tests/test_patch_runner.py`
  - Targeted: `./.venv/bin/python -m unittest tests.test_patch_runner -v` (35 tests pass)
  - Full suite: `./.venv/bin/python -m unittest discover -s tests -v` (191 tests pass)

## Consequences

- Expected benefits:
  - Cleaner ablation fairness at the retrieval→patch boundary.
  - Patch context volume is controlled and method-invariant by default.
  - Explicit manifest knob enables controlled sweeps (`6`, `8`, `10`, etc.).
- Known risks:
  - Hard cap may remove useful files for methods that produce high-recall candidate sets.
  - Requires reporting pre/post cap counts to detect aggressive truncation.
- Monitoring signals:
  - `retrieved_files_pre_cap` vs `retrieved_files_post_cap`
  - method-wise truncation rate
  - resolved-rate sensitivity to cap value

## Follow-up

1. Add cap-sensitivity mini-ablation (`6` vs `8` vs `10`) on pilot manifests.
2. Keep default `6` for headline fairness runs unless ablation indicates harmful truncation.
3. Ensure upcoming `repomap_like` / `agentless_like_localization` methods use same cap contract.
