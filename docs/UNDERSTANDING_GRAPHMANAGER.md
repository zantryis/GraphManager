# Understanding GraphManager (Plain Language)

This guide explains the project in direct, practical terms.

## 1) What problem this project solves

When an agent sees a software issue, it often reads too much code and still misses the right files.
That is expensive and noisy.

GraphManager's idea is to separate:

1. navigation (find where the change should happen)
2. execution (actually edit/patch code, future step)

In this repo, we are mainly evaluating navigation quality and cost.

## 2) Core idea mapped to your original proposal

From `idea.md`, the key idea is a shared "world model".
In code, that world model is:

- `src/graph_builder.py`: builds a graph from repository AST
- `src/resolvers.py`: resolves imports/types/calls to create meaningful edges

Manager agent uses graph tools to choose files:

- `src/manager_agent.py`

RAG baseline uses vector chunks instead of graph traversal:

- `src/rag_baseline.py`

Evaluation compares both under matched settings:

- `src/evaluation.py`
- `run_experiment.py`
- `run_suite.py`

## 3) What happens in one run

1. load issue set from dataset adapter
2. checkout target commit(s)
3. build graph and RAG indexes
4. run each method on same issues
5. compute file-level precision/recall/F1
6. compute token cost blocks (setup + runtime)
7. save artifacts under `results/runs/<run_id>/`

## 4) Why strict vs same-snapshot matters

Strict:
- realistic commit fidelity
- less reuse opportunity

Same-snapshot:
- controlled amortization test
- setup reused across many tasks

Both are needed. They answer different questions.

## 5) How to read current evidence quickly

1. start with repeat sets in `results/repeat_sets/`
2. check gates (`ci_ready`, `min_repeats_met`)
3. compare `gm_progressive` vs `rag_progressive` first
4. only trust claims backed by frozen artifact paths in `research_report/artifacts/`

## 6) How to verify the system yourself (fast path)

1. run tests:
```bash
./.venv/bin/python -m unittest discover -s tests -v
```

2. run one strict small experiment:
```bash
./.venv/bin/python run_experiment.py \
  --repo-name psf/requests \
  --task-family swe-bench \
  --dataset-name SWE-bench/SWE-bench \
  --source-prefix requests \
  --n-issues 3
```

3. inspect:
- `results/runs/<run_id>/summary.json`
- `results/runs/<run_id>/detailed_results.json`

## 7) Current limitations (important)

1. many repeated slices are still small (`n=3`), not publication-final
2. PolyBench repeat completeness has had API stability issues
3. retrieval-only focus is stronger than full patch execution evidence (so far)

