#!/usr/bin/env python3
"""Generate deterministic SWE-bench Verified N=100 patch manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import yaml
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.patch_study_split import allocate_verified_split

ANCHOR_REPOS = [
    "psf/requests",
    "pytest-dev/pytest",
    "pallets/flask",
]

EXTRA_REPO_CAPS = {
    "sympy/sympy": 12,
    "sphinx-doc/sphinx": 12,
    "matplotlib/matplotlib": 12,
    "scikit-learn/scikit-learn": 12,
    "astropy/astropy": 12,
    "pydata/xarray": 12,
}

RETRIEVAL_METHODS = {
    "oracle": "oracle",
    "gm_progressive": "gm_progressive",
    "rag_progressive": "rag_progressive",
    "none": "none",
}

SOURCE_PREFIXES = {
    "psf/requests": ["requests"],
    "pytest-dev/pytest": ["src/_pytest", "src/pytest"],
    "pallets/flask": ["src/flask"],
    "sympy/sympy": ["sympy"],
    "sphinx-doc/sphinx": ["sphinx"],
    "matplotlib/matplotlib": ["lib/matplotlib", "matplotlib"],
    "scikit-learn/scikit-learn": ["sklearn"],
    "astropy/astropy": ["astropy"],
    "pydata/xarray": ["xarray"],
}


def _repo_slug(repo: str) -> str:
    return repo.replace("/", "_").replace("-", "_")


def _manifest_payload(*, repo: str, retrieval_method: str, instance_ids: list[str]) -> dict:
    return {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "repo_name": repo,
        "source_prefixes": SOURCE_PREFIXES.get(repo, []),
        "retrieval_method": retrieval_method,
        "manager_max_turns": 8,
        "patch_max_turns": 1,
        "patch_max_output_tokens": 65536,
        "patch_max_file_chars": 200000,
        "api_timeout_s": 180,
        "manager_model": "gemini-3-flash-preview",
        "patch_model": "gemini-3-flash-preview",
        "rate_limit_max_retries": 2,
        "rate_limit_initial_delay_s": 0.5,
        "rate_limit_backoff_multiplier": 1.7,
        "rate_limit_max_delay_s": 5.0,
        "rate_limit_jitter_s": 0.2,
        "per_instance_cooldown_s": 0.0,
        "instance_wall_clock_cap_s": 480,
        "patch_apply_repair_retries": 1,
        "patch_retrieval_retry_max": 0,
        "patch_redact_paths_in_issue_text": False,
        "retrieval_redact_paths_in_issue_text": True,
        "instance_ids": instance_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SWE-bench Verified N=100 patch manifests")
    parser.add_argument("--seed", type=int, default=17, help="Deterministic split seed")
    parser.add_argument("--target-n", type=int, default=100, help="Target total instances")
    parser.add_argument(
        "--split-json",
        default="patch_manifests/verified_n100_split_v1.json",
        help="Path to write the frozen split JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="patch_manifests/n100_verified",
        help="Directory for generated manifests and ledger",
    )
    args = parser.parse_args()

    dataset = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    available: dict[str, list[str]] = {}
    for row in dataset:
        repo = str(row["repo"])
        iid = str(row["instance_id"])
        available.setdefault(repo, []).append(iid)

    selected = allocate_verified_split(
        available_ids_by_repo=available,
        anchor_repos=ANCHOR_REPOS,
        capped_repos=EXTRA_REPO_CAPS,
        seed=args.seed,
        target_n=args.target_n,
    )

    split_path = Path(args.split_json)
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_payload = {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "seed": args.seed,
        "target_n": args.target_n,
        "anchor_repos": ANCHOR_REPOS,
        "extra_repo_caps": EXTRA_REPO_CAPS,
        "selected_instance_ids": selected,
    }
    split_path.write_text(json.dumps(split_payload, indent=2), encoding="utf-8")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_entries = []

    for repo, ids in selected.items():
        sorted_ids = sorted(ids)
        for method_label, retrieval_method in RETRIEVAL_METHODS.items():
            payload = _manifest_payload(
                repo=repo,
                retrieval_method=retrieval_method,
                instance_ids=sorted_ids,
            )
            filename = f"{_repo_slug(repo)}_{method_label}_v1.yaml"
            path = output_dir / filename
            text = yaml.safe_dump(payload, sort_keys=False)
            path.write_text(text, encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            ledger_entries.append(
                {
                    "repo": repo,
                    "method": method_label,
                    "manifest_path": str(path),
                    "manifest_sha256": digest,
                    "n_instances": len(sorted_ids),
                }
            )

    ledger = {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "seed": args.seed,
        "target_n": args.target_n,
        "split_path": str(split_path),
        "entries": sorted(ledger_entries, key=lambda e: (e["repo"], e["method"])),
    }
    ledger_path = output_dir / "manifest_ledger_v1.json"
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    total = sum(len(v) for v in selected.values())
    print(f"Generated split: {total} instances across {len(selected)} repos")
    print(f"Split JSON: {split_path}")
    print(f"Ledger: {ledger_path}")
    for repo in sorted(selected):
        print(f"  {repo}: {len(selected[repo])}")


if __name__ == "__main__":
    main()
