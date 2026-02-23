# 2026-02-21 - Targeted Reruns Launched + Full Paper Update

## Context

- Picked up project after v4 auto-finalize agent completed Phase 2/5.
- All 9 `none` runs complete; Phase 3 analysis already refreshed; rerun gate = YES.
- User flagged paper as stale; previous agent died mid-run leaving some v4 docs potentially incomplete.

## Decisions

1. **Targeted reruns**: Use same existing manifests from `patch_manifests/n100_verified/` (same frozen
   instance IDs, same parameters). New runs get new run IDs. After completion, update `FROZEN_RUN_IDS`
   in `tools/analyze_v4_handoff.py` for 6 entries (3 repos × 2 methods). Justification: manifests define
   the experiment; updating the analysis script's run-ID lookup is the intended update path.

2. **Sequential execution**: API-friendly, matches previous unattended supervisor strategy. Single
   shell script at `/tmp/targeted_reruns.sh` with `set -euo pipefail` for fail-fast on errors.
   Background task ID: `b8242f4`. Log: `/tmp/targeted_reruns.log`. Run IDs file: `/tmp/rerun_ids.txt`.

3. **`--manifest` flag**: CLAUDE.md showed positional argument, but `run_patch.py` requires `--manifest`.
   Fixed in shell script on second launch attempt. Root cause: CLAUDE.md command example was stale.

4. **Full paper update**: All sections updated in a single session pass (see evidence below).
   `RESEARCH_INTENT.md` unchanged per policy.

## Evidence

### Targeted reruns
- Script: `/tmp/targeted_reruns.sh`
- Order: sympy GM → sympy RAG → sphinx GM → sphinx RAG → matplotlib GM → matplotlib RAG
- Run 1 confirmed started: `results/patch_runs/20260221_111111/patches/` directory exists
- All 6 manifests verified present in `patch_manifests/n100_verified/`
- No active supervisor processes at session start

### Paper updates (all in `research_report/sections/`)

| File | Changes |
|------|---------|
| `00_abstract.tex` | Added patching pilot sentence (42% GM vs 33% RAG, 4.9× CPR advantage) |
| `01_introduction.tex` | Added 4th contribution: patching pilot |
| `04_experimental_setup.tex` | Model: `gemini-2.0-flash` → `gemini-3-flash-preview`; turns: 4 → 8; added patching setup subsection with dual-build disclosure and timeout accounting paragraph |
| `05_results.tex` | gm_deterministic Table 1 rows filled (0.679/0.520/0.473); gm_det added to amortization table (Requests); gm_det added to cost table (706K total); claims-lock violation at line 64 softened; patching pilot section added (Tables 4+5, key observations); section intro updated |
| `06_discussion.tex` | Added patching findings paragraph; updated limitations to mention patching and correct model name |
| `07_threats_to_validity.tex` | Model name corrected; construct validity updated; timeout censoring threat paragraph added |
| `08_conclusion.tex` | Updated to mention patching pilot (42%/4.9× CPR); removed "without downstream patch generation" stale language |

### gm_deterministic numbers used
- Strict (single runs, `--methods gm_deterministic --deterministic-config-path configs/gm_deterministic_selected_v1.json`):
  - Flask (`20260218_220114`): F1=0.679, runtime=1,316, setup=153,750, total=155,066
  - Requests (`20260218_220148`): F1=0.520, runtime=1,727, setup=107,557, total=109,284
  - Pytest (`20260218_220227`): F1=0.473, runtime=2,361, setup=439,747, total=442,108
- Same-snapshot Requests (`20260218_221920`): F1=0.603, runtime=1,727, setup=9,018, total=10,745

### CURRENT_STATE.md fixes
- Duplicate "none baseline status INCOMPLETE" block removed (replaced with one-liner pointing to ledger)
- Workstream B next actions updated (steps 1-2 marked done, step 3 marked in-progress)
- Workstream C status updated with all completed paper changes
- Frozen run table updated: none run IDs filled for all 9 repos; rerun-pending noted for sympy/sphinx/matplotlib GM+RAG

## Consequences

- Paper is substantially more current: includes patching pilot section, correct model names, gm_det rows.
- `CLAIMS_LOCK.md` constraints honored throughout: patching results framed as exploratory/directional.
- Targeted reruns are running; once complete, `FROZEN_RUN_IDS` update + analysis refresh + table final-lock remain.

## Follow-up

1. Monitor reruns via `tail /tmp/targeted_reruns.log` or `cat /tmp/rerun_ids.txt`.
2. When all 6 complete:
   a. Update `FROZEN_RUN_IDS` in `tools/analyze_v4_handoff.py` for 6 entries.
   b. Re-run: `./.venv/bin/python tools/analyze_v4_handoff.py`
   c. Update patching tables in `05_results.tex` with final numbers.
   d. Final `CURRENT_STATE.md` update with locked run IDs.
3. Consider whether to also freeze `none` run IDs explicitly in the analysis script (currently dynamic).
