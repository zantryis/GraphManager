"""
BM25 Retrieval Baseline: Zero-LLM-cost lexical retrieval over Python files.

Uses file-level BM25 scoring (one document per .py file). Tokenizes with
a regex tokenizer that extracts alphanumeric tokens (handles "main():" →
["main"], "alpha_function" → ["alpha", "function"]).  No embedding cost.

Uses BM25Plus (rank_bm25) which guarantees non-negative IDF and is more
robust than BM25Okapi for small corpora where common terms would otherwise
receive negative IDF scores.

Interface mirrors RawRAG / gm_deterministic so it plugs into the same
evaluation pipeline.

Granularity choice: **file-level** (one document per file).
Rationale: simpler, adequate for Tier-0 baseline, matches retrieval F1
evaluation unit (files, not lines).
"""

from __future__ import annotations

import re
from pathlib import Path

from rank_bm25 import BM25Plus


def _tokenize(text: str) -> list[str]:
    """Regex alphanumeric tokenizer (lowercase).

    Splits on any non-alphanumeric character, so identifiers like
    'alpha_function():' become ['alpha', 'function'] and string literals
    like "'hello'" become ['hello'].
    """
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Index:
    """File-level BM25 index over a Python repository.

    Build once per commit, query many times per issue — same amortization
    pattern as GraphIndex and RAGIndex.
    """

    def __init__(
        self,
        repo_dir: str,
        include_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.repo_dir = Path(repo_dir)
        self.include_prefixes = include_prefixes
        self._file_paths: list[str] = []   # relative paths indexed (parallel to _bm25)
        self._bm25: BM25Plus | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Index all .py files in repo_dir (filtered by include_prefixes if set)."""
        corpus: list[list[str]] = []
        file_paths: list[str] = []

        for py_file in sorted(self.repo_dir.rglob("*.py")):
            rel = py_file.relative_to(self.repo_dir).as_posix()

            if self.include_prefixes:
                if not any(rel.startswith(prefix) for prefix in self.include_prefixes):
                    continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            tokens = _tokenize(content)
            # Include even empty files so index has a document for each file.
            # BM25Okapi handles empty token lists gracefully.
            corpus.append(tokens)
            file_paths.append(rel)

        self._file_paths = file_paths
        if corpus:
            self._bm25 = BM25Plus(corpus)
        else:
            self._bm25 = None

    def query(self, query_text: str, top_k: int = 10) -> list[str]:
        """Return top-k file paths ranked by BM25 score against query_text.

        Files are deduplicated (index is file-level, so no duplicates by
        construction). Returns an empty list if the index is empty or
        all scores are zero.
        """
        if self._bm25 is None or not self._file_paths:
            return []

        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Pair scores with file paths and sort descending
        scored = sorted(
            zip(scores, self._file_paths),
            key=lambda x: x[0],
            reverse=True,
        )

        # Return top_k results; exclude files with score == 0 if all tokens are absent
        results = [path for score, path in scored if score > 0.0]
        return results[:top_k]

    def find_relevant_files(
        self, issue_text: str, top_k: int = 10
    ) -> tuple[list[str], dict]:
        """Return (files, token_usage) — matches RawRAG / DeterministicGraphRetriever interface.

        BM25 has zero LLM and zero embedding cost.
        """
        files = self.query(issue_text, top_k=top_k)
        token_usage = {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
            "query_embedding_tokens": 0,
        }
        return files, token_usage

    @property
    def embedding_tokens_estimate(self) -> int:
        """BM25 has no embedding cost — always 0."""
        return 0
