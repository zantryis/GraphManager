"""
Manager Agent: Gemini function-calling agent that navigates the knowledge graph
to identify which files are relevant to a given GitHub issue.
"""

import json
import re

from google import genai
from google.genai import types

from .path_resolution import canonicalize_file_path

SYSTEM_PROMPT = """You are a code navigation expert. You have access to a knowledge graph \
of a Python repository. Your job is to identify which SOURCE FILES need to be modified to \
resolve a given GitHub issue.

You have three tools:
1. search_nodes(query) — fuzzy search for functions/classes by name or description
2. get_neighbors(node_id) — see what a node imports, calls, or is called by
3. get_file_summary(file_path) — list all functions/classes defined in a file

Strategy:
- Start by searching for keywords from the issue
- Inspect promising nodes and their neighbors to understand the dependency chain
- Use get_file_summary to confirm a file is relevant before selecting it
- Be thorough: follow imports and call edges to find related files

When you are confident you have found all relevant files, respond with ONLY a JSON object:
{"files": ["path/to/file1.py", "path/to/file2.py"]}

Do NOT guess files. Only select files you've confirmed through the tools.
Do NOT include test files unless the issue specifically mentions tests."""

TOOL_DECLARATIONS = [
    {
        "name": "search_nodes",
        "description": "Search the codebase knowledge graph for functions and classes matching a query. Returns node IDs, names, types, file paths, docstrings, and relevance scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — can be a function name, concept, or keyword from the issue",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_neighbors",
        "description": "Get all nodes connected to a given node in the knowledge graph. Shows what a function/class imports, calls, is called by, or contains.",
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "The node ID to inspect (e.g., 'src/app.py::Flask' or 'src/helpers.py::url_for')",
                }
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "get_file_summary",
        "description": "List all functions and classes defined in a specific file, with their signatures and docstrings.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative file path in the repository (e.g., 'src/app.py')",
                }
            },
            "required": ["file_path"],
        },
    },
]

MANAGER_RETRIEVAL_MODES = {
    "baseline": {
        "search_top_k": 5,
        "max_neighbors_return": 20,
        "max_definitions_return": 12,
        "max_methods_per_class": 6,
        "max_neighbor_docstring_chars": 60,
        "max_definition_docstring_chars": 80,
        "stagnation_limit": 2,
        "max_tool_calls_per_turn": 4,
        "max_return_files": 20,
        "compact_search_results": False,
        "require_confirmed_files": False,
        "fallback_to_observed_files": True,
        "confirmed_only_if_available": False,
    },
    "progressive": {
        "search_top_k": 5,
        "max_neighbors_return": 10,
        "max_definitions_return": 8,
        "max_methods_per_class": 4,
        "max_neighbor_docstring_chars": 40,
        "max_definition_docstring_chars": 50,
        "stagnation_limit": 2,
        "max_tool_calls_per_turn": 4,
        "max_return_files": 6,
        "compact_search_results": True,
        "require_confirmed_files": True,
        "fallback_to_observed_files": False,
        "confirmed_only_if_available": True,
    },
}


def serialize_manager_telemetry(tokens: dict) -> dict:
    """Build a stable manager telemetry payload from token usage state."""
    src = tokens or {}
    return {
        "tool_calls": int(src.get("tool_calls", 0) or 0),
        "tool_cache_hits": int(src.get("tool_cache_hits", 0) or 0),
        "tool_response_chars": int(src.get("tool_response_chars", 0) or 0),
        "tool_calls_by_name": dict(src.get("tool_calls_by_name", {}) or {}),
        "stop_reason": str(src.get("stop_reason", "") or ""),
    }


class ManagerAgent:
    def __init__(
        self,
        graph,
        graph_index,
        gemini_client,
        model: str = "gemini-2.0-flash",
        retrieval_mode: str = "progressive",
    ):
        self.graph = graph
        self.index = graph_index
        self.client = gemini_client
        self.model = model
        if retrieval_mode not in MANAGER_RETRIEVAL_MODES:
            raise ValueError(
                f"Unknown manager retrieval mode: {retrieval_mode}. "
                f"Valid modes: {sorted(MANAGER_RETRIEVAL_MODES)}"
            )
        self.retrieval_mode = retrieval_mode
        self.cfg = MANAGER_RETRIEVAL_MODES[retrieval_mode]
        self._valid_files = {
            str(node_id)
            for node_id, node_data in self.graph.nodes(data=True)
            if node_data.get("type") == "file" and str(node_id).endswith(".py")
        }
        self._search_cache: dict[str, list[dict]] = {}
        self._neighbors_cache: dict[str, list[dict]] = {}
        self._file_summary_cache: dict[str, dict] = {}

    def find_relevant_files(self, issue_text: str, max_turns: int = 3) -> tuple[list[str], dict]:
        """
        Given an issue description, use the graph tools to find relevant files.
        Returns (list of file paths, token usage dict).
        """
        token_usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": 0,
            "tool_calls": 0,
            "tool_cache_hits": 0,
            "tool_response_chars": 0,
            "tool_calls_by_name": {},
            "stop_reason": "",
        }
        # Cache only within this issue's conversation to avoid cross-issue leakage.
        self._search_cache.clear()
        self._neighbors_cache.clear()
        self._file_summary_cache.clear()
        observed_files: set[str] = set()
        observed_nodes: set[str] = set()
        confirmed_files: set[str] = set()
        file_scores: dict[str, float] = {}
        stagnant_turns = 0
        executed_tool_calls = 0

        tools = types.Tool(function_declarations=TOOL_DECLARATIONS)
        config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=SYSTEM_PROMPT,
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

            # Track tokens
            if response.usage_metadata:
                token_usage["prompt_tokens"] += response.usage_metadata.prompt_token_count or 0
                token_usage["candidate_tokens"] += response.usage_metadata.candidates_token_count or 0
                token_usage["total_tokens"] += response.usage_metadata.total_token_count or 0

            candidate = response.candidates[0]

            # Check for function calls
            function_calls = [
                part.function_call
                for part in candidate.content.parts
                if hasattr(part, "function_call") and part.function_call
            ]

            if not function_calls:
                # Model returned text — try to parse file list
                text = response.text or ""
                files = self._parse_files_from_response(text)
                if files and executed_tool_calls > 0:
                    return self._finalize_file_list(
                        files,
                        confirmed_files,
                        observed_files,
                        file_scores,
                    ), self._finalize_usage(token_usage, stop_reason="sufficient_confidence")
                if self.cfg["require_confirmed_files"] and confirmed_files:
                    return self._finalize_file_list(
                        sorted(confirmed_files),
                        confirmed_files,
                        observed_files,
                        file_scores,
                    ), self._finalize_usage(token_usage, stop_reason="sufficient_confidence")
                if self.cfg["fallback_to_observed_files"] and observed_files:
                    return self._finalize_file_list(
                        sorted(observed_files),
                        confirmed_files,
                        observed_files,
                        file_scores,
                    ), self._finalize_usage(token_usage, stop_reason="sufficient_confidence")
                return [], self._finalize_usage(token_usage, stop_reason="budget")

            # Process function calls
            contents.append(candidate.content)
            response_parts = []
            turn_new_data = False
            seen_turn_calls: set[tuple[str, str]] = set()
            executed_calls = 0

            for fc in function_calls:
                args = dict(fc.args)
                key = (fc.name, json.dumps(args, sort_keys=True))
                usage_delta = {"query_embedding_tokens": 0}
                if key in seen_turn_calls:
                    result = {"skipped_duplicate_call": True, "name": fc.name}
                elif executed_calls >= self.cfg["max_tool_calls_per_turn"]:
                    result = {"tool_call_limit_reached": self.cfg["max_tool_calls_per_turn"]}
                else:
                    result, usage_delta = self._execute_tool(fc.name, args)
                    token_usage["query_embedding_tokens"] += int(usage_delta.get("query_embedding_tokens", 0))
                    seen_turn_calls.add(key)
                    executed_calls += 1
                    executed_tool_calls += 1

                token_usage["tool_calls"] += 1
                token_usage["tool_calls_by_name"][fc.name] = token_usage["tool_calls_by_name"].get(fc.name, 0) + 1
                if isinstance(result, dict) and result.get("cached"):
                    token_usage["tool_cache_hits"] += 1
                token_usage["tool_response_chars"] += len(json.dumps(result, ensure_ascii=True))

                if self._record_observed(result, observed_files, observed_nodes, file_scores):
                    turn_new_data = True
                if self.cfg["require_confirmed_files"] and fc.name == "get_file_summary" and isinstance(result, dict):
                    file_path = result.get("file")
                    if isinstance(file_path, str):
                        canonical = self._canonicalize_candidate_file(file_path)
                        if canonical:
                            confirmed_files.add(canonical)
                            file_scores[canonical] = file_scores.get(canonical, 0.0) + 1.0
                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))

            if turn_new_data:
                stagnant_turns = 0
            else:
                stagnant_turns += 1

            if stagnant_turns >= self.cfg["stagnation_limit"]:
                if self.cfg["require_confirmed_files"] and confirmed_files:
                    return self._finalize_file_list(
                        sorted(confirmed_files),
                        confirmed_files,
                        observed_files,
                        file_scores,
                    ), self._finalize_usage(token_usage, stop_reason="budget")
                if self.cfg["fallback_to_observed_files"] and observed_files:
                    return self._finalize_file_list(
                        sorted(observed_files),
                        confirmed_files,
                        observed_files,
                        file_scores,
                    ), self._finalize_usage(token_usage, stop_reason="budget")

        # If we exhausted turns, try to extract files from the last response
        if self.cfg["require_confirmed_files"] and confirmed_files:
            return self._finalize_file_list(
                sorted(confirmed_files),
                confirmed_files,
                observed_files,
                file_scores,
            ), self._finalize_usage(token_usage, stop_reason="budget")
        if self.cfg["fallback_to_observed_files"] and observed_files:
            return self._finalize_file_list(
                sorted(observed_files),
                confirmed_files,
                observed_files,
                file_scores,
            ), self._finalize_usage(token_usage, stop_reason="budget")
        return [], self._finalize_usage(token_usage, stop_reason="max_turns")

    def _finalize_usage(self, token_usage: dict, stop_reason: str) -> dict:
        finalized = dict(token_usage)
        finalized["stop_reason"] = stop_reason
        finalized["manager_telemetry"] = serialize_manager_telemetry(finalized)
        return finalized

    def _execute_tool(self, name: str, args: dict) -> tuple[object, dict]:
        """Execute a tool call and return (result, usage delta)."""
        if name == "search_nodes":
            query = str(args.get("query", "")).strip()
            cache_key = query.lower()
            if cache_key in self._search_cache:
                return ({
                    "cached": True,
                    "tool": name,
                    "key": cache_key,
                    "message": "Result already returned earlier in this conversation.",
                }, {"query_embedding_tokens": 0})
            search_outcome = self.index.search(query, top_k=self.cfg["search_top_k"]) if query else {
                "results": [],
                "query_embedding_tokens": 0,
            }
            raw_results = search_outcome.get("results", [])
            if self.cfg["compact_search_results"]:
                results = []
                for item in raw_results:
                    results.append({
                        "node_id": item.get("node_id", ""),
                        "name": item.get("name", ""),
                        "type": item.get("type", ""),
                        "file": item.get("file", ""),
                        "score": round(float(item.get("score", 0.0)), 4),
                    })
            else:
                results = raw_results
            self._search_cache[cache_key] = results
            return (
                results,
                {"query_embedding_tokens": int(search_outcome.get("query_embedding_tokens", 0))},
            )
        elif name == "get_neighbors":
            node_id = str(args.get("node_id", "")).strip()
            if node_id in self._neighbors_cache:
                return ({
                    "cached": True,
                    "tool": name,
                    "key": node_id,
                    "message": "Result already returned earlier in this conversation.",
                }, {"query_embedding_tokens": 0})
            result = self._get_neighbors(node_id)
            self._neighbors_cache[node_id] = result
            return result, {"query_embedding_tokens": 0}
        elif name == "get_file_summary":
            file_path = str(args.get("file_path", "")).strip()
            if file_path in self._file_summary_cache:
                return ({
                    "cached": True,
                    "tool": name,
                    "key": file_path,
                    "message": "Result already returned earlier in this conversation.",
                }, {"query_embedding_tokens": 0})
            result = self._get_file_summary(file_path)
            self._file_summary_cache[file_path] = result
            return result, {"query_embedding_tokens": 0}
        else:
            return {"error": f"Unknown tool: {name}"}, {"query_embedding_tokens": 0}

    def _get_neighbors(self, node_id: str) -> list[dict]:
        """Get all nodes connected to a given node."""
        if node_id not in self.graph:
            return [{"error": f"Node '{node_id}' not found in graph"}]

        neighbors = []

        # Outgoing edges
        for _, target, data in self.graph.out_edges(node_id, data=True):
            target_data = self.graph.nodes.get(target, {})
            file_path = str(target_data.get("file", target))
            neighbors.append({
                "node_id": target,
                "direction": "outgoing",
                "edge_type": data.get("type", ""),
                "name": target_data.get("name", ""),
                "type": target_data.get("type", ""),
                "file": file_path,
                "docstring": target_data.get("docstring", "")[:self.cfg["max_neighbor_docstring_chars"]],
                "_rank": (0, file_path, str(target)),
            })
        # Incoming edges
        for source, _, data in self.graph.in_edges(node_id, data=True):
            source_data = self.graph.nodes.get(source, {})
            file_path = str(source_data.get("file", source))
            neighbors.append({
                "node_id": source,
                "direction": "incoming",
                "edge_type": data.get("type", ""),
                "name": source_data.get("name", ""),
                "type": source_data.get("type", ""),
                "file": file_path,
                "docstring": source_data.get("docstring", "")[:self.cfg["max_neighbor_docstring_chars"]],
                "_rank": (1, file_path, str(source)),
            })

        neighbors.sort(key=lambda item: (item["_rank"], item.get("node_id", "")))
        trimmed = []
        seen = set()
        for item in neighbors:
            key = (item.get("node_id"), item.get("direction"), item.get("edge_type"))
            if key in seen:
                continue
            seen.add(key)
            cleaned = dict(item)
            cleaned.pop("_rank", None)
            trimmed.append(cleaned)
            if len(trimmed) >= self.cfg["max_neighbors_return"]:
                break

        return trimmed

    def _get_file_summary(self, file_path: str) -> dict:
        """List all definitions in a file."""
        if file_path not in self.graph:
            # Try to find partial matches
            matches = [n for n in self.graph.nodes if n == file_path or n.endswith("/" + file_path)]
            if matches:
                file_path = matches[0]
            else:
                return {"error": f"File '{file_path}' not found in graph"}

        definitions = []
        for _, target, data in self.graph.out_edges(file_path, data=True):
            if data.get("type") in ("DEFINES",):
                target_data = self.graph.nodes[target]
                entry = {
                    "node_id": target,
                    "type": target_data.get("type", ""),
                    "name": target_data.get("name", ""),
                    "docstring": target_data.get("docstring", "")[:self.cfg["max_definition_docstring_chars"]],
                }
                if target_data.get("type") == "function":
                    entry["signature"] = target_data.get("signature", "")
                # If it's a class, list its methods
                if target_data.get("type") == "class":
                    methods = []
                    for _, method_id, mdata in self.graph.out_edges(target, data=True):
                        if mdata.get("type") == "CONTAINS":
                            method_data = self.graph.nodes[method_id]
                            methods.append({
                                "name": method_data.get("name", ""),
                                "signature": method_data.get("signature", ""),
                            })
                    entry["methods"] = methods[:self.cfg["max_methods_per_class"]]
                definitions.append(entry)

        definitions.sort(key=lambda item: item.get("name", ""))
        return {"file": file_path, "definitions": definitions[:self.cfg["max_definitions_return"]]}

    def _record_observed(
        self,
        result,
        observed_files: set[str],
        observed_nodes: set[str],
        file_scores: dict[str, float],
    ) -> bool:
        """Track files and nodes surfaced by tool outputs; returns True if any new item is found."""
        changed = False

        def visit(value):
            nonlocal changed
            if isinstance(value, dict):
                node_id = value.get("node_id")
                if isinstance(node_id, str) and node_id and node_id not in observed_nodes:
                    observed_nodes.add(node_id)
                    changed = True
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

    def _parse_files_from_response(self, text: str) -> list[str]:
        """Extract file paths from the model's final response."""
        # Try to parse JSON
        try:
            # Find JSON object in the text
            match = re.search(r'\{[^{}]*"files"\s*:\s*\[.*?\][^{}]*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return data.get("files", [])
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: extract file paths with .py extension
        paths = re.findall(r'[\w/.-]+\.py', text)
        return list(dict.fromkeys(paths))  # deduplicate preserving order

    def _finalize_file_list(
        self,
        files: list[str],
        confirmed_files: set[str],
        observed_files: set[str],
        file_scores: dict[str, float] | None = None,
    ) -> list[str]:
        """Deduplicate, enforce grounding, prioritize confirmed files, and cap output size."""
        scores = file_scores or {}
        cleaned = []
        seen = set()
        for file_path in files:
            if not isinstance(file_path, str):
                continue
            canonical = self._canonicalize_candidate_file(file_path)
            if not canonical:
                continue
            if canonical not in observed_files and canonical not in confirmed_files:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            cleaned.append(canonical)

        if self.cfg.get("confirmed_only_if_available") and confirmed_files:
            cleaned = [f for f in cleaned if f in confirmed_files]
            if not cleaned:
                cleaned = sorted(confirmed_files)

        prioritized = sorted(
            cleaned,
            key=lambda f: (
                0 if f in confirmed_files else 1,
                -float(scores.get(f, 0.0)),
                f,
            ),
        )
        return prioritized[:self.cfg["max_return_files"]]

    def _canonicalize_candidate_file(self, file_path: str) -> str | None:
        """Resolve a model/tool file path to a canonical in-repo python file path."""
        if not isinstance(file_path, str):
            return None
        return canonicalize_file_path(file_path, self._valid_files)
