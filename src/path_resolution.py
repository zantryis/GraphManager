"""
Helpers for normalizing and canonicalizing repository-relative file paths.
"""

from __future__ import annotations

from typing import Iterable


def normalize_file_path(path: str) -> str:
    """Normalize a potentially messy file path into repo-relative form."""
    if not path:
        return ""
    normalized = str(path).strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def normalize_file_paths(paths: Iterable[str]) -> list[str]:
    """Normalize and deduplicate file paths while preserving order."""
    seen = set()
    out = []
    for path in paths:
        normalized = normalize_file_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def canonicalize_file_path(path: str, valid_paths: set[str]) -> str | None:
    """
    Canonicalize one path against a known valid file set.

    Returns None if the path cannot be unambiguously resolved.
    """
    normalized = normalize_file_path(path)
    if not normalized:
        return None
    if normalized in valid_paths:
        return normalized

    suffix = "/" + normalized
    suffix_matches = [candidate for candidate in valid_paths if candidate.endswith(suffix)]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


def canonicalize_file_paths(paths: Iterable[str], valid_paths: set[str]) -> list[str]:
    """Canonicalize and deduplicate a list of file paths."""
    seen = set()
    out = []
    for path in paths:
        canonical = canonicalize_file_path(path, valid_paths)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out
