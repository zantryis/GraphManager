"""Dataset adapter layer for schema-normalized issue loading."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from datasets import load_dataset

from src.path_resolution import normalize_file_paths

_PATCH_FILE_PATTERN = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)


def extract_gold_files_from_patch(patch: str) -> list[str]:
    if not isinstance(patch, str) or not patch:
        return []
    seen = set()
    result = []
    for match in _PATCH_FILE_PATTERN.findall(patch):
        if match in seen:
            continue
        seen.add(match)
        result.append(match)
    return result


def normalize_gold_files(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        pieces = [piece.strip() for piece in re.split(r"[,;\n]", raw_value) if piece.strip()]
        return normalize_file_paths(pieces)
    if isinstance(raw_value, (list, tuple, set)):
        return normalize_file_paths([str(item).strip() for item in raw_value if str(item).strip()])
    return []


class BaseIssueAdapter(ABC):
    """Adapter contract for normalized issue records."""

    def __init__(self, dataset_name: str):
        self.dataset_name = dataset_name

    @abstractmethod
    def load_issues(
        self,
        repo: str,
        n: int,
        instance_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    def _normalize_common(
        self,
        row: dict,
        *,
        fallback_repo: str,
        split_name: str | None = None,
    ) -> dict:
        instance_id = (
            row.get("instance_id")
            or row.get("id")
            or row.get("issue_id")
            or row.get("problem_id")
            or ""
        )
        repo_name = row.get("repo") or row.get("repository") or fallback_repo
        base_commit = (
            row.get("base_commit")
            or row.get("base_sha")
            or row.get("commit")
            or row.get("snapshot_commit")
        )
        problem_statement = (
            row.get("problem_statement")
            or row.get("statement")
            or row.get("issue")
            or row.get("prompt")
            or ""
        )
        patch = row.get("patch") or row.get("gold_patch") or ""

        gold_files = normalize_gold_files(
            row.get("gold_files")
            or row.get("oracle_files")
            or row.get("target_files")
            or row.get("file_paths")
        )
        if not gold_files and patch:
            gold_files = normalize_file_paths(extract_gold_files_from_patch(patch))

        normalized = {
            "instance_id": str(instance_id),
            "repo": str(repo_name),
            "problem_statement": str(problem_statement),
            "patch": str(patch),
            "base_commit": str(base_commit) if base_commit else None,
            "gold_files": gold_files,
        }
        if split_name:
            normalized["split"] = split_name
        return normalized


class SWEBenchIssueAdapter(BaseIssueAdapter):
    """Adapter for SWE-bench style issue datasets."""

    DEFAULT_SPLITS = ("test", "train", "dev")

    def __init__(self, dataset_name: str = "SWE-bench/SWE-bench", splits: tuple[str, ...] | None = None):
        super().__init__(dataset_name=dataset_name)
        self.splits = tuple(splits or self.DEFAULT_SPLITS)

    def load_issues(
        self,
        repo: str,
        n: int,
        instance_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        all_issues: list[dict] = []
        for split_name in self.splits:
            try:
                ds = load_dataset(self.dataset_name, split=split_name)
            except Exception:
                continue
            for row in ds:
                if row.get("repo") != repo:
                    continue
                normalized = self._normalize_common(
                    row,
                    fallback_repo=repo,
                    split_name=split_name,
                )
                all_issues.append(normalized)

        deduped: list[dict] = []
        seen_ids: set[str] = set()
        for issue in all_issues:
            instance_id = issue.get("instance_id", "")
            if instance_id in seen_ids:
                continue
            seen_ids.add(instance_id)
            deduped.append(issue)
        return _select_manifest_issues(deduped, n=n, instance_ids=instance_ids)


class SWEPolyBenchIssueAdapter(BaseIssueAdapter):
    """Adapter for SWE-PolyBench retrieval/evaluation issue records."""

    DEFAULT_SPLITS = ("test", "validation", "dev", "train")

    def __init__(
        self,
        dataset_name: str = "AmazonScience/SWE-PolyBench_Verified",
        splits: tuple[str, ...] | None = None,
    ):
        super().__init__(dataset_name=dataset_name)
        self.splits = tuple(splits or self.DEFAULT_SPLITS)

    def load_issues(
        self,
        repo: str,
        n: int,
        instance_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        all_issues: list[dict] = []
        for split_name in self.splits:
            try:
                ds = load_dataset(self.dataset_name, split=split_name)
            except Exception:
                continue
            for row in ds:
                repo_name = row.get("repo") or row.get("repository")
                if repo_name != repo:
                    continue
                normalized = self._normalize_common(
                    row,
                    fallback_repo=repo,
                    split_name=split_name,
                )
                all_issues.append(normalized)
        deduped: list[dict] = []
        seen_ids: set[str] = set()
        for issue in all_issues:
            instance_id = issue.get("instance_id", "")
            if instance_id in seen_ids:
                continue
            seen_ids.add(instance_id)
            deduped.append(issue)
        return _select_manifest_issues(deduped, n=n, instance_ids=instance_ids)


def _select_manifest_issues(
    issues: list[dict],
    *,
    n: int,
    instance_ids: list[str] | tuple[str, ...] | None,
) -> list[dict]:
    limit = max(int(n or 0), 0)
    if not instance_ids:
        return issues[:limit]

    id_to_issue = {
        str(issue.get("instance_id", "")): issue
        for issue in issues
        if issue.get("instance_id")
    }
    selected: list[dict] = []
    seen: set[str] = set()
    for raw_id in instance_ids:
        instance_id = str(raw_id).strip()
        if not instance_id or instance_id in seen:
            continue
        issue = id_to_issue.get(instance_id)
        if issue is None:
            continue
        selected.append(issue)
        seen.add(instance_id)
        if len(selected) >= limit:
            break
    return selected


def build_issue_adapter(task_family: str, dataset_name: str) -> BaseIssueAdapter:
    family = (task_family or "").strip().lower()
    dataset_name_l = (dataset_name or "").lower()
    if "polybench" in dataset_name_l or family in {"swe-polybench", "polybench"}:
        return SWEPolyBenchIssueAdapter(dataset_name=dataset_name)
    return SWEBenchIssueAdapter(dataset_name=dataset_name)
