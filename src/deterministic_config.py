"""Utilities for loading and validating gm_deterministic tuning configs."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

DETERMINISTIC_KEYS = (
    "deterministic_seed_k",
    "deterministic_depth",
    "deterministic_neighbor_cap",
    "deterministic_min_return_files",
    "deterministic_score_ratio_cutoff",
    "deterministic_min_score_cutoff",
    "deterministic_hub_degree_threshold",
    "deterministic_hub_penalty_scale",
    "deterministic_w_sem",
    "deterministic_w_graph",
    "deterministic_w_conf",
    "deterministic_w_hint",
    "deterministic_w_pen",
)

_WEIGHT_KEYS = (
    "deterministic_w_sem",
    "deterministic_w_graph",
    "deterministic_w_conf",
    "deterministic_w_hint",
    "deterministic_w_pen",
)

_ALT_KEY_MAP = {
    "seed_k": "deterministic_seed_k",
    "depth": "deterministic_depth",
    "neighbor_cap": "deterministic_neighbor_cap",
    "min_return_files": "deterministic_min_return_files",
    "score_ratio_cutoff": "deterministic_score_ratio_cutoff",
    "min_score_cutoff": "deterministic_min_score_cutoff",
    "hub_degree_threshold": "deterministic_hub_degree_threshold",
    "hub_penalty_scale": "deterministic_hub_penalty_scale",
    "w_sem": "deterministic_w_sem",
    "w_graph": "deterministic_w_graph",
    "w_conf": "deterministic_w_conf",
    "w_hint": "deterministic_w_hint",
    "w_pen": "deterministic_w_pen",
}


def _as_int(name: str, value) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be >= 1")
    return parsed


def _as_nonnegative_float(name: str, value) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{name} must be >= 0")
    return parsed


def _normalize_payload(payload: dict) -> dict:
    normalized = {}
    for key, value in payload.items():
        if key in DETERMINISTIC_KEYS:
            normalized[key] = value
        elif key in _ALT_KEY_MAP:
            normalized[_ALT_KEY_MAP[key]] = value
    return normalized


def validate_deterministic_config(overrides: dict) -> dict:
    """Validate deterministic overrides and return normalized typed values."""
    validated = {}
    for key, value in overrides.items():
        if key in {
            "deterministic_seed_k",
            "deterministic_depth",
            "deterministic_neighbor_cap",
            "deterministic_min_return_files",
            "deterministic_hub_degree_threshold",
        }:
            validated[key] = _as_int(key, value)
        elif key in {
            "deterministic_score_ratio_cutoff",
            "deterministic_min_score_cutoff",
            "deterministic_hub_penalty_scale",
        }:
            validated[key] = _as_nonnegative_float(key, value)
        elif key in _WEIGHT_KEYS:
            parsed = float(value)
            if parsed < 0 or parsed > 0.7:
                raise ValueError(f"{key} must be in [0, 0.7]")
            validated[key] = parsed
        else:
            raise ValueError(f"Unsupported deterministic key: {key}")

    present_weights = [validated[k] for k in _WEIGHT_KEYS if k in validated]
    if present_weights:
        total = sum(present_weights)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("deterministic weights must sum to 1.0")
    return validated


def load_deterministic_config(path: str | Path) -> dict:
    """Load deterministic tuning config (JSON or YAML) for run_experiment."""
    config_path = Path(path)
    raw_text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() in {".json"}:
        raw = json.loads(raw_text)
    else:
        raw = yaml.safe_load(raw_text)

    if not isinstance(raw, dict):
        raise ValueError("deterministic config must be a mapping")

    payload = raw.get("deterministic_retrieval", raw)
    if not isinstance(payload, dict):
        raise ValueError("deterministic_retrieval must be a mapping")

    normalized = _normalize_payload(payload)
    if not normalized:
        raise ValueError("deterministic config does not contain supported keys")
    return validate_deterministic_config(normalized)

