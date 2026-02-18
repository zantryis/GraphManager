# 2026-02-18 — End-to-End Improvement Plan (Phase B onwards)

## Context

Retrieval evaluation (Phase A) is complete: 11 valid cells across 4 repos,
gm_progressive consistently outperforms rag_progressive, all ci_ready=True.

Patching pipeline (Phase B) is built but not yet producing clean results.
Latest run (20260218_120541): 8/8 patches generated, 1/8 resolved by harness.
Known failure modes identified from patch_summary.json inspection (see below).

This document synthesises two independent agent plans into a single sequenced
roadmap with concrete exit criteria.

---

## Known Failure Modes (Current State)

Before any research work, three engineering bugs are causing uninterpretable results:

| Failure | Root cause | Evidence |
|---------|-----------|---------|
| Truncated diffs | `max_output_tokens=4096` in PatchAgent | `stop_reason: FinishReason.MAX_TOKENS` on 1142, 1921, 6028 |
| Manager cuts off early | `manager_max_turns=4` in manifest | All 8 retrievals hit `stop_reason: max_turns`, exactly 4 tool calls each — never terminates naturally |
| File context cut short | `max_file_chars=8000` in PatchAgent | requests/sessions.py is ~1500 lines; at 8000 chars model sees ~250 lines |
| Harness results not captured | Bug in run_patch.py harness result parsing | `harness_results: null` in every patch_summary.json despite harness running |
| 3/8 retrieval misses | Manager ran out of turns before finding right file | 1142 (gold: models.py, got: sessions.py+api.py), 2317 (gold: sessions.py, got: models.py), 6028 (gold: utils.py, got: adapters.py) |

These are not research questions. Fix them before drawing any conclusions.

---

## Phase 0 — Engineering Prerequisites

**Goal:** remove noise sources so failures are attributable to retrieval quality
or model reasoning, not configuration bugs.

### 0a. Fix hard limits

In `src/patch_agent.py`:
- `max_output_tokens`: 4096 → 16384
- `max_file_chars`: 8000 → 24000

In `patch_manifests/swebench_verified_requests_v1.yaml`:
- `manager_max_turns`: 4 → 8

Rationale: a non-trivial unified diff for a 400-line file with 3-line context
can easily exceed 4096 tokens. At 8000 chars, requests/sessions.py is truncated
to ~250 lines. The manager at 4 turns always exhausts budget before naturally
concluding (it should emit the JSON result when done, not be cut off).

### 0b. Fix Docker harness result capture

Debug why `harness_results` is always null in `patch_summary.json`.
Options: the harness subprocess output is not being parsed, the predictions.json
format is wrong, or the harness is failing silently. Fix so results are
automatically captured and written.

### 0c. Add `git apply --check` validation

After PatchAgent returns a patch, run:
```bash
git apply --check <patch_file>
```
against the repo at the relevant base_commit before saving. If it fails, mark
the instance as `patch_status: apply_failed` rather than `patched`. This
distinguishes "model produced text" from "model produced a valid diff."

**Exit criteria for Phase 0:**
- Re-run 8-instance manifest: zero instances with `stop_reason: MAX_TOKENS`
- Manager stop_reason shows natural termination for at least some instances
- `patch_summary.json` contains a non-null `harness_results` entry
- `apply_failed` instances are correctly counted and excluded from patch_rate

---

## Phase 1 — Patch Robustness Gate

**Goal:** make the pipeline produce harness-safe diffs reliably, with automatic
recovery when generation fails. TDD throughout.

### 1a. Auto-repair retry loop (diff level)

When `git apply --check` fails, feed the error back to the patch agent:

```
"Your previous diff failed to apply with error: <git apply stderr>.
Common causes: wrong line numbers, missing context lines, path mismatch.
Please regenerate the patch."
```

Cap at 2 repair attempts. If still failing after 2 retries, mark `apply_failed`.
This is distinct from the existing max_turns retry (which handles missing patch
tags) — this handles syntactically-present but structurally-invalid diffs.

### 1b. Retrieval-level feedback signal (manager retry)

After Phase 0 raises max_turns to 8, add one retrieval retry path: if
PatchAgent emits `CANNOT_PATCH` or the diff fails apply-check after repair
attempts, record which files were tried and re-query the manager:

```
"The following files were retrieved but were insufficient to generate a patch:
[files]. Please search for additional context, particularly around [error hint]."
```

Cap at 1 retrieval retry. This addresses the 3/8 retrieval misses where the
manager found the wrong files.

### 1c. TDD test coverage

Add tests before implementing 1a and 1b:

**Diff validation tests (test_patch_agent.py):**
- `test_apply_check_passes_on_valid_diff` — valid diff passes git apply --check
- `test_apply_check_fails_on_truncated_diff` — truncated hunk fails and is caught
- `test_apply_check_fails_on_wrong_path` — wrong file path fails and is caught
- `test_repair_retry_on_apply_failure` — auto-repair is attempted on fail
- `test_max_repair_retries_respected` — stops after 2 repair attempts
- `test_retrieval_retry_on_cannot_patch` — manager is re-queried on CANNOT_PATCH

**Regression tests:**
- `test_max_output_tokens_not_truncating` — mock response at 4096 tokens is
  detected and flagged (ensures the limit is high enough)
- `test_malformed_diff_without_hunk_header` — caught before submission
- `test_raw_diff_without_tags_parsed_correctly` — existing fallback still works

**Exit criteria for Phase 1:**
- `apply_success_rate >= 90%` on the 8-instance manifest
- Zero instances where `patch_status=patched` but diff fails `git apply --check`
- All new tests passing, full suite still green

---

## Phase 2 — Baseline Establishment

**Goal:** make the 1/8 result scientifically interpretable before scaling up.
This requires comparison points. Run on the same 8-instance manifest.

### 2a. Oracle retrieval run

Feed gold files directly to PatchAgent, bypassing the manager entirely.
This answers: "what is the ceiling for this patch agent given perfect retrieval?"

If oracle gets N/8 where N > current 1/8, the gap is retrieval quality.
If oracle also gets 1/8, the problem is model capability regardless of retrieval
— and the entire comparison exercise changes meaning.

Implementation: add `--gold-files` flag to `run_patch.py` that reads gold files
from the dataset and bypasses the retrieval stage.

### 2b. Cold-start baseline

Run PatchAgent with issue text only — no retrieved files, no context.
This answers: "how much does any retrieval help at all?"

If cold-start gets 0/8 and graph retrieval gets 2/8, retrieval is clearly adding
value. If cold-start gets 1/8, retrieval is not helping on this sample.

Implementation: add `retrieval_method: none` as a supported value in manifests.

### 2c. RAG patch baseline

Run `rag_progressive` retrieval → same PatchAgent on same 8 instances.
This is the direct graph vs RAG comparison at the end-to-end level, consistent
with what the retrieval-only evaluation already measures.

**After Phase 2, you have:**

| Method | Retrieval | Resolved / 8 | Apply success / 8 |
|--------|-----------|-------------|------------------|
| Cold start | none | ? | ? |
| RAG progressive | rag | ? | ? |
| GM progressive | graph | 1 (current, pre-fixes) | ? |
| Oracle | gold files | ? | ? |

This is the minimum table needed to make any claim about the system.

**Exit criteria for Phase 2:**
- All four rows filled with real harness numbers
- Oracle establishes an upper bound
- Direction of graph vs RAG consistent with retrieval F1 numbers from Phase A

---

## Phase 3 — Controlled Method Comparison

**Goal:** full method sweep on a fixed instance set with statistical validity.
Mirrors what Phase A did for retrieval-only evaluation.

### 3a. Full method sweep

Run all supported methods on the same manifest:
- `gm_progressive`
- `gm_deterministic`
- `rag_progressive`
- `raw_rag_function`
- `raw_rag_fixed`
- `no_retrieval` (cold start)

Hold constant: same 8 instances, same manifest, same model, same temperature.

### 3b. Repeat sets + paired analysis

Run each method 3 times (as in the retrieval eval). Compute:
- Per-instance paired deltas: `delta_i = resolved_i(graph) - resolved_i(rag)`
- Mean delta + 95% bootstrap CI
- Cost metrics: tokens (setup + query + patch), wall time

At N=8 the bootstrap CI will be wide — that is expected. This is still more
defensible than a single run.

### 3c. Cost vs quality tradeoff curves

For each method, plot (or tabulate):
- Total tokens (x) vs resolved rate (y)
- Setup tokens vs query tokens breakdown
- Apply success rate as a separate quality dimension

**Exit criteria for Phase 3:**
- All 6 methods have 3 repeat runs
- Ranking is stable across repeats (not dominated by single-run noise)
- Cost breakdown table written to `research_report/`

---

## Phase 4 — Scale-Out

**Goal:** enough instances for statistically meaningful claims. Minimum credible
sample for a retrieval+patching paper is 50–100 instances across 2+ repos.

### 4a. Expand psf/requests to full ~44 instances

All psf/requests instances exist in SWE-bench Verified or full SWE-bench.
At N=44, bootstrap CI narrows to ±7-8 percentage points — defensible.

### 4b. Add pallets/flask

Flask is the next most tractable — 11 instances in SWE-bench Verified, already
covered in the retrieval eval. Cross-repo results are necessary to claim
generalization beyond psf/requests.

### 4c. Reproducibility infrastructure

- Pinned manifests per repo (instance IDs, splits, model config)
- Split dev track (for iteration) from frozen track (for report claims)
- Frozen artifact bundle per scale-out run under `research_report/artifacts/`
- `visualize_results.py` updated to render patching results alongside retrieval

**Exit criteria for Phase 4:**
- ≥ 50 instances across ≥ 2 repos
- Frozen manifest + artifact bundle committed
- Results reproducible from manifest alone (no manual steps)

---

## Phase 5 — Amortization Study

**Goal:** validate the core thesis — "shared world model reduces cost as N scales."
This is what distinguishes the paper from a standard retrieval comparison.

### 5a. Same-snapshot track

Fix one repo snapshot (single commit/tag). Build graph once. Run all N issues
against it. Record:
- Setup cost: paid once
- Query cost: paid per issue
- Total amortized cost per issue = (setup + N × query) / N

Compare to RAG same-snapshot (also builds once).

### 5b. Strict-commit-fidelity track

Per-issue at its own base_commit. Cache index builds by commit hash.
This is the conservative "realistic" estimate.

Report both tracks. Do not mix them.

### 5c. Break-even N calculation

From EVALUATION_SPEC.md formula:
```
N_break_even = (setup_graph - setup_rag) / (runtime_rag - runtime_graph)
```
If break-even is N=3 and the experiment runs N=44, that is a compelling
amortization story. If break-even is N=50 and the experiment only runs N=8,
the amortization claim is weak.

### 5d. High-repeat-ratio repo selection

psf/requests has only 6.8% commit repeat ratio — weak amortization signal
in the strict-commit track. For a strong amortization result, add one repo
with higher repeat ratio (measured in EVALUATION_SPEC.md):
- `pandas-dev/pandas`: 26.2% repeat ratio
- `tiangolo/fastapi`: 25.0%
- `conda/conda`: 22.4%

**Exit criteria for Phase 5:**
- Both tracks (same-snapshot, strict-commit) reported side by side
- Break-even N computed for gm_progressive vs rag_progressive
- At least one high-repeat-ratio repo included in the strict-commit track

---

## Dependency Graph

```
Phase 0 (engineering prereqs)
  └── Phase 1 (robustness gate)
        └── Phase 2 (baseline establishment)   ← minimum for any claim
              └── Phase 3 (controlled comparison)
                    └── Phase 4 (scale-out)
                          └── Phase 5 (amortization study)   ← core thesis
```

Phases 0–2 are prerequisites for any publishable result.
Phases 3–5 are the research contribution.

Do not skip Phase 2 to go directly to Phase 4. An N=44 result with no oracle
or cold-start baseline is still uninterpretable.

---

## What Each Phase Answers

| Phase | Question answered |
|-------|-----------------|
| 0 | Are the current failures real or configuration bugs? |
| 1 | Can the pipeline reliably produce valid, applicable diffs? |
| 2 | Is retrieval actually helping, and how much is the model's ceiling? |
| 3 | Which retrieval method produces the best end-to-end outcome at what cost? |
| 4 | Does the result hold across repos and at statistically meaningful sample sizes? |
| 5 | Does the graph world model amortize cost as the core thesis claims? |
