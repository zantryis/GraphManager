# V2 Pilot Results (psf/requests, n=8 each)

Date: 2026-02-24

| Method | Patched | Apply Success | Resolved | Total Cost Tokens | Cost / Resolved | Summary |
|---|---:|---:|---:|---:|---:|---|
| oracle | 8/8 | 100.0% | 4/8 (50.0%) | 61,490 | 15,372.50 | `results/v2_pilot_parallel/pilot_oracle_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json` |
| bm25 | 7/8 | 87.5% | 4/8 (50.0%) | 289,433 | 72,358.25 | `results/v2_pilot_parallel/pilot_bm25_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json` |
| gm_progressive | 7/8 | 87.5% | 5/8 (62.5%) | 366,129 | 73,225.80 | `results/v2_pilot_parallel/pilot_gm_progressive_v1_session_20260223_210845/patch_runs/20260223_210845/patch_summary.json` |

Notes:
- All three runs were launched concurrently and evaluated with `--modal`.
- Harness run IDs are now method/path-scoped in code to avoid cross-run collisions.
