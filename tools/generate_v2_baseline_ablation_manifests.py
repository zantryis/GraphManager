#!/usr/bin/env python3
"""Generate V2 ablation manifests for repomap_like and agentless_like_localization."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SOURCE_PREFIXES: dict[str, list[str]] = {
    "psf/requests": ["requests"],
    "pytest-dev/pytest": ["src/_pytest", "src/pytest"],
    "pallets/flask": ["src/flask"],
    "sympy/sympy": ["sympy"],
    "sphinx-doc/sphinx": ["sphinx"],
    "matplotlib/matplotlib": ["lib/matplotlib", "matplotlib"],
    "scikit-learn/scikit-learn": ["sklearn"],
    "astropy/astropy": ["astropy"],
    "pydata/xarray": ["xarray"],
    "django/django": ["django"],
    "pylint-dev/pylint": ["pylint"],
}


ABLATION_PROFILES: dict[str, dict] = {
    # RepoMap-like
    "repomap_base": {
        "retrieval_method": "repomap_like",
        "repomap_like_map_tokens": 1000,
        "repomap_like_top_k_files": 10,
        "repomap_like_use_llm_selector": False,
        "repomap_like_refresh_mode": "static_per_issue",
        "repomap_like_enable_same_module_edge": False,
        "repomap_like_personalization_enabled": True,
    },
    "repomap_map512": {
        "retrieval_method": "repomap_like",
        "repomap_like_map_tokens": 512,
        "repomap_like_top_k_files": 10,
        "repomap_like_use_llm_selector": False,
        "repomap_like_refresh_mode": "static_per_issue",
        "repomap_like_enable_same_module_edge": False,
        "repomap_like_personalization_enabled": True,
    },
    "repomap_map2000": {
        "retrieval_method": "repomap_like",
        "repomap_like_map_tokens": 2000,
        "repomap_like_top_k_files": 10,
        "repomap_like_use_llm_selector": False,
        "repomap_like_refresh_mode": "static_per_issue",
        "repomap_like_enable_same_module_edge": False,
        "repomap_like_personalization_enabled": True,
    },
    "repomap_no_personalization": {
        "retrieval_method": "repomap_like",
        "repomap_like_map_tokens": 1000,
        "repomap_like_top_k_files": 10,
        "repomap_like_use_llm_selector": False,
        "repomap_like_refresh_mode": "static_per_issue",
        "repomap_like_enable_same_module_edge": False,
        "repomap_like_personalization_enabled": False,
    },
    "repomap_selector": {
        "retrieval_method": "repomap_like",
        "repomap_like_map_tokens": 1000,
        "repomap_like_top_k_files": 10,
        "repomap_like_use_llm_selector": True,
        "repomap_like_refresh_mode": "static_per_issue",
        "repomap_like_enable_same_module_edge": False,
        "repomap_like_personalization_enabled": True,
    },
    # Agentless-like
    "agentless_stage1_only": {
        "retrieval_method": "agentless_like_localization",
        "agentless_like_stage2_enabled": False,
        "agentless_like_stage3_enabled": False,
        "agentless_like_edit_location_samples": 1,
        "agentless_like_file_branch_top_n": 3,
        "agentless_like_embed_branch_top_k": 20,
        "agentless_like_merge_top_k": 12,
        "agentless_like_stage3_context_window_lines": 10,
        "agentless_like_stage3_max_tokens_per_file": 1200,
        "agentless_like_constrained_candidates_max": 200,
        "agentless_like_reject_out_of_candidate_paths": True,
    },
    "agentless_stage12": {
        "retrieval_method": "agentless_like_localization",
        "agentless_like_stage2_enabled": True,
        "agentless_like_stage3_enabled": False,
        "agentless_like_edit_location_samples": 1,
        "agentless_like_file_branch_top_n": 3,
        "agentless_like_embed_branch_top_k": 20,
        "agentless_like_merge_top_k": 12,
        "agentless_like_stage3_context_window_lines": 10,
        "agentless_like_stage3_max_tokens_per_file": 1200,
        "agentless_like_constrained_candidates_max": 200,
        "agentless_like_reject_out_of_candidate_paths": True,
    },
    "agentless_full": {
        "retrieval_method": "agentless_like_localization",
        "agentless_like_stage2_enabled": True,
        "agentless_like_stage3_enabled": True,
        "agentless_like_edit_location_samples": 4,
        "agentless_like_file_branch_top_n": 3,
        "agentless_like_embed_branch_top_k": 20,
        "agentless_like_merge_top_k": 12,
        "agentless_like_stage3_context_window_lines": 10,
        "agentless_like_stage3_max_tokens_per_file": 1200,
        "agentless_like_constrained_candidates_max": 200,
        "agentless_like_reject_out_of_candidate_paths": True,
    },
    "agentless_embed_only": {
        "retrieval_method": "agentless_like_localization",
        "agentless_like_stage2_enabled": True,
        "agentless_like_stage3_enabled": True,
        "agentless_like_edit_location_samples": 4,
        "agentless_like_file_branch_top_n": 0,
        "agentless_like_embed_branch_top_k": 20,
        "agentless_like_merge_top_k": 12,
        "agentless_like_stage3_context_window_lines": 10,
        "agentless_like_stage3_max_tokens_per_file": 1200,
        "agentless_like_constrained_candidates_max": 200,
        "agentless_like_reject_out_of_candidate_paths": True,
    },
}


def _repo_slug(repo: str) -> str:
    return repo.replace("/", "_").replace("-", "_")


def _manifest_payload(*, repo: str, instance_ids: list[str], profile_payload: dict, profile_name: str) -> dict:
    payload = {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "repo_name": repo,
        "source_prefixes": SOURCE_PREFIXES.get(repo, []),
        "manager_max_turns": 8,
        "patch_max_turns": 1,
        "patch_max_output_tokens": 65536,
        "patch_max_file_chars": 200000,
        "retrieval_max_files_for_patch": 6,
        "api_timeout_s": 180,
        "manager_model": "gemini-3-flash-preview",
        "patch_model": "gemini-3-flash-preview",
        "rate_limit_max_retries": 3,
        "rate_limit_initial_delay_s": 0.5,
        "rate_limit_backoff_multiplier": 1.7,
        "rate_limit_max_delay_s": 5.0,
        "rate_limit_jitter_s": 0.2,
        "per_instance_cooldown_s": 0.0,
        "instance_wall_clock_cap_s": 600,
        "patch_apply_repair_retries": 1,
        "patch_retrieval_retry_max": 0,
        "patch_redact_paths_in_issue_text": False,
        "retrieval_redact_paths_in_issue_text": True,
        "patch_repair_samples": 1,
        "instance_ids": sorted(instance_ids),
        "ablation_profile": profile_name,
    }
    payload.update(profile_payload)
    return payload


def _write_manifest(path: Path, payload: dict) -> str:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate V2 ablation manifests for new baselines.")
    parser.add_argument(
        "--repos",
        nargs="*",
        default=["psf/requests", "pallets/flask", "pytest-dev/pytest"],
        help="Repos to include (default: requests/flask/pytest).",
    )
    parser.add_argument(
        "--profiles",
        nargs="*",
        default=sorted(ABLATION_PROFILES.keys()),
        help="Ablation profile names to include.",
    )
    parser.add_argument(
        "--output-dir",
        default="patch_manifests/v2_ablation",
        help="Output directory for generated manifests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    unknown_profiles = sorted(set(args.profiles) - set(ABLATION_PROFILES))
    if unknown_profiles:
        raise SystemExit(f"Unknown profiles: {', '.join(unknown_profiles)}")

    dataset = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    by_repo: dict[str, list[str]] = {}
    for row in dataset:
        repo = str(row["repo"])
        instance_id = str(row["instance_id"])
        by_repo.setdefault(repo, []).append(instance_id)

    output_dir = (ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ledger_entries = []
    for repo in sorted(args.repos):
        instance_ids = sorted(by_repo.get(repo, []))
        if not instance_ids:
            print(f"SKIP {repo}: no instances found in Verified test split")
            continue
        for profile in args.profiles:
            profile_payload = dict(ABLATION_PROFILES[profile])
            slug = _repo_slug(repo)
            filename = f"{slug}_{profile}_v1.yaml"
            path = output_dir / filename
            payload = _manifest_payload(
                repo=repo,
                instance_ids=instance_ids,
                profile_payload=profile_payload,
                profile_name=profile,
            )
            digest = _write_manifest(path, payload)
            ledger_entries.append(
                {
                    "repo": repo,
                    "profile": profile,
                    "retrieval_method": profile_payload["retrieval_method"],
                    "manifest_path": str(path.relative_to(ROOT)),
                    "manifest_sha256": digest,
                    "n_instances": len(instance_ids),
                }
            )
            print(f"Wrote {filename} ({len(instance_ids)} instances)")

    ledger = {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "repos": sorted(args.repos),
        "profiles": list(args.profiles),
        "entries": sorted(ledger_entries, key=lambda row: (row["repo"], row["profile"])),
    }
    ledger_path = output_dir / "manifest_ledger_v2_ablation.json"
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Ledger: {ledger_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
