"""
Agentic cold-start retrieval: tool-using file discovery with no retrieval index.

This baseline intentionally avoids graph/rag indices and instead gives the model
filesystem tools to explore repository files directly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from google.genai import types

from .path_resolution import canonicalize_file_path

SYSTEM_PROMPT = """You are a code navigation expert. You have no prebuilt retrieval index.
Use tools to explore repository files and identify which SOURCE FILES should be modified
to resolve the issue.

Tools:
1. list_files(prefix, limit): list Python files in the repo.
2. search_paths(query, top_k): lexical search over Python file paths.
3. get_file_contents(path): read a file's source contents.

Guidelines:
- Start with search_paths, then inspect promising files.
- Prefer source files over tests unless the issue explicitly requires test changes.
- Return only files you inspected or discovered via tools.

When done, respond with ONLY:
{"files": ["path/to/file1.py", "path/to/file2.py"]}"""

TOOL_DECLARATIONS = [
    {
        "name": "list_files",
        "description": "List python source files in the repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "prefix": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "search_paths",
        "description": "Lexically search repository python file paths by query terms.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_file_contents",
        "description": "Read the full source of a repository file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
]


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", (text or "").lower()) if tok}


class AgenticColdStartAgent:
    def __init__(
        self,
        *,
        repo_dir: str,
        client,
        model: str = "gemini-3-flash-preview",
        include_prefixes: tuple[str, ...] | None = None,
        max_file_chars: int = 200_000,
        max_return_files: int = 6,
    ):
        self.repo_dir = Path(repo_dir)
        self.client = client
        self.model = model
        self.max_file_chars = max_file_chars
        self.max_return_files = max(max_return_files, 1)
        self.include_prefixes = tuple(
            str(prefix).rstrip("/") for prefix in (include_prefixes or ())
        )
        self._valid_files = self._collect_python_files()
        self._path_tokens = {path: _tokenize(path) for path in self._valid_files}
        self._list_cache: dict[tuple[str, int], list[str]] = {}
        self._search_cache: dict[tuple[str, int], list[dict]] = {}

    def _is_included(self, rel_path: str) -> bool:
        if not self.include_prefixes:
            return True
        return any(
            rel_path == prefix or rel_path.startswith(prefix + "/")
            for prefix in self.include_prefixes
        )

    def _collect_python_files(self) -> set[str]:
        files = set()
        for py_file in sorted(self.repo_dir.rglob("*.py")):
            if any(part.startswith(".") for part in py_file.parts):
                continue
            rel = py_file.relative_to(self.repo_dir).as_posix()
            if not self._is_included(rel):
                continue
            files.add(rel)
        return files

    def _list_files(self, prefix: str = "", limit: int = 200) -> list[str]:
        key = (prefix, max(limit, 1))
        if key in self._list_cache:
            return self._list_cache[key]
        normalized_prefix = prefix.strip().lstrip("./")
        out = sorted(
            path for path in self._valid_files
            if not normalized_prefix or path.startswith(normalized_prefix)
        )[: max(limit, 1)]
        self._list_cache[key] = out
        return out

    def _search_paths(self, query: str, top_k: int = 20) -> list[dict]:
        key = (query.strip().lower(), max(top_k, 1))
        if key in self._search_cache:
            return self._search_cache[key]
        q_tokens = _tokenize(query)
        if not q_tokens:
            self._search_cache[key] = []
            return []

        scored: list[tuple[float, str]] = []
        query_l = query.lower()
        for path, p_tokens in self._path_tokens.items():
            overlap = len(q_tokens & p_tokens)
            substring_bonus = 1.0 if query_l and query_l in path.lower() else 0.0
            score = float(overlap) + substring_bonus
            if score > 0:
                scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        results = [
            {"file": path, "score": score}
            for score, path in scored[: max(top_k, 1)]
        ]
        self._search_cache[key] = results
        return results

    def _handle_get_file_contents(self, path: str, observed_files: set[str]) -> str:
        raw_path = str(path or "").strip()
        if not raw_path:
            return "Error: empty path"
        try:
            full_path = (self.repo_dir / raw_path).resolve()
            repo_root = self.repo_dir.resolve()
            full_path.relative_to(repo_root)
        except ValueError:
            return f"Error: path is outside the repository: {raw_path}"

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return f"Error: file not found or not readable: {raw_path}"

        if len(content) > self.max_file_chars:
            content = content[: self.max_file_chars] + "\n... [truncated]"

        canonical = canonicalize_file_path(raw_path, self._valid_files)
        if canonical:
            observed_files.add(canonical)
        else:
            try:
                rel = full_path.relative_to(self.repo_dir.resolve()).as_posix()
                if rel in self._valid_files:
                    observed_files.add(rel)
            except ValueError:
                pass
        return content

    def _parse_files_from_response(self, text: str) -> list[str]:
        try:
            match = re.search(r'\{[^{}]*"files"\s*:\s*\[.*?\][^{}]*\}', text or "", re.DOTALL)
            if match:
                data = json.loads(match.group())
                if isinstance(data.get("files"), list):
                    return data["files"]
        except Exception:
            pass
        return list(dict.fromkeys(re.findall(r"[\w/.-]+\.py", text or "")))

    def _finalize(self, files: list[str], observed_files: set[str], file_scores: dict[str, float]) -> list[str]:
        deduped = []
        seen = set()
        for file_path in files:
            canonical = canonicalize_file_path(file_path, self._valid_files)
            if not canonical or canonical in seen:
                continue
            if canonical not in observed_files:
                continue
            seen.add(canonical)
            deduped.append(canonical)

        deduped.sort(key=lambda path: (-float(file_scores.get(path, 0.0)), path))
        return deduped[: self.max_return_files]

    def _record_observed(self, result, observed_files: set[str], file_scores: dict[str, float]) -> bool:
        changed = False

        def visit(value):
            nonlocal changed
            if isinstance(value, dict):
                file_path = value.get("file")
                if isinstance(file_path, str):
                    canonical = canonicalize_file_path(file_path, self._valid_files)
                    if canonical and canonical not in observed_files:
                        observed_files.add(canonical)
                        changed = True
                    if canonical:
                        score = value.get("score")
                        file_scores[canonical] = file_scores.get(canonical, 0.0) + (
                            float(score) if isinstance(score, (int, float)) else 0.05
                        )
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(result)
        return changed

    def find_relevant_files(self, issue_text: str, max_turns: int = 6) -> tuple[list[str], dict]:
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
        observed_files: set[str] = set()
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
                parts=[types.Part(text=f"Find relevant files for this issue:\n\n{issue_text}")],
            )
        ]

        for _ in range(max(max_turns, 1)):
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
                if getattr(part, "function_call", None)
            ]
            if not function_calls:
                files = self._parse_files_from_response(response.text or "")
                if files and executed_tool_calls > 0:
                    token_usage["stop_reason"] = "sufficient_confidence"
                    return self._finalize(files, observed_files, file_scores), token_usage
                if observed_files:
                    token_usage["stop_reason"] = "budget"
                    return self._finalize(sorted(observed_files), observed_files, file_scores), token_usage
                token_usage["stop_reason"] = "budget"
                return [], token_usage

            contents.append(candidate.content)
            response_parts = []
            turn_new_data = False

            for fc in function_calls:
                name = str(fc.name)
                args = dict(fc.args)
                if name == "list_files":
                    prefix = str(args.get("prefix", "") or "")
                    limit = int(args.get("limit", 200) or 200)
                    result = self._list_files(prefix=prefix, limit=limit)
                elif name == "search_paths":
                    query = str(args.get("query", "") or "")
                    top_k = int(args.get("top_k", 20) or 20)
                    result = self._search_paths(query=query, top_k=top_k)
                elif name == "get_file_contents":
                    path = str(args.get("path", "") or "")
                    result = self._handle_get_file_contents(path, observed_files)
                else:
                    result = {"error": f"Unknown tool: {name}"}

                token_usage["tool_calls"] += 1
                token_usage["tool_calls_by_name"][name] = token_usage["tool_calls_by_name"].get(name, 0) + 1
                token_usage["tool_response_chars"] += len(json.dumps(result, ensure_ascii=True))
                executed_tool_calls += 1

                if self._record_observed(result, observed_files, file_scores):
                    turn_new_data = True

                response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result},
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
            stagnant_turns = 0 if turn_new_data else (stagnant_turns + 1)
            if stagnant_turns >= 2 and observed_files:
                token_usage["stop_reason"] = "budget"
                return self._finalize(sorted(observed_files), observed_files, file_scores), token_usage

        token_usage["stop_reason"] = "max_turns"
        if observed_files:
            return self._finalize(sorted(observed_files), observed_files, file_scores), token_usage
        return [], token_usage
