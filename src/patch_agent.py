"""
Patch Agent: Generate a unified diff patch from retrieved files and an issue.

Single-agent, no MAS. Consumes retrieved file list from the retrieval stage
and produces a git-format unified diff that can be fed directly to the
SWE-bench evaluation harness.

Usage:
    agent = PatchAgent(repo_dir, client)
    patch, tokens = agent.generate_patch(issue_text, retrieved_files)
"""

import re
from pathlib import Path

from google import genai
from google.genai import types

PATCH_SYSTEM_PROMPT = """You are a software engineering expert fixing GitHub issues.

You will receive:
1. A GitHub issue description
2. The contents of the relevant source files

Your task: produce a minimal, correct unified diff (git diff format) that resolves the issue.

Rules:
- Output ONLY the patch, wrapped in <patch> and </patch> tags
- Use standard unified diff format: --- a/path and +++ b/path headers
- Include 3 lines of context before and after each change
- Make the smallest change that fixes the issue
- Do not include test file changes unless the issue specifically requires it
- Do not add docstrings, comments, or refactors beyond what the fix requires
- If you cannot determine the correct fix with confidence, output: <patch>CANNOT_PATCH</patch>

Patch format example:
<patch>
--- a/src/module.py
+++ b/src/module.py
@@ -42,7 +42,7 @@
 def existing_function():
     context_line_1
     context_line_2
-    old_line_that_is_wrong
+    new_line_that_is_correct
     context_line_3
</patch>"""

_PATCH_TAG_RE = re.compile(r"<patch>(.*?)</patch>", re.DOTALL)
_CANNOT_PATCH_RE = re.compile(r"CANNOT_PATCH", re.IGNORECASE)
_HUNK_HEADER_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@", re.MULTILINE)


def _extract_raw_unified_diff(response_text: str) -> str | None:
    """
    Best-effort fallback when model emits raw diff without <patch> tags.

    Accepts markdown-fenced or plain-text unified diffs.
    """
    text = (response_text or "").strip()
    if not text:
        return None

    # Drop opening code fence language header (e.g., ```diff).
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :].lstrip()

    start = text.find("--- a/")
    if start == -1:
        return None
    candidate = text[start:]

    # Trim trailing markdown fence if present.
    fence_idx = candidate.find("\n```")
    if fence_idx != -1:
        candidate = candidate[:fence_idx]

    candidate = candidate.strip()
    if "+++ b/" not in candidate:
        return None
    if not _HUNK_HEADER_RE.search(candidate):
        return None
    if _CANNOT_PATCH_RE.search(candidate):
        return None
    return candidate if candidate.endswith("\n") else candidate + "\n"


def extract_patch(response_text: str) -> str | None:
    """Extract the unified diff from the model response.

    Returns None if no patch tag found or patch is a CANNOT_PATCH signal.
    """
    match = _PATCH_TAG_RE.search(response_text)
    if match:
        content = match.group(1).strip()
        if not content or _CANNOT_PATCH_RE.search(content):
            return None
        return content if content.endswith("\n") else content + "\n"

    # Fallback for model outputs that provide a raw unified diff without tags.
    return _extract_raw_unified_diff(response_text)


def contains_cannot_patch_signal(response_text: str) -> bool:
    """Return True when the model explicitly signals CANNOT_PATCH."""
    return bool(_CANNOT_PATCH_RE.search(response_text or ""))



def build_patch_prompt(
    issue_text: str,
    file_contents: dict[str, str],
    correction_context: str | None = None,
) -> str:
    """Build the user-turn prompt for patch generation."""
    parts = [f"## Issue\n\n{issue_text}\n"]
    if file_contents:
        for path, content in file_contents.items():
            parts.append(f"## File: {path}\n\n```python\n{content}\n```\n")
    else:
        parts.append(
            "## Retrieved Context\n\n"
            "No repository files were provided. If insufficient context, return "
            "<patch>CANNOT_PATCH</patch>.\n"
        )
    if correction_context:
        parts.append(f"## Correction Context\n\n{correction_context}\n")
    return "\n".join(parts)


class PatchAgent:
    """Generate unified diff patches from retrieved files and an issue description.

    Single-turn by default; supports up to ``max_turns`` correction turns if the
    first response lacks a valid patch tag.
    """

    def __init__(
        self,
        repo_dir: str,
        client: genai.Client,
        model: str = "gemini-3-flash-preview",
        max_file_chars: int = 200_000,
        max_output_tokens: int = 65536,
    ):
        self.repo_dir = Path(repo_dir)
        self.client = client
        self.model = model
        self.max_file_chars = max_file_chars
        self.max_output_tokens = max_output_tokens

    def _read_file(self, rel_path: str) -> str | None:
        """Read a repo file, truncate if over max_file_chars."""
        path = self.repo_dir / rel_path
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if len(text) > self.max_file_chars:
            text = text[: self.max_file_chars] + "\n# ... (truncated)"
        return text

    def _build_file_contents(self, retrieved_files: list[str]) -> dict[str, str]:
        """Read each retrieved file; skip files that cannot be read."""
        contents = {}
        for rel_path in retrieved_files:
            text = self._read_file(rel_path)
            if text is not None:
                contents[rel_path] = text
        return contents

    def generate_patch(
        self,
        issue_text: str,
        retrieved_files: list[str],
        *,
        max_turns: int = 3,
        correction_context: str | None = None,
    ) -> tuple[str | None, dict]:
        """Generate a unified diff patch for the given issue.

        Args:
            issue_text: Prepared issue text (from prepare_issue_text).
            retrieved_files: Normalized file paths from the retrieval stage.
            max_turns: Maximum correction turns if patch extraction fails.

        Returns:
            (patch, token_usage): patch is a unified diff string or None;
            token_usage is a dict with prompt_tokens, candidate_tokens,
            total_tokens, tool_calls=0, stop_reason.
        """
        file_contents = self._build_file_contents(retrieved_files)

        prompt = build_patch_prompt(issue_text, file_contents, correction_context=correction_context)
        total_prompt = 0
        total_candidate = 0
        stop_reason = "unknown"

        for turn in range(max_turns):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=PATCH_SYSTEM_PROMPT,
                        temperature=0.0,
                        max_output_tokens=self.max_output_tokens,
                    ),
                )
            except Exception as e:
                return None, {
                    "prompt_tokens": total_prompt,
                    "candidate_tokens": total_candidate,
                    "total_tokens": total_prompt + total_candidate,
                    "tool_calls": 0,
                    "stop_reason": f"api_error:{type(e).__name__}",
                    "error": str(e),
                }

            usage = response.usage_metadata or {}
            total_prompt += int(getattr(usage, "prompt_token_count", 0) or 0)
            total_candidate += int(getattr(usage, "candidates_token_count", 0) or 0)
            stop_reason = str(
                getattr(response.candidates[0], "finish_reason", "unknown")
                if response.candidates else "no_candidates"
            )

            response_text_obj = getattr(response, "text", "")
            response_text = response_text_obj if isinstance(response_text_obj, str) else ""
            if (not response_text) and response.candidates and response.candidates[0].content.parts:
                part_text = response.candidates[0].content.parts[0].text
                response_text = part_text if isinstance(part_text, str) else ""

            if contains_cannot_patch_signal(response_text):
                return None, {
                    "prompt_tokens": total_prompt,
                    "candidate_tokens": total_candidate,
                    "total_tokens": total_prompt + total_candidate,
                    "tool_calls": 0,
                    "stop_reason": "cannot_patch",
                    "turns_used": turn + 1,
                    "files_provided": len(file_contents),
                    "cannot_patch": True,
                }

            patch = extract_patch(response_text)
            if patch is not None:
                return patch, {
                    "prompt_tokens": total_prompt,
                    "candidate_tokens": total_candidate,
                    "total_tokens": total_prompt + total_candidate,
                    "tool_calls": 0,
                    "stop_reason": stop_reason,
                    "turns_used": turn + 1,
                    "files_provided": len(file_contents),
                    "cannot_patch": False,
                }

            # No valid patch yet — ask for a correction on the next turn
            if turn < max_turns - 1:
                prompt = (
                    prompt
                    + f"\n\n[Your previous response did not contain a valid <patch>...</patch> block. "
                    f"Please output ONLY the patch wrapped in <patch> and </patch> tags.]"
                )

        return None, {
            "prompt_tokens": total_prompt,
            "candidate_tokens": total_candidate,
            "total_tokens": total_prompt + total_candidate,
            "tool_calls": 0,
            "stop_reason": stop_reason,
            "turns_used": max_turns,
            "files_provided": len(file_contents),
            "cannot_patch": False,
            "error": "no_valid_patch_after_max_turns",
        }
