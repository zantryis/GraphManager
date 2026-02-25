# Retrieval Redesign V1 (Deterministic Graph-First)

Goal: replace loop-heavy retrieval with a deterministic, explainable, lower-cost mechanism that preserves or improves F1.

## Why redesign

Current retrieval in `ManagerAgent` and `RAGAgent` relies on multi-turn tool loops. This can:

1. increase token and latency cost,
2. make ranking behavior harder to audit,
3. reduce recall when confirmation gates are strict.

This redesign keeps graph-aware retrieval, but moves ranking and candidate selection to a deterministic scorer.

## Design principles

1. One semantic seed retrieval call per issue.
2. Bounded graph expansion with fixed limits.
3. Explicit evidence scoring per file.
4. No hard exclusion unless path grounding fails.
5. Same input and config produce same output.
6. Keep current looped modes as ablations, not default.

## High-level flow

For one issue:

1. prepare issue text (existing `prepare_issue_text` in `src/evaluation.py`)
2. semantic seed retrieval from `GraphIndex.search`
3. bounded bidirectional graph walk from seeds
4. aggregate node/edge evidence onto files
5. compute deterministic file scores
6. return top-K files with evidence trace

## Retrieval algorithm (concrete)

### Step 1: seed nodes

- call `GraphIndex.search(query, top_k=K_seed)` once
- take top `K_seed` nodes (default 8)
- keep node score as normalized semantic evidence

### Step 2: bounded expansion

From each seed node, run BFS with:

- max depth `D` (default 2)
- max neighbors per node `N` (default 12)
- allowed edge types: `CALLS`, `IMPORTS`, `INHERITS`, `DEFINES`, `CONTAINS`
- traversal both outgoing and incoming

Record each discovered path:

- source seed,
- traversed edge types,
- edge confidence (if present),
- destination node/file.

### Step 3: file evidence aggregation

Map each visited node to a file and aggregate:

1. semantic evidence from seeds
2. graph support counts (independent paths)
3. confidence-weighted edge support
4. light path-similarity/context bonus
5. penalties for weak-only support

## Scoring formula

Let each component be normalized to `[0, 1]`.

`score(file) =`
`  w_sem * S_sem(file)`
`+ w_graph * S_graph(file)`
`+ w_conf * S_conf(file)`
`+ w_hint * S_hint(file)`
`- w_pen * S_pen(file)`

Where:

1. `S_sem`: max or mean seed similarity hitting this file.
2. `S_graph`: graph support strength.
- example: `log(1 + unique_paths)` and edge-type diversity.
3. `S_conf`: confidence quality of supporting paths.
- edge weights: `high=1.0`, `medium=0.6`, `low=0.2`
4. `S_hint`: lexical/path hint overlap from issue text and file/module names.
5. `S_pen`: penalties.
- file supported only by low-confidence paths,
- too many shallow weak paths with no strong support.

Tie-breakers:

1. higher count of high-confidence paths,
2. shorter average path length,
3. lexicographic file path.

## Initial default coefficients

Start with:

- `w_sem = 0.35`
- `w_graph = 0.30`
- `w_conf = 0.20`
- `w_hint = 0.10`
- `w_pen = 0.05`

These are starting points, not final.

## Coefficient tuning protocol

Tune coefficients on a frozen dev split only.

### Objective

Primary objective:

- maximize `F1` under token budget constraint.

Alternative scalar objective:

- `utility = F1 - lambda * log(1 + runtime_tokens)`

Use this only if constraint-based selection is unstable.

### Search strategy

1. coarse grid over weight ranges:
- `w_sem in [0.2, 0.5]`
- `w_graph in [0.2, 0.5]`
- `w_conf in [0.1, 0.3]`
- `w_hint in [0.0, 0.2]`
- `w_pen in [0.0, 0.2]`
2. normalize weights if needed
3. select top region
4. fine search around top region

### Stability checks

Candidate weights must pass:

1. non-negative paired F1 delta vs current `gm_progressive` on dev median,
2. token reduction target met (for example, >=25 percent runtime-token reduction),
3. bootstrap CI for paired deltas not dominated by zero across main cells.

Freeze final coefficients and write them to artifacts and docs.

## Required ablations

Run and report:

1. deterministic retriever vs current `gm_progressive`
2. no-confidence term (`w_conf=0`)
3. no-penalty term (`w_pen=0`)
4. semantic-only (`w_graph=0`)
5. graph-only (`w_sem=0`)

This proves what each component contributes.

## Integration plan in this repo

### New module

- add `src/deterministic_retrieval.py` with:
1. `DeterministicGraphRetriever`
2. `score_file_evidence`
3. evidence trace serializer

### Existing modules to wire

1. `src/evaluation.py`
- add method variant, for example `gm_deterministic`
- record runtime token usage and retrieval trace metadata
2. `run_experiment.py` / `run_suite.py`
- expose config options:
  - seed_k, depth, neighbor_cap
  - coefficients
  - retrieval mode
3. `visualize_results.py`
- add cards/plots for:
  - coefficient profile
  - evidence composition per method
  - cost-quality frontier including deterministic mode

### Keep current modes

- keep `gm_progressive` and `rag_progressive` unchanged for baseline comparability.

## Test plan (TDD)

Add failing tests before implementation:

1. deterministic output ordering for fixed graph/input
2. monotonic effect of high-confidence support on ranking
3. penalty application for low-confidence-only files
4. no ungrounded file leakage after canonicalization
5. budget guard: expansion never exceeds depth/fanout caps
6. regression: a valid file is not dropped only because it was not "confirmed" by a looped tool

## Acceptance criteria

1. Full unit suite passes.
2. Deterministic mode beats or matches `gm_progressive` F1 on dev aggregate.
3. Runtime tokens reduced materially versus `gm_progressive`.
4. Paired delta and bootstrap CI are reported for strict and same-snapshot tracks.
5. Final weights and run settings are frozen in artifacts.

## Risks and mitigations

1. Overfitting coefficients to small dev sets.
- mitigation: multi-repo dev split, repeated runs, bootstrap CI.
2. Over-pruning by strict budgets.
- mitigation: ablate depth/fanout; monitor recall impact.
3. Underuse of semantic signals on vague issues.
- mitigation: keep semantic seed term strong enough; allow tuned `K_seed`.

## Provenance alignment

This redesign aligns with prior work direction:

1. deterministic AST-derived graph as primary structure,
2. semantic retrieval for seed discovery,
3. graph traversal for multi-hop dependency grounding.

It intentionally differs from loop-heavy orchestration by making scoring local, explicit, and reproducible.
