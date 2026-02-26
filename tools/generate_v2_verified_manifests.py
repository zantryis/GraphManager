#!/usr/bin/env python3
"""Generate V2 SWE-bench Verified patch manifests.

V2 design decisions:
  - Dataset: SWE-bench Verified, full 500-instance test set (no cap per repo)
  - Methods (full matrix): oracle, gm_progressive, rag_progressive,
    gm_deterministic, raw_rag_function, raw_rag_fixed, bm25, agentic_cold_start,
    repomap_like, agentless_like_localization
  - Pilot: psf/requests instances only (8 instances in Verified)
  - instance_wall_clock_cap_s: 600 (bumped from V1's 480)
  - rate_limit_max_retries: 3 (bumped from V1's 2)

Manifest structure (per-repo, same pattern as N=100 generator):
  patch_manifests/v2_verified/
    pilot_oracle_v1.yaml              psf/requests, oracle
    pilot_gm_progressive_v1.yaml      psf/requests, gm_progressive
    pilot_bm25_v1.yaml                psf/requests, bm25
    <repo_slug>_oracle_v1.yaml        all instances in repo, oracle
    <repo_slug>_gm_progressive_v1.yaml  all instances in repo, gm_progressive
    <repo_slug>_rag_progressive_v1.yaml all instances in repo, rag_progressive
    <repo_slug>_gm_deterministic_v1.yaml all instances in repo, gm_deterministic
    <repo_slug>_raw_rag_function_v1.yaml all instances in repo, raw_rag_function
    <repo_slug>_raw_rag_fixed_v1.yaml all instances in repo, raw_rag_fixed
    <repo_slug>_bm25_v1.yaml          all instances in repo, bm25
    <repo_slug>_agentic_cold_start_v1.yaml  all instances in repo, agentic_cold_start
    <repo_slug>_repomap_like_v1.yaml      all instances in repo, repomap_like
    <repo_slug>_agentless_like_localization_v1.yaml  all instances in repo, agentless_like_localization
    manifest_ledger_v2.json

Usage:
    ./.venv/bin/python tools/generate_v2_verified_manifests.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PILOT_REPO = "psf/requests"

# Source prefixes per repo — used to scope the retrieval index to relevant Python files.
# Repos not listed here have their entire repo indexed (None → all .py files).
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
    "mwaskom/seaborn": ["seaborn"],
    "django/django": ["django"],
    "pylint-dev/pylint": ["pylint"],
    "psf/black": ["blib2to3", "src/black"],
}

# Full-run methods (11-method matrix with oracle included).
# rag_metadata is the key control: same embedding content as gm_deterministic
# (name + signature + docstring[:200]), no graph traversal.  Isolates graph
# structure contribution from embedding-content choice.
FULL_METHODS = [
    "oracle",
    "gm_progressive",
    "rag_progressive",
    "gm_deterministic",
    "raw_rag_function",
    "raw_rag_fixed",
    "rag_metadata",
    "bm25",
    "agentic_cold_start",
    "repomap_like",
    "agentless_like_localization",
]
METHOD_RETRIEVAL = {method: method for method in FULL_METHODS}

# Pilot methods (smaller smoke trio)
PILOT_METHODS = ["oracle", "gm_progressive", "bm25"]


def _repo_slug(repo: str) -> str:
    return repo.replace("/", "_").replace("-", "_")


def _manifest_payload(
    *,
    repo: str,
    retrieval_method: str,
    instance_ids: list[str],
) -> dict:
    """Build a V2 manifest payload with updated settings."""
    payload: dict = {
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "repo_name": repo,
        "source_prefixes": SOURCE_PREFIXES.get(repo, []),
        "retrieval_method": retrieval_method,
        # V2 timing / model settings
        "manager_max_turns": 8,
        "patch_max_turns": 1,
        "patch_max_output_tokens": 65536,
        "patch_max_file_chars": 200000,
        "retrieval_max_files_for_patch": 6,
        "api_timeout_s": 180,
        "manager_model": "gemini-3-flash-preview",
        "patch_model": "gemini-3-flash-preview",
        # V2 rate-limit settings (bumped from V1)
        "rate_limit_max_retries": 3,
        "rate_limit_initial_delay_s": 0.5,
        "rate_limit_backoff_multiplier": 1.7,
        "rate_limit_max_delay_s": 5.0,
        "rate_limit_jitter_s": 0.2,
        "per_instance_cooldown_s": 0.0,
        # V2 wall-clock cap (bumped from V1's 480)
        "instance_wall_clock_cap_s": 600,
        "patch_apply_repair_retries": 1,
        "patch_retrieval_retry_max": 0,
        "patch_redact_paths_in_issue_text": False,
        "retrieval_redact_paths_in_issue_text": True,
        # Single-sample repair (V2 explicit)
        "patch_repair_samples": 1,
        # Instance list (sorted for reproducibility)
        "instance_ids": sorted(instance_ids),
    }
    if retrieval_method == "rag_progressive":
        payload["rag_symmetric_tools"] = True
    elif retrieval_method in {"bm25", "raw_rag_function", "raw_rag_fixed", "rag_metadata"}:
        # Explicit for clarity in manifests: deterministic/no-tool RAG-family runs.
        payload["rag_symmetric_tools"] = False
    return payload


def _write_manifest(path: Path, payload: dict) -> str:
    """Write manifest YAML; return SHA-256 hex digest."""
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    print("Loading SWE-bench/SWE-bench_Verified (test split)...")
    dataset = load_dataset("SWE-bench/SWE-bench_Verified", split="test")

    # Group instance_ids by repo, sorted deterministically
    by_repo: dict[str, list[str]] = {}
    for row in dataset:
        repo = str(row["repo"])
        iid = str(row["instance_id"])
        by_repo.setdefault(repo, []).append(iid)

    total = sum(len(v) for v in by_repo.values())
    print(f"  Found {total} instances across {len(by_repo)} repos")
    for repo in sorted(by_repo):
        print(f"    {repo}: {len(by_repo[repo])} instances")

    output_dir = ROOT / "patch_manifests" / "v2_verified"
    output_dir.mkdir(parents=True, exist_ok=True)

    ledger_entries: list[dict] = []

    # --- Pilot manifests (psf/requests only) ---
    pilot_ids = sorted(by_repo.get(PILOT_REPO, []))
    print(f"\nPilot: {PILOT_REPO} ({len(pilot_ids)} instances)")
    for method_label in PILOT_METHODS:
        retrieval_method = METHOD_RETRIEVAL[method_label]
        payload = _manifest_payload(
            repo=PILOT_REPO,
            retrieval_method=retrieval_method,
            instance_ids=pilot_ids,
        )
        filename = f"pilot_{method_label}_v1.yaml"
        path = output_dir / filename
        digest = _write_manifest(path, payload)
        ledger_entries.append({
            "type": "pilot",
            "repo": PILOT_REPO,
            "method": method_label,
            "manifest_path": str(path.relative_to(ROOT)),
            "manifest_sha256": digest,
            "n_instances": len(pilot_ids),
        })
        print(f"  Wrote {filename} ({len(pilot_ids)} instances, {retrieval_method})")

    # --- Full manifests (per-repo, all instances) ---
    print("\nFull manifests:")
    for repo in sorted(by_repo):
        repo_ids = sorted(by_repo[repo])
        for method_label in FULL_METHODS:
            retrieval_method = METHOD_RETRIEVAL[method_label]
            payload = _manifest_payload(
                repo=repo,
                retrieval_method=retrieval_method,
                instance_ids=repo_ids,
            )
            slug = _repo_slug(repo)
            filename = f"{slug}_{method_label}_v1.yaml"
            path = output_dir / filename
            digest = _write_manifest(path, payload)
            ledger_entries.append({
                "type": "full",
                "repo": repo,
                "method": method_label,
                "manifest_path": str(path.relative_to(ROOT)),
                "manifest_sha256": digest,
                "n_instances": len(repo_ids),
            })
        print(f"  {repo}: {len(repo_ids)} instances × {len(FULL_METHODS)} methods")

    # --- Ledger ---
    full_entries = [e for e in ledger_entries if e["type"] == "full"]
    full_total = sum(
        e["n_instances"]
        for e in full_entries
        if e["method"] == "oracle"  # count unique instances once
    )
    ledger = {
        "schema_version": "v2",
        "dataset_name": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "full_run_total_instances": full_total,
        "full_run_repos": len(by_repo),
        "full_run_methods": FULL_METHODS,
        "pilot_repo": PILOT_REPO,
        "pilot_n_instances": len(pilot_ids),
        "pilot_methods": PILOT_METHODS,
        "entries": sorted(ledger_entries, key=lambda e: (e["type"], e["repo"], e["method"])),
    }
    ledger_path = output_dir / "manifest_ledger_v2.json"
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    n_full = len([e for e in ledger_entries if e["type"] == "full"])
    n_pilot = len([e for e in ledger_entries if e["type"] == "pilot"])
    print(f"\nDone. Output: {output_dir}")
    print(f"  Pilot manifests: {n_pilot}")
    print(f"  Full manifests:  {n_full}")
    print(f"  Total unique instances (oracle, 1 per): {full_total}")
    print(f"  Ledger: {ledger_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
