# Graph-Augmented Manager

**Can a structured knowledge graph enable more precise file retrieval than vector-search RAG for multi-agent software engineering?**

This project compares four code file retrieval strategies on real GitHub issues from [SWE-bench](https://www.swebench.com/), measuring both retrieval quality (precision/recall/F1) and token cost.

## Architecture

```
GitHub Issue ──▶ Manager Agent ──▶ Relevant Files
                 (Gemini + tools)
                       │
                Knowledge Graph
                (AST + vectors)
```

### Methods Compared

| Method | Strategy | LLM? |
|--------|----------|------|
| **Graph-Manager** | Navigates a knowledge graph via 3 tools: `search_nodes`, `get_neighbors`, `get_file_summary` | Yes |
| **RAG-Agent** | Searches a code-chunk vector index via `search_codebase` | Yes |
| **Raw-RAG (func)** | Pure vector similarity over function-level chunks | No |
| **Raw-RAG (fixed)** | Pure vector similarity over fixed-size chunks | No |

Both agent methods use **Gemini 2.0 Flash** with identical prompting — only the retrieval tool differs.

### Knowledge Graph

Built from static AST analysis (tree-sitter):

- **Nodes**: files, classes, functions (with signatures and docstrings)
- **Edges**: `DEFINES`, `IMPORTS`, `CALLS`, `CONTAINS`
- **Vector index**: FAISS over node names + docstrings for fuzzy entry points

No LLM calls required to build the graph. Setup cost is 3-4x cheaper than RAG chunk embedding.

### Retrieval Modes

Each agent method supports two modes:

- **Baseline**: More exploratory — larger search results, more tool calls, lenient stopping
- **Progressive**: More targeted — constrained search, early stopping, compact responses

## Results (Flask, n=10)

| Method | Precision | Recall | F1 | LLM Tokens/Issue | Setup Tokens |
|--------|-----------|--------|----|-------------------|--------------|
| **Graph-Manager** | **0.850** | **0.842** | **0.786** | 25,128 | 19,890 |
| RAG-Agent | 0.667 | 0.650 | 0.620 | 8,312 | 76,135 |
| Raw-RAG (func) | 0.170 | 0.875 | 0.266 | 0 | 76,135 |
| Raw-RAG (fixed) | 0.145 | 0.908 | 0.237 | 0 | 39,598 |

**Key findings:**

- Graph-Manager achieves the highest F1 (0.786), beating RAG-Agent by +27%
- Graph-Manager is substantially more precise (0.85 vs 0.67) — when it picks a file, it's usually correct
- Graph setup cost is 3.8x cheaper (19.9k vs 76.1k tokens) because it embeds signatures, not full code bodies
- Per-issue LLM cost is higher for Graph-Manager (25k vs 8k tokens) but amortizes over many issues on the same repo
- Raw-RAG gets high recall but very low precision — not useful for automated systems

## Quick Start

```bash
# Clone and set up
git clone <repo-url> && cd GraphManager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Add your Gemini API key
cp .env.example .env
# Edit .env: GEMINI_API_KEY=your-key-here

# Run the experiment
python run_experiment.py --n-issues 10 --manager-max-turns 10 --rag-max-turns 10
```

### CLI Options

```
python run_experiment.py [OPTIONS]

--n-issues N              Number of issues to evaluate (default: 10)
--manager-max-turns N     Tool-calling budget for Graph-Manager (default: 6)
--rag-max-turns N         Tool-calling budget for RAG-Agent (default: 6)
--manager-mode MODE       baseline or progressive (default: progressive)
--rag-mode MODE           baseline or progressive (default: progressive)
--repeats N               Run N times for variance estimation (default: 1)
--source-prefix PATH      Restrict indexing to these paths (repeatable)
```

### Visualize Results

```bash
python visualize_results.py
# Opens results/compare.html — interactive dashboard with per-issue drill-down
```

## Project Structure

```
run_experiment.py          CLI entry point
visualize_results.py       HTML dashboard generator
src/
  graph_builder.py         tree-sitter AST → NetworkX graph + FAISS index
  manager_agent.py         Gemini agent with graph navigation tools
  rag_baseline.py          RAG baselines (agent + raw vector search)
  evaluation.py            SWE-bench loading, metrics, experiment orchestration
```

## Limitations

1. **Small sample** — SWE-bench has limited Flask issues (n~11). Statistical significance requires testing on larger repos.
2. **Single repository** — Results shown for Flask only. The graph advantage may vary with repo size and structure.
3. **Retrieval only** — We measure file-level retrieval, not end-to-end patch generation (Pass@1).
4. **Static analysis** — Dynamic dispatch (`getattr`, decorators) is not captured in the graph.

## Dependencies

- `tree-sitter` + `tree-sitter-python` — AST parsing
- `networkx` — Graph storage and traversal
- `google-genai` — Gemini API (LLM + embeddings)
- `faiss-cpu` — Vector similarity search
- `datasets` — HuggingFace dataset loading (SWE-bench)
- `gitpython` — Repository cloning
