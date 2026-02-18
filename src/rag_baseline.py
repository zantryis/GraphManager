"""
RAG Baseline: Standard vector-search retrieval over code chunks.

Two chunking strategies:
  - "function": tree-sitter-based, one chunk per function/class body
  - "fixed": sliding window of ~512 tokens with overlap

Two retrieval modes:
  - RawRAG: embed query → top-k chunks → map to files (no LLM)
  - RAGAgent: Gemini with a search_codebase tool (comparable to ManagerAgent)
"""

import json
import re
from pathlib import Path

import faiss
import numpy as np
import tree_sitter_python as tspython
from google import genai
from google.genai import types
from tree_sitter import Language, Parser

from .path_resolution import canonicalize_file_path

PY_LANGUAGE = Language(tspython.language())

RAG_AGENT_SYSTEM_PROMPT = """You are a code navigation expert. You have access to a vector \
search tool over a Python repository's codebase. Your job is to identify which SOURCE FILES \
need to be modified to resolve a given GitHub issue.

You have one tool:
1. search_codebase(query) — semantic search over code chunks, returns matching code snippets with file paths

Strategy:
- Search for keywords and concepts from the issue
- Try multiple search queries to cover different aspects of the issue
- Look at which files appear most frequently in results
- Consider the file paths and function names to understand the codebase structure

When you are confident you have found all relevant files, respond with ONLY a JSON object:
{"files": ["path/to/file1.py", "path/to/file2.py"]}

Do NOT guess files. Only select files whose code you've seen in search results.
Do NOT include test files unless the issue specifically mentions tests."""

RAG_TOOL_DECLARATION = {
    "name": "search_codebase",
    "description": "Semantic search over the codebase. Returns code chunks with file paths, function names, and code snippets ranked by relevance.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — keywords, function names, or concepts from the issue",
            }
        },
        "required": ["query"],
    },
}

RAG_RETRIEVAL_MODES = {
    "baseline": {
        "search_top_k": 20,
        "max_tool_calls_per_turn": 10,
        "max_snippet_chars": 300,
        "max_return_files": 20,
        "stagnation_limit": None,
        "compact_results": False,
        "fallback_to_observed_files": False,
    },
    "progressive": {
        "search_top_k": 5,
        "max_tool_calls_per_turn": 4,
        "max_snippet_chars": 120,
        "max_return_files": 6,
        "stagnation_limit": 2,
        "compact_results": True,
        "fallback_to_observed_files": True,
    },
}


class RAGIndex:
    """Vector index over code chunks from a repository."""

    def __init__(
        self,
        repo_path: str,
        gemini_client,
        chunk_strategy: str = "function",
        include_prefixes: tuple[str, ...] | None = None,
    ):
        self.repo_path = Path(repo_path)
        self.client = gemini_client
        self.chunk_strategy = chunk_strategy
        self.parser = Parser(PY_LANGUAGE)
        self.chunks: list[dict] = []  # [{file, name, text, start_line, end_line}, ...]
        self.index = None
        self.embedding_tokens_estimate = 0
        self.include_prefixes = tuple(
            prefix.rstrip("/") for prefix in (include_prefixes or ())
        )

    def build(self):
        """Chunk the codebase and build a FAISS index."""
        # Collect chunks
        py_files = sorted(self.repo_path.rglob("*.py"))
        for py_file in py_files:
            rel_path = str(py_file.relative_to(self.repo_path))
            if any(part.startswith(".") for part in py_file.parts):
                continue
            if not self._is_included(rel_path):
                continue
            try:
                source = py_file.read_text(errors="replace")
                if self.chunk_strategy == "function":
                    self._chunk_by_function(rel_path, source)
                else:
                    self._chunk_fixed_size(rel_path, source)
            except Exception as e:
                print(f"  Warning: failed to chunk {rel_path}: {e}")

        # Filter out empty chunks
        self.chunks = [c for c in self.chunks if c["text"].strip()]

        if not self.chunks:
            print("  Warning: no chunks to index")
            return

        # Embed all chunks
        texts = [c["text"][:500] for c in self.chunks]  # truncate long chunks for embedding
        self.embedding_tokens_estimate = sum(len(t) for t in texts) // 4

        all_embeddings = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self.client.models.embed_content(
                model="gemini-embedding-001",
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=768,
                ),
            )
            for emb in result.embeddings:
                all_embeddings.append(emb.values)

        embeddings = np.array(all_embeddings, dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embeddings = embeddings / norms

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)
        print(f"  RAG index ({self.chunk_strategy}): {len(self.chunks)} chunks, ~{self.embedding_tokens_estimate} embedding tokens")

    def _is_included(self, rel_path: str) -> bool:
        """Check whether a file should be indexed based on include prefixes."""
        if not self.include_prefixes:
            return True
        return any(
            rel_path == prefix or rel_path.startswith(prefix + "/")
            for prefix in self.include_prefixes
        )

    def search(self, query: str, top_k: int = 20) -> dict:
        """Search for chunks matching a query."""
        if self.index is None:
            return {"results": [], "query_embedding_tokens": 0}

        query_embedding_tokens = max(len(query.strip()) // 4, 0) if query else 0
        result = self.client.models.embed_content(
            model="gemini-embedding-001",
            contents=[query],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        query_emb = np.array([result.embeddings[0].values], dtype=np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)

        k = min(top_k, len(self.chunks))
        scores, indices = self.index.search(query_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk = self.chunks[idx]
            results.append({
                "file": chunk["file"],
                "name": chunk.get("name", ""),
                "text": chunk["text"][:300],  # truncate for context window
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
                "score": float(score),
            })
        return {
            "results": results,
            "query_embedding_tokens": query_embedding_tokens,
        }

    def _chunk_by_function(self, rel_path: str, source: str):
        """Split a file into chunks at function/class boundaries using tree-sitter."""
        tree = self.parser.parse(source.encode("utf-8"))
        root = tree.root_node

        found_definitions = False
        for child in root.children:
            if child.type in ("function_definition", "class_definition"):
                self._add_definition_chunk(child, source, rel_path)
                found_definitions = True
            elif child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type in ("function_definition", "class_definition"):
                        self._add_definition_chunk(sub, source, rel_path)
                        found_definitions = True

        # If no functions/classes found, chunk the whole file
        if not found_definitions and source.strip():
            self.chunks.append({
                "file": rel_path,
                "name": rel_path,
                "text": source[:2000],
                "start_line": 1,
                "end_line": source.count("\n") + 1,
            })

    def _add_definition_chunk(self, node, source: str, rel_path: str):
        """Add a function or class body as a chunk."""
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "unknown"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        text = source[node.start_byte:node.end_byte]

        self.chunks.append({
            "file": rel_path,
            "name": name,
            "text": text[:2000],  # cap chunk size
            "start_line": start_line,
            "end_line": end_line,
        })

        # For classes, also add individual methods as separate chunks
        if node.type == "class_definition":
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type in ("function_definition", "decorated_definition"):
                        inner = child
                        if child.type == "decorated_definition":
                            for sub in child.children:
                                if sub.type == "function_definition":
                                    inner = sub
                                    break
                        if inner.type == "function_definition":
                            method_name = inner.child_by_field_name("name")
                            mname = method_name.text.decode("utf-8") if method_name else "method"
                            self.chunks.append({
                                "file": rel_path,
                                "name": f"{name}.{mname}",
                                "text": source[inner.start_byte:inner.end_byte][:2000],
                                "start_line": inner.start_point[0] + 1,
                                "end_line": inner.end_point[0] + 1,
                            })

    def _chunk_fixed_size(self, rel_path: str, source: str):
        """Split a file into fixed-size overlapping chunks (~512 tokens ≈ ~2048 chars)."""
        chunk_size = 2048
        overlap = 256
        lines = source.split("\n")
        text = source

        if len(text) <= chunk_size:
            self.chunks.append({
                "file": rel_path,
                "name": rel_path,
                "text": text,
                "start_line": 1,
                "end_line": len(lines),
            })
            return

        pos = 0
        chunk_idx = 0
        while pos < len(text):
            end = min(pos + chunk_size, len(text))
            chunk_text = text[pos:end]
            start_line = text[:pos].count("\n") + 1
            end_line = text[:end].count("\n") + 1
            self.chunks.append({
                "file": rel_path,
                "name": f"{rel_path}#chunk{chunk_idx}",
                "text": chunk_text,
                "start_line": start_line,
                "end_line": end_line,
            })
            chunk_idx += 1
            pos += chunk_size - overlap
            if end >= len(text):
                break


class RawRAG:
    """No-LLM retrieval: embed query → top-k chunks → extract unique file paths."""

    def __init__(self, rag_index: RAGIndex):
        self.index = rag_index

    def find_relevant_files(self, issue_text: str, top_k: int = 20) -> tuple[list[str], dict]:
        """Return files from top-k chunks. Token cost = embedding the query only."""
        search_outcome = self.index.search(issue_text, top_k=top_k)
        results = search_outcome.get("results", [])
        # Extract unique files in order of first appearance (highest relevance first)
        seen = set()
        files = []
        for r in results:
            f = r["file"]
            if f not in seen:
                seen.add(f)
                files.append(f)

        query_tokens = int(search_outcome.get("query_embedding_tokens", 0))
        token_usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": query_tokens,
        }
        return files, token_usage


class RAGAgent:
    """Gemini function-calling agent with a vector search tool over code chunks."""

    def __init__(
        self,
        rag_index: RAGIndex,
        gemini_client,
        model: str = "gemini-2.0-flash",
        retrieval_mode: str = "progressive",
    ):
        self.rag_index = rag_index
        self.client = gemini_client
        self.model = model
        if retrieval_mode not in RAG_RETRIEVAL_MODES:
            raise ValueError(
                f"Unknown RAG retrieval mode: {retrieval_mode}. "
                f"Valid modes: {sorted(RAG_RETRIEVAL_MODES)}"
            )
        self.retrieval_mode = retrieval_mode
        self.cfg = RAG_RETRIEVAL_MODES[retrieval_mode]
        self._valid_files = {str(chunk.get("file", "")) for chunk in self.rag_index.chunks if chunk.get("file")}
        self._search_cache: dict[str, list[dict]] = {}

    def find_relevant_files(self, issue_text: str, max_turns: int = 10) -> tuple[list[str], dict]:
        """Use Gemini with search_codebase tool to find relevant files."""
        token_usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": 0,
            "tool_calls": 0,
            "tool_cache_hits": 0,
            "tool_response_chars": 0,
            "tool_calls_by_name": {},
        }
        self._search_cache.clear()
        observed_files: set[str] = set()
        file_scores: dict[str, float] = {}
        stagnant_turns = 0
        executed_tool_calls = 0

        tools = types.Tool(function_declarations=[RAG_TOOL_DECLARATION])
        config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=RAG_AGENT_SYSTEM_PROMPT,
            temperature=0.0,
        )

        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=f"Find the files that need to be modified to resolve this GitHub issue:\n\n{issue_text}")],
            )
        ]

        for turn in range(max_turns):
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            if response.usage_metadata:
                token_usage["prompt_tokens"] += response.usage_metadata.prompt_token_count or 0
                token_usage["candidate_tokens"] += response.usage_metadata.candidates_token_count or 0
                token_usage["total_tokens"] += response.usage_metadata.total_token_count or 0

            candidate = response.candidates[0]
            function_calls = [
                part.function_call
                for part in candidate.content.parts
                if hasattr(part, "function_call") and part.function_call
            ]

            if not function_calls:
                text = response.text or ""
                files = self._parse_files_from_response(text)
                if files and executed_tool_calls > 0:
                    return self._finalize_file_list(files, observed_files, file_scores), token_usage
                if self.cfg["fallback_to_observed_files"] and observed_files:
                    return self._finalize_file_list(
                        sorted(observed_files),
                        observed_files,
                        file_scores,
                    ), token_usage
                return [], token_usage

            contents.append(candidate.content)
            response_parts = []
            seen_turn_queries: set[str] = set()
            turn_new_data = False
            executed_calls = 0

            for fc in function_calls:
                query = str(fc.args.get("query", "")).strip()
                norm_query = query.lower()
                if norm_query in seen_turn_queries:
                    results = {"skipped_duplicate_call": True, "name": fc.name}
                elif executed_calls >= self.cfg["max_tool_calls_per_turn"]:
                    results = {"tool_call_limit_reached": self.cfg["max_tool_calls_per_turn"]}
                elif norm_query in self._search_cache:
                    results = {
                        "cached": True,
                        "tool": fc.name,
                        "key": norm_query,
                        "message": "Result already returned earlier in this conversation.",
                    }
                    seen_turn_queries.add(norm_query)
                else:
                    search_outcome = self.rag_index.search(query, top_k=self.cfg["search_top_k"])
                    raw_results = search_outcome.get("results", [])
                    token_usage["query_embedding_tokens"] += int(
                        search_outcome.get("query_embedding_tokens", 0)
                    )
                    if self.cfg["compact_results"]:
                        results = []
                        for item in raw_results:
                            results.append({
                                "file": item.get("file", ""),
                                "name": item.get("name", ""),
                                "start_line": item.get("start_line", 0),
                                "end_line": item.get("end_line", 0),
                                "score": round(float(item.get("score", 0.0)), 4),
                            })
                    else:
                        results = raw_results
                    self._search_cache[norm_query] = results
                    seen_turn_queries.add(norm_query)
                    executed_calls += 1
                    executed_tool_calls += 1

                token_usage["tool_calls"] += 1
                token_usage["tool_calls_by_name"][fc.name] = token_usage["tool_calls_by_name"].get(fc.name, 0) + 1
                if isinstance(results, dict) and results.get("cached"):
                    token_usage["tool_cache_hits"] += 1
                token_usage["tool_response_chars"] += len(json.dumps(results, ensure_ascii=True))
                if self._record_observed_files(results, observed_files, file_scores):
                    turn_new_data = True

                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": results},
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
            if turn_new_data:
                stagnant_turns = 0
            else:
                stagnant_turns += 1
            if (
                self.cfg["stagnation_limit"] is not None
                and stagnant_turns >= self.cfg["stagnation_limit"]
                and self.cfg["fallback_to_observed_files"]
                and observed_files
            ):
                return self._finalize_file_list(
                    sorted(observed_files),
                    observed_files,
                    file_scores,
                ), token_usage

        if self.cfg["fallback_to_observed_files"] and observed_files:
            return self._finalize_file_list(
                sorted(observed_files),
                observed_files,
                file_scores,
            ), token_usage
        return [], token_usage

    def _parse_files_from_response(self, text: str) -> list[str]:
        """Extract file paths from the model's final response."""
        try:
            match = re.search(r'\{[^{}]*"files"\s*:\s*\[.*?\][^{}]*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return data.get("files", [])
        except (json.JSONDecodeError, AttributeError):
            pass
        paths = re.findall(r'[\w/.-]+\.py', text)
        return list(dict.fromkeys(paths))

    def _record_observed_files(
        self,
        result,
        observed_files: set[str],
        file_scores: dict[str, float],
    ) -> bool:
        """Track files surfaced by tool outputs; returns True if any new file is found."""
        changed = False

        def visit(value):
            nonlocal changed
            if isinstance(value, dict):
                file_path = value.get("file")
                if isinstance(file_path, str):
                    canonical = self._canonicalize_candidate_file(file_path)
                    if canonical and canonical not in observed_files:
                        observed_files.add(canonical)
                        changed = True
                    if canonical:
                        raw_score = value.get("score")
                        score = float(raw_score) if isinstance(raw_score, (int, float)) else 0.05
                        file_scores[canonical] = file_scores.get(canonical, 0.0) + score
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(result)
        return changed

    def _finalize_file_list(
        self,
        files: list[str],
        observed_files: set[str],
        file_scores: dict[str, float] | None = None,
    ) -> list[str]:
        """Deduplicate, enforce grounding, and cap output size."""
        scores = file_scores or {}
        cleaned = []
        seen = set()
        for file_path in files:
            canonical = self._canonicalize_candidate_file(file_path)
            if not canonical:
                continue
            if canonical not in observed_files:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            cleaned.append(canonical)

        prioritized = sorted(
            cleaned,
            key=lambda f: (-float(scores.get(f, 0.0)), f),
        )
        return prioritized[:self.cfg["max_return_files"]]

    def _canonicalize_candidate_file(self, file_path: str) -> str | None:
        """Resolve a model/tool file path to a canonical in-index python file path."""
        if not isinstance(file_path, str):
            return None
        return canonicalize_file_path(file_path, self._valid_files)
