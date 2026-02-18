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


def extract_patch(response_text: str) -> str | None:
    """Extract the unified diff from the model response.

    Returns None if no patch tag found or patch is a CANNOT_PATCH signal.
    """
    match = _PATCH_TAG_RE.search(response_text)
    if not match:
        return None
    content = match.group(1).strip()
    if not content or _CANNOT_PATCH_RE.search(content):
        return None
    return content


def build_patch_prompt(
    issue_text: str,
    file_contents: dict[str, str],
) -> str:
    """Build the user-turn prompt for patch generation."""
    parts = [f"## Issue\n\n{issue_text}\n"]
    for path, content in file_contents.items():
        parts.append(f"## File: {path}\n\n```python\n{content}\n```\n")
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
        model: str = "gemini-2.0-flash",
        max_file_chars: int = 8000,
    ):
        self.repo_dir = Path(repo_dir)
        self.client = client
        self.model = model
        self.max_file_chars = max_file_chars

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
        if not file_contents:
            return None, {
                "prompt_tokens": 0,
                "candidate_tokens": 0,
                "total_tokens": 0,
                "tool_calls": 0,
                "stop_reason": "no_readable_files",
            }

        prompt = build_patch_prompt(issue_text, file_contents)
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
                        max_output_tokens=4096,
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

            response_text = ""
            if response.candidates and response.candidates[0].content.parts:
                response_text = response.candidates[0].content.parts[0].text or ""

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
            "error": "no_valid_patch_after_max_turns",
        }
