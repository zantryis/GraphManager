"""Agentless-like hierarchical localization under constrained file candidates."""

from __future__ import annotations

import json
import hashlib
import random
import re
from collections import defaultdict


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", (text or "").lower())
        if token
    }


def _estimate_tokens(text: str) -> int:
    return max(len(text) // 4, 0)


def _safe_response_text(response) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                return part_text
    return ""


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_scores(raw: dict[str, float]) -> dict[str, float]:
    if not raw:
        return {}
    values = list(raw.values())
    lo = min(values)
    hi = max(values)
    if hi - lo <= 1e-12:
        return {key: 1.0 for key in raw}
    return {
        key: (float(value) - lo) / (hi - lo)
        for key, value in raw.items()
    }


class AgentlessLikeLocalizer:
    """Three-stage file localization with constrained candidate outputs."""

    def __init__(
        self,
        *,
        rag_index,
        graph,
        client=None,
        model: str = "gemini-3-flash-preview",
        stage2_enabled: bool = True,
        stage3_enabled: bool = True,
        edit_location_samples: int = 4,
        file_branch_top_n: int = 3,
        embed_branch_top_k: int = 20,
        merge_top_k: int = 12,
        stage3_context_window_lines: int = 10,
        stage3_max_tokens_per_file: int = 1200,
        constrained_candidates_max: int = 200,
        reject_out_of_candidate_paths: bool = True,
    ):
        self.rag_index = rag_index
        self.graph = graph
        self.client = client
        self.model = model

        self.stage2_enabled = bool(stage2_enabled)
        self.stage3_enabled = bool(stage3_enabled)
        self.edit_location_samples = max(int(edit_location_samples), 1)
        self.file_branch_top_n = max(int(file_branch_top_n), 0)
        self.embed_branch_top_k = max(int(embed_branch_top_k), 1)
        self.merge_top_k = max(int(merge_top_k), 1)
        self.stage3_context_window_lines = max(int(stage3_context_window_lines), 0)
        self.stage3_max_tokens_per_file = max(int(stage3_max_tokens_per_file), 1)
        self.constrained_candidates_max = max(int(constrained_candidates_max), 10)
        self.reject_out_of_candidate_paths = bool(reject_out_of_candidate_paths)

        rag_files = {
            str(chunk.get("file", ""))
            for chunk in getattr(self.rag_index, "chunks", [])
            if str(chunk.get("file", "")).endswith(".py")
        }
        graph_files = {
            str(node_id)
            for node_id, node_data in self.graph.nodes(data=True)
            if node_data.get("type") == "file" and str(node_id).endswith(".py")
        }
        self.valid_files = sorted(rag_files | graph_files)

        chunks_by_file: dict[str, list[dict]] = defaultdict(list)
        for chunk in getattr(self.rag_index, "chunks", []) or []:
            file_path = str(chunk.get("file", "") or "")
            if not file_path:
                continue
            chunks_by_file[file_path].append(chunk)
        self.chunks_by_file = chunks_by_file

        symbols_by_file: dict[str, list[dict]] = defaultdict(list)
        for node_id, node_data in self.graph.nodes(data=True):
            node_type = str(node_data.get("type", "") or "")
            if node_type not in {"function", "class"}:
                continue
            file_path = str(node_data.get("file", "") or "")
            if not file_path:
                continue
            symbol_name = str(node_data.get("name", "") or str(node_id).split("::")[-1])
            symbols_by_file[file_path].append(
                {
                    "symbol_id": str(node_id),
                    "symbol_name": symbol_name,
                    "start_line": int(node_data.get("start_line", 1) or 1),
                    "end_line": int(node_data.get("end_line", node_data.get("start_line", 1) or 1) or 1),
                }
            )
        for file_path in list(symbols_by_file):
            symbols_by_file[file_path] = sorted(
                symbols_by_file[file_path],
                key=lambda item: (item["start_line"], item["symbol_name"]),
            )
        self.symbols_by_file = symbols_by_file

    def find_relevant_files(self, issue_text: str, max_turns: int = 6) -> tuple[list[str], dict]:
        _ = max_turns
        usage = self._empty_usage()

        candidate_pool = self._build_candidate_pool(issue_text)
        dense_scores, dense_tokens = self._dense_stage_scores(issue_text)
        usage["query_embedding_tokens"] += dense_tokens

        llm_ranked_files = []
        invalid_stage1 = 0
        stage1_llm_fired = False
        if self.client is not None and self.file_branch_top_n > 0 and candidate_pool:
            stage1_llm_fired = True
            llm_ranked_files, llm_usage, invalid_stage1 = self._llm_rank_files_stage1(
                issue_text=issue_text,
                candidate_pool=candidate_pool,
            )
            self._accumulate_usage(usage, llm_usage)

        merged_files = self._merge_stage1(
            candidate_pool=candidate_pool,
            dense_scores=dense_scores,
            llm_ranked_files=llm_ranked_files,
        )
        stage1_files = merged_files[: self.merge_top_k]

        selected_symbols = self._deterministic_symbol_selection(stage1_files)
        invalid_stage2 = 0
        stage2_llm_fired = False
        if self.stage2_enabled and self.client is not None and stage1_files:
            stage2_llm_fired = True
            selected_symbols, stage2_usage, invalid_stage2 = self._llm_select_symbols_stage2(
                issue_text=issue_text,
                candidate_files=stage1_files,
                fallback_symbols=selected_symbols,
            )
            self._accumulate_usage(usage, stage2_usage)

        selected_spans = self._deterministic_stage3_spans(selected_symbols, issue_text)
        stage3_schema_violations = 0
        stage3_context_tokens_by_file = {}
        stage3_llm_fired = False
        if self.stage3_enabled and self.client is not None and selected_symbols:
            stage3_llm_fired = True
            (
                selected_spans,
                stage3_usage,
                stage3_schema_violations,
                stage3_context_tokens_by_file,
            ) = self._llm_select_spans_stage3(
                issue_text=issue_text,
                selected_symbols=selected_symbols,
                fallback_spans=selected_spans,
            )
            self._accumulate_usage(usage, stage3_usage)

        if selected_spans:
            final_files = []
            for span in selected_spans:
                file_path = span.get("file")
                if file_path and file_path not in final_files:
                    final_files.append(file_path)
        elif selected_symbols:
            final_files = []
            for symbol in selected_symbols:
                file_path = symbol.get("file")
                if file_path and file_path not in final_files:
                    final_files.append(file_path)
        else:
            final_files = list(stage1_files)

        usage["agentless_like_meta"] = {
            "stage1_candidate_pool_size": len(candidate_pool),
            "stage1_dense_result_files": len(dense_scores),
            "stage1_invalid_selection_count": int(invalid_stage1),
            "stage2_selected_symbol_count": len(selected_symbols),
            "stage2_invalid_selection_count": int(invalid_stage2),
            "stage3_span_schema_violation_count": int(stage3_schema_violations),
            "stage3_context_tokens_per_file": {
                str(path): int(tokens)
                for path, tokens in stage3_context_tokens_by_file.items()
            },
            "edit_location_samples": self.edit_location_samples,
            "invalid_path_selection_rate": (
                float(invalid_stage1) / float(max(self.file_branch_top_n, 1))
            ),
            "out_of_candidate_rejection_count": int(invalid_stage1 + invalid_stage2),
            "stage1_llm_fired": bool(stage1_llm_fired),
            "stage2_llm_fired": bool(stage2_llm_fired),
            "stage3_llm_fired": bool(stage3_llm_fired),
        }
        usage["stop_reason"] = "stage3_spans" if selected_spans else "stage1_rank"
        return final_files[: self.merge_top_k], usage

    def _build_candidate_pool(self, issue_text: str) -> list[str]:
        query_tokens = _tokenize(issue_text)
        scored = []
        for file_path in self.valid_files:
            path_tokens = _tokenize(file_path.replace("/", " ").replace(".", " "))
            overlap = len(path_tokens & query_tokens)
            mention = 2 if file_path.lower() in issue_text.lower() else 0
            score = overlap + mention
            scored.append((score, file_path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ranked = [file_path for _, file_path in scored]
        if len(ranked) > self.constrained_candidates_max:
            ranked = ranked[: self.constrained_candidates_max]
        return ranked

    def _dense_stage_scores(self, issue_text: str) -> tuple[dict[str, float], int]:
        outcome = self.rag_index.search(issue_text, top_k=self.embed_branch_top_k)
        query_tokens = int(outcome.get("query_embedding_tokens", 0) or 0)
        file_scores: dict[str, float] = {}
        for row in outcome.get("results", []) or []:
            file_path = str(row.get("file", "") or "")
            score = float(row.get("score", 0.0) or 0.0)
            if not file_path:
                continue
            prev = file_scores.get(file_path)
            if prev is None or score > prev:
                file_scores[file_path] = score
        return file_scores, query_tokens

    def _merge_stage1(
        self,
        *,
        candidate_pool: list[str],
        dense_scores: dict[str, float],
        llm_ranked_files: list[str],
    ) -> list[str]:
        dense_norm = _normalize_scores(dense_scores)
        lex_norm = {
            path: 1.0 - (idx / max(len(candidate_pool), 1))
            for idx, path in enumerate(candidate_pool)
        }
        llm_boost = {
            path: 1.0 - (idx / max(len(llm_ranked_files), 1))
            for idx, path in enumerate(llm_ranked_files)
        }

        merged: dict[str, float] = defaultdict(float)
        all_files = set(candidate_pool) | set(dense_norm) | set(llm_boost)
        for file_path in all_files:
            merged[file_path] += 0.55 * float(dense_norm.get(file_path, 0.0))
            merged[file_path] += 0.30 * float(lex_norm.get(file_path, 0.0))
            merged[file_path] += 0.15 * float(llm_boost.get(file_path, 0.0))
        ranked = sorted(merged.items(), key=lambda item: (-item[1], item[0]))
        return [path for path, _ in ranked]

    def _deterministic_symbol_selection(self, candidate_files: list[str]) -> list[dict]:
        selected = []
        for file_path in candidate_files:
            symbols = self.symbols_by_file.get(file_path, [])
            if not symbols:
                continue
            selected.append(
                {
                    "file": file_path,
                    "symbol_id": symbols[0]["symbol_id"],
                    "symbol_name": symbols[0]["symbol_name"],
                    "start_line": symbols[0]["start_line"],
                    "end_line": symbols[0]["end_line"],
                }
            )
        return selected

    def _llm_rank_files_stage1(
        self,
        *,
        issue_text: str,
        candidate_pool: list[str],
    ) -> tuple[list[str], dict, int]:
        candidate_block = "\n".join(f"- {path}" for path in candidate_pool)
        prompt = (
            "Choose the most relevant files for bug localization.\n"
            "You MUST choose only from the candidate list.\n"
            "Return strict JSON: {\"files\": [\"...\"]}\n\n"
            f"Issue:\n{issue_text}\n\n"
            f"Candidate files:\n{candidate_block}\n"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        usage = self._usage_from_response(response)
        parsed = _extract_json_object(_safe_response_text(response)) or {}
        selected = parsed.get("files") if isinstance(parsed, dict) else []
        if not isinstance(selected, list):
            selected = []
        candidate_set = set(candidate_pool)
        invalid = 0
        chosen = []
        for item in selected:
            path = str(item or "").strip()
            if not path:
                continue
            if path not in candidate_set:
                if self.reject_out_of_candidate_paths:
                    invalid += 1
                    continue
            if path not in chosen:
                chosen.append(path)
        if not chosen:
            chosen = candidate_pool[: self.file_branch_top_n]
        return chosen[: self.file_branch_top_n], usage, invalid

    def _llm_select_symbols_stage2(
        self,
        *,
        issue_text: str,
        candidate_files: list[str],
        fallback_symbols: list[dict],
    ) -> tuple[list[dict], dict, int]:
        symbol_pool = []
        for file_path in candidate_files:
            for symbol in self.symbols_by_file.get(file_path, [])[:6]:
                symbol_pool.append(
                    {
                        "symbol_id": symbol["symbol_id"],
                        "file": file_path,
                        "symbol_name": symbol["symbol_name"],
                        "start_line": symbol["start_line"],
                        "end_line": symbol["end_line"],
                    }
                )
        if not symbol_pool:
            return fallback_symbols, {}, 0

        symbol_block = "\n".join(
            f"- {row['symbol_id']} ({row['file']}:{row['start_line']}-{row['end_line']})"
            for row in symbol_pool
        )
        prompt = (
            "Select relevant symbols for localization.\n"
            "You MUST choose only from the symbol IDs listed.\n"
            "Return strict JSON: {\"symbols\": [\"symbol_id\", ...]}\n\n"
            f"Issue:\n{issue_text}\n\n"
            f"Symbol candidates:\n{symbol_block}\n"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        usage = self._usage_from_response(response)
        parsed = _extract_json_object(_safe_response_text(response)) or {}
        selected = parsed.get("symbols") if isinstance(parsed, dict) else []
        if not isinstance(selected, list):
            selected = []

        symbol_by_id = {row["symbol_id"]: row for row in symbol_pool}
        invalid = 0
        chosen = []
        for item in selected:
            symbol_id = str(item or "").strip()
            if not symbol_id:
                continue
            if symbol_id not in symbol_by_id:
                invalid += 1
                continue
            row = symbol_by_id[symbol_id]
            if row not in chosen:
                chosen.append(row)
        if not chosen:
            chosen = fallback_symbols
        return chosen, usage, invalid

    def _deterministic_stage3_spans(self, symbols: list[dict], issue_text: str) -> list[dict]:
        if not symbols:
            return []
        seed_material = (
            (issue_text or "")
            + "\n"
            + "\n".join(sorted(str(sym.get("symbol_id", "") or "") for sym in symbols))
        )
        digest = hashlib.sha256(seed_material.encode("utf-8", errors="replace")).hexdigest()
        seed = int(digest[:16], 16)
        rng = random.Random(seed)
        pool = list(symbols)
        rng.shuffle(pool)
        spans = []
        for symbol in pool[: self.edit_location_samples]:
            start = max(int(symbol.get("start_line", 1) or 1) - self.stage3_context_window_lines, 1)
            end = int(symbol.get("end_line", start) or start) + self.stage3_context_window_lines
            spans.append(
                {
                    "file": symbol.get("file"),
                    "start_line": int(start),
                    "end_line": int(max(end, start)),
                    "confidence": 0.5,
                    "symbol_id": symbol.get("symbol_id"),
                }
            )
        return spans

    def _llm_select_spans_stage3(
        self,
        *,
        issue_text: str,
        selected_symbols: list[dict],
        fallback_spans: list[dict],
    ) -> tuple[list[dict], dict, int, dict[str, int]]:
        if not selected_symbols:
            return fallback_spans, {}, 0, {}

        span_pool = []
        for symbol in selected_symbols:
            start = max(int(symbol.get("start_line", 1) or 1) - self.stage3_context_window_lines, 1)
            end = int(symbol.get("end_line", start) or start) + self.stage3_context_window_lines
            span_pool.append(
                {
                    "symbol_id": symbol.get("symbol_id"),
                    "file": symbol.get("file"),
                    "start_line": int(start),
                    "end_line": int(max(end, start)),
                }
            )

        pool_block = "\n".join(
            f"- {row['symbol_id']} => {row['file']}:{row['start_line']}-{row['end_line']}"
            for row in span_pool
        )
        context_block, context_tokens_by_file = self._build_stage3_context_block(selected_symbols)
        prompt = (
            "Pick likely edit spans.\n"
            "You MUST choose only symbol IDs from the provided span candidates.\n"
            "Return strict JSON: {\"spans\": [{\"symbol_id\": \"...\", \"confidence\": 0.0}]}\n"
            f"Select up to {self.edit_location_samples} spans.\n\n"
            f"Issue:\n{issue_text}\n\n"
            f"Span candidates:\n{pool_block}\n"
            f"\nSymbol context (token-capped per file):\n{context_block}\n"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        usage = self._usage_from_response(response)
        parsed = _extract_json_object(_safe_response_text(response)) or {}
        rows = parsed.get("spans") if isinstance(parsed, dict) else []
        if not isinstance(rows, list):
            rows = []

        pool_by_id = {row["symbol_id"]: row for row in span_pool}
        selected = []
        schema_violations = 0
        for row in rows:
            if not isinstance(row, dict):
                schema_violations += 1
                continue
            symbol_id = str(row.get("symbol_id", "") or "").strip()
            if symbol_id not in pool_by_id:
                schema_violations += 1
                continue
            confidence = row.get("confidence", 0.5)
            try:
                confidence_value = float(confidence)
            except Exception:
                schema_violations += 1
                continue
            if confidence_value < 0.0 or confidence_value > 1.0:
                schema_violations += 1
                continue
            base = pool_by_id[symbol_id]
            selected.append(
                {
                    "file": base["file"],
                    "start_line": int(base["start_line"]),
                    "end_line": int(base["end_line"]),
                    "confidence": confidence_value,
                    "symbol_id": symbol_id,
                }
            )
            if len(selected) >= self.edit_location_samples:
                break
        if not selected:
            selected = fallback_spans
        return selected, usage, schema_violations, context_tokens_by_file

    def _build_stage3_context_block(self, selected_symbols: list[dict]) -> tuple[str, dict[str, int]]:
        lines = []
        tokens_by_file: dict[str, int] = defaultdict(int)
        for symbol in selected_symbols:
            file_path = str(symbol.get("file", "") or "")
            if not file_path:
                continue
            symbol_id = str(symbol.get("symbol_id", "") or "")
            excerpt = self._symbol_excerpt(symbol)
            if excerpt:
                line = (
                    f"- {symbol_id} ({file_path}:{int(symbol.get('start_line', 1))}-"
                    f"{int(symbol.get('end_line', 1))}) :: {excerpt}"
                )
            else:
                line = (
                    f"- {symbol_id} ({file_path}:{int(symbol.get('start_line', 1))}-"
                    f"{int(symbol.get('end_line', 1))})"
                )
            line_tokens = _estimate_tokens(line) + 1
            if tokens_by_file[file_path] + line_tokens > self.stage3_max_tokens_per_file:
                continue
            tokens_by_file[file_path] += line_tokens
            lines.append(line)

        if not lines:
            return "(no context under token cap)", {str(path): int(tok) for path, tok in tokens_by_file.items()}
        return "\n".join(lines), {str(path): int(tok) for path, tok in tokens_by_file.items()}

    def _symbol_excerpt(self, symbol: dict) -> str:
        file_path = str(symbol.get("file", "") or "")
        if not file_path:
            return ""
        symbol_name = str(symbol.get("symbol_name", "") or "")
        start_line = int(symbol.get("start_line", 1) or 1)
        end_line = int(symbol.get("end_line", start_line) or start_line)
        chunks = self.chunks_by_file.get(file_path, [])
        for chunk in chunks:
            chunk_start = int(chunk.get("start_line", 1) or 1)
            chunk_end = int(chunk.get("end_line", chunk_start) or chunk_start)
            overlaps = not (end_line < chunk_start or start_line > chunk_end)
            if not overlaps:
                continue
            text = str(chunk.get("text", "") or "").strip()
            if not text:
                continue
            text = re.sub(r"\s+", " ", text)
            return text[:400]

        for chunk in chunks:
            chunk_name = str(chunk.get("name", "") or "")
            if symbol_name and chunk_name and symbol_name in chunk_name:
                text = str(chunk.get("text", "") or "").strip()
                if not text:
                    continue
                text = re.sub(r"\s+", " ", text)
                return text[:400]
        return ""

    def _empty_usage(self) -> dict:
        return {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": 0,
            "tool_calls": 0,
            "stop_reason": "",
        }

    def _usage_from_response(self, response) -> dict:
        usage = self._empty_usage()
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage["prompt_tokens"] = int(getattr(meta, "prompt_token_count", 0) or 0)
            usage["candidate_tokens"] = int(getattr(meta, "candidates_token_count", 0) or 0)
            usage["total_tokens"] = int(getattr(meta, "total_token_count", 0) or 0)
        usage["tool_calls"] = 1
        return usage

    def _accumulate_usage(self, target: dict, delta: dict) -> None:
        for key in ("prompt_tokens", "candidate_tokens", "total_tokens", "query_embedding_tokens", "tool_calls"):
            target[key] = int(target.get(key, 0) or 0) + int(delta.get(key, 0) or 0)
