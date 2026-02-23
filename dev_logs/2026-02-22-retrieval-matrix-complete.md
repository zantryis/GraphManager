# Dev Log: Retrieval Matrix Complete (2026-02-22, Session 2)

## Summary

Completed the pending retrieval experiment cells for yt-dlp, LangChain, and Keras.
All Table 3 cells are now filled. Paper compiles clean (15 pages, 492 KB, 0 overfull).

## Completed Runs

| Repo | Track | Run dir | Key F1s |
|------|-------|---------|---------|
| yt-dlp (n=5, SWE-PolyBench) | strict | `results/runs/20260222_032232/` | GM-prog=0.347, RAG-prog=0.114, GM-det=0.297 |
| yt-dlp (n=5, SWE-PolyBench) | same-snap | `results/runs/20260222_033353/` | GM-prog=0.347, RAG-prog=0.200 |
| LangChain (n=10, SWE-PolyBench) | strict | `results/runs/20260222_035932/` | GM-prog=0.783, RAG-prog=0.366, GM-det=0.452 |
| Keras (n=10, SWE-PolyBench) | strict | `results/runs/20260222_040949/` | GM-det=0.274, GM-prog=0.267, RAG-prog=0.162 |

LangChain same-snapshot and Keras same-snapshot were skipped (strict track sufficient for Table 3).

## Incident: 503 API Error During LangChain Graph Build

The original run script (`/tmp/run_pending_retrieval.sh`) crashed at [5/8] LangChain strict
due to `google.genai.errors.ServerError: 503 UNAVAILABLE` during embedding. The error
was transient; retry after ~20 minutes succeeded. Root cause: likely a momentary API endpoint
outage at ~03:40 MST.

Resolution: Created a partial retry script (`/tmp/run_langchain_keras_strict.sh`) for just
LangChain and Keras strict tracks.

## Paper Changes

- `05_results.tex` tab:main_results: all 7 method × 7 repo cells filled
- Cross-benchmark section: per-repo observations added for all 4 new repos
- `07_threats_to_validity.tex`: statistical validity paragraph updated ("full retrieval matrix complete")
- `main.tex` compile: 0 overfull hbox, 0 overfull vbox, 15 pages, 492 KB

## Notable Finding

LangChain GM-prog F1 = 0.783 — the highest single-repo F1 across all 7 evaluated repos.
This is consistent with graph-guided methods benefiting from LangChain's high interconnection
density (many imports, call edges). GM-prog here substantially leads RAG-prog (0.366).

Keras: All methods score lower than on SWE-bench repos (GM-det/GM-prog ≈ 0.267–0.274).
This appears to be a benchmark difficulty effect rather than a method-specific failure —
all methods, including RAG baselines, score similarly low.

## CLAIMS_LOCK check

All new observations in cross-benchmark section use permitted framing:
- LangChain: "substantially outperforming" RAG-prog (permitted — quality comparison with cost context)
- Keras: "benchmark difficulty" — no quality-superiority framing

## Test suite

143 tests pass (run at session start; no code changes in session 2).
