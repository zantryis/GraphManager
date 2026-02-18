Research Proposal: The Graph-Augmented Manager
Working Title: Context is All You Need (to Share): Decoupling Exploration from Execution in Multi-Agent Software Engineering
1. Problem Statement
Current Multi-Agent Systems (MAS) for Software Engineering suffer from a "Cold Start" inefficiency. To understand a codebase, agents must independently traverse and read files. This creates two critical bottlenecks:
Linear Cost Scaling ($O(N)$): As the number of agents increases, the computational cost (tokens) and time required for context gathering scale linearly. Every new agent repeats the expensive exploration phase.
Context Fragmentation: Without a shared understanding, agents may overwrite each other’s work or lack global awareness of dependencies, leading to regression errors.
Core Insight: A human engineering manager does not read every line of code. They possess a high-level "mental map" of the system and direct developers to specific files relevant to a task. We aim to replicate this efficiency.

2. Proposed Solution: The Graph-Augmented Manager
We propose a hierarchical architecture that separates Context Exploration from Code Execution.
A. The "World Model" (The Map)
Instead of raw text, the system maintains a compressed, structured representation of the repository.
Structure: A Static Knowledge Graph (built via AST parsing).
Nodes: Files, Classes, Functions.
Edges: Imports, Defines, Calls, Inherits.
Attributes: Docstrings, Function Signatures (No implementation bodies).
Index: A Vector Index on node names and docstrings to enable "fuzzy" entry points (e.g., mapping "login" to AuthUtils).
B. The Agents
The Manager Agent (The Navigator):
Role: Identifies where the work needs to happen.
Capabilities: specific tools to query the Graph (search_nodes, get_neighbors).
Constraint: Does not read raw code bodies, only structure and docstrings.
Output: A precise list of relevant file paths and context cues.
The Worker Agent (The Executor):
Role: Performs the actual coding task.
Input: The specific file snippets provided by the Manager.
Feedback Loop: Can reject tasks (ERROR: MISSING_CONTEXT) if the provided files are insufficient, triggering a retry by the Manager.

3. Research Hypothesis
By centralizing context exploration into a shared Graph-Manager:
Efficiency: We can reduce total token consumption by >50% compared to standard RAG/Agent loops for the same set of tasks.
Scalability: The marginal cost of adding a new agent/task will approach $O(1)$ (constant time/cost) relative to context gathering.
Accuracy: The system will maintain or exceed the Pass@1 rate on benchmarks by reducing "context noise" (irrelevant files).

4. Experiment Design (The MVP)
We will validate this hypothesis using a "Batch Processing" simulation.
Dataset: SWE-bench Lite (A filtered subset of real GitHub issues).
Subject Repo: scikit-learn or flask (Large, mature Python codebases).
Task: Solve 10 distinct issues from the same repository.
Comparison Groups
Feature
Baseline (Standard RAG)
Proposed (Graph-Manager)
Context Source
Vector Database (Embeddings of code chunks)
Static Knowledge Graph (AST + Call Graph)
Workflow
Agent queries DB $\to$ Reads Top-k Chunks $\to$ Codes
Manager queries Graph $\to$ Selects Files $\to$ Worker Codes
Metric: Cost
Sum of tokens for 10 independent runs ($10 \times Cost$)
Build Graph ($1 \times Cost$) + 10 cheap queries
Metric: Precision
% of retrieved chunks that are relevant
% of selected files that match the "Gold" solution


5. Implementation Roadmap
Phase 1: The Graph Builder
Goal: Create the "World Model" that the Manager will read.
Tech Stack: Python, tree-sitter (parsing), networkx (graph storage).
Deliverable: A script that takes a repo path and saves a graph.json containing nodes (Classes/Funcs) and edges (Imports/Calls).
Phase 2: The Manager Agent
Goal: Enable an LLM to "walk" the graph.
Tech Stack: LangChain or simple OpenAI API calls.
Tools:
search_index(query): Returns Node IDs.
inspect_node(node_id): Returns neighbors and docstring.
Deliverable: A script where you ask "Where is the login logic?" and the Agent returns ['/src/auth.py', '/src/user.py'].
Phase 3: The Evaluation Loop
Goal: Connect the Manager to a Worker and run on SWE-bench.
Deliverable: Run 10 issues. Record Token Usage and Success Rate.

6. Addressed Risks
Stale Graphs: If code changes, the graph becomes outdated.
Mitigation: Incremental Parsing. We only re-parse the specific files that are modified by the Worker.
Hallucination: The Manager might invent connections.
Mitigation: Strict Tool Use. The Manager cannot "invent" a file; it can only select from the valid nodes returned by the graph tools.
Complexity: Building a perfect Call Graph is hard in dynamic languages (Python).
Mitigation: Static Approximation. We map clear import and def statements. We accept that some dynamic calls (e.g., getattr) will be missed in the MVP.

