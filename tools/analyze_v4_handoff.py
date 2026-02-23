#!/usr/bin/env python3
"""Generate v4 handoff analysis artifacts from N=100 patch summaries."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


METHODS = ("oracle", "gm_progressive", "rag_progressive", "none")
GM_METHOD = "gm_progressive"
RAG_METHOD = "rag_progressive"

LEDGER_PATH = Path("patch_manifests/n100_verified/manifest_ledger_v1.json")
PATCH_RUNS_ROOT = Path("results/patch_runs")
OUTPUT_DIR = Path("results/analysis_v4_handoff")

FROZEN_RUN_IDS: dict[str, dict[str, str | None]] = {
    "astropy/astropy": {
        "oracle": "20260218_223151",
        "gm_progressive": "20260219_172533",
        "rag_progressive": "20260220_061030",
        "none": None,
    },
    "matplotlib/matplotlib": {
        "oracle": "20260218_234323",
        "gm_progressive": "20260221_165614",  # rerun (timeout confound fix)
        "rag_progressive": "20260221_202646",  # rerun (timeout confound fix)
        "none": None,
    },
    "pallets/flask": {
        "oracle": "20260219_021634",
        "gm_progressive": "20260219_215321",
        "rag_progressive": "20260220_115054",
        "none": None,
    },
    "psf/requests": {
        "oracle": "20260219_022540",
        "gm_progressive": "20260219_220131",
        "rag_progressive": "20260220_115755",
        "none": None,
    },
    "pydata/xarray": {
        "oracle": "20260219_030133",
        "gm_progressive": "20260219_223642",
        "rag_progressive": "20260220_123601",
        "none": None,
    },
    "pytest-dev/pytest": {
        "oracle": "20260219_043417",
        "gm_progressive": "20260220_000151",
        "rag_progressive": "20260220_134949",
        "none": None,
    },
    "scikit-learn/scikit-learn": {
        "oracle": "20260219_155601",
        "gm_progressive": "20260220_014233",
        "rag_progressive": "20260220_152959",
        "none": None,
    },
    "sphinx-doc/sphinx": {
        "oracle": "20260219_133935",
        "gm_progressive": "20260221_141004",  # rerun (timeout confound fix)
        "rag_progressive": "20260221_153148",  # rerun (timeout confound fix)
        "none": None,
    },
    "sympy/sympy": {
        "oracle": "20260219_145153",
        "gm_progressive": "20260221_111111",  # rerun (timeout confound fix)
        "rag_progressive": "20260221_123817",  # rerun (timeout confound fix)
        "none": None,
    },
}


@dataclass
class Cell:
    repo: str
    method: str
    manifest_path: str
    expected_n_instances: int
    run_id: str | None
    summary: dict[str, Any] | None
    completion_marker: str
    completed: bool
    n_instances: int | None
    n_resolved: int | None
    resolved_rate: float | None
    resolved_instances: list[str]
    retrieval_setup_tokens: int
    retrieval_runtime_tokens: int
    patch_runtime_tokens: int
    total_cost_tokens: int
    setup_tokens_graph_built: int | None
    setup_tokens_rag_built: int | None
    setup_tokens_method_accounted: int
    timeout_count: int


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_int(value: Any, default: int = 0) -> int:
    if _is_number(value):
        return int(value)
    return default


def _completion_marker(summary: dict[str, Any] | None) -> tuple[str, bool, int | None, list[str]]:
    if not summary:
        return "missing_summary", False, None, []
    harness = summary.get("harness_results")
    if isinstance(harness, dict) and _is_number(harness.get("n_resolved")):
        n_resolved = int(harness.get("n_resolved"))
        resolved_instances = harness.get("resolved_instances")
        if isinstance(resolved_instances, list):
            resolved = sorted(str(x) for x in resolved_instances)
        else:
            resolved = []
        return "harness_results", True, n_resolved, resolved
    if "harness_error" in summary:
        return "harness_error", True, None, []
    if "harness_skipped_reason" in summary:
        return "harness_skipped_reason", True, None, []
    return "incomplete", False, None, []


def _scan_summaries() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for summary_path in sorted(PATCH_RUNS_ROOT.glob("*/patch_summary.json")):
        try:
            payload = _read_json(summary_path)
        except Exception:
            continue
        run_id = summary_path.parent.name
        manifest_path = str(payload.get("manifest") or "")
        method = str(payload.get("retrieval_method") or "")
        marker, completed, n_resolved, resolved_instances = _completion_marker(payload)
        records.append(
            {
                "run_id": run_id,
                "summary_path": summary_path,
                "manifest_path": manifest_path,
                "method": method,
                "summary": payload,
                "completion_marker": marker,
                "completed": completed,
                "n_resolved": n_resolved,
                "resolved_instances": resolved_instances,
            }
        )
    return records


def _select_cell_summary(
    *,
    repo: str,
    method: str,
    manifest_path: str,
    summary_records: list[dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None]:
    candidates = [
        record
        for record in summary_records
        if record["manifest_path"] == manifest_path and record["method"] == method
    ]
    if method != "none":
        frozen_run_id = FROZEN_RUN_IDS.get(repo, {}).get(method)
        if frozen_run_id:
            frozen_path = PATCH_RUNS_ROOT / frozen_run_id / "patch_summary.json"
            if frozen_path.exists():
                return frozen_run_id, _read_json(frozen_path)
        if candidates:
            chosen = sorted(candidates, key=lambda item: item["run_id"])[-1]
            return chosen["run_id"], chosen["summary"]
        return None, None

    completed_candidates = [record for record in candidates if record["completed"]]
    if completed_candidates:
        chosen = sorted(completed_candidates, key=lambda item: item["run_id"])[-1]
        return chosen["run_id"], chosen["summary"]
    if candidates:
        chosen = sorted(candidates, key=lambda item: item["run_id"])[-1]
        return chosen["run_id"], chosen["summary"]
    return None, None


def _build_cells() -> list[Cell]:
    ledger = _read_json(LEDGER_PATH)
    entries = ledger.get("entries", [])
    summary_records = _scan_summaries()
    manifest_map: dict[tuple[str, str], tuple[str, int]] = {}
    for entry in entries:
        repo = str(entry.get("repo"))
        method = str(entry.get("method"))
        if method not in METHODS:
            continue
        manifest_map[(repo, method)] = (
            str(entry.get("manifest_path")),
            int(entry.get("n_instances", 0)),
        )

    cells: list[Cell] = []
    for repo in sorted({key[0] for key in manifest_map}):
        for method in METHODS:
            manifest_path, expected_n = manifest_map[(repo, method)]
            run_id, summary = _select_cell_summary(
                repo=repo,
                method=method,
                manifest_path=manifest_path,
                summary_records=summary_records,
            )
            marker, completed, n_resolved, resolved_instances = _completion_marker(summary)
            n_instances = int(summary.get("n_instances", expected_n)) if summary else None
            if n_resolved is not None and n_instances:
                resolved_rate = n_resolved / n_instances
            else:
                resolved_rate = None
            per_instance = summary.get("per_instance", []) if isinstance(summary, dict) else []
            timeout_count = sum(
                1
                for item in per_instance
                if isinstance(item, dict)
                and (
                    item.get("patch_status") == "timeout_budget_exceeded"
                    or bool(item.get("timeout_budget_exceeded"))
                )
            )
            setup_graph = None
            setup_rag = None
            method_setup = 0
            if isinstance(summary, dict):
                if "setup_tokens_graph_built" in summary:
                    setup_graph = _to_int(summary.get("setup_tokens_graph_built"))
                if "setup_tokens_rag_built" in summary:
                    setup_rag = _to_int(summary.get("setup_tokens_rag_built"))
                if "setup_tokens_method_accounted" in summary:
                    method_setup = _to_int(summary.get("setup_tokens_method_accounted"))
                else:
                    method_setup = _to_int(summary.get("retrieval_setup_tokens"))
            cells.append(
                Cell(
                    repo=repo,
                    method=method,
                    manifest_path=manifest_path,
                    expected_n_instances=expected_n,
                    run_id=run_id,
                    summary=summary,
                    completion_marker=marker,
                    completed=completed,
                    n_instances=n_instances,
                    n_resolved=n_resolved,
                    resolved_rate=resolved_rate,
                    resolved_instances=resolved_instances,
                    retrieval_setup_tokens=_to_int((summary or {}).get("retrieval_setup_tokens")),
                    retrieval_runtime_tokens=_to_int((summary or {}).get("retrieval_runtime_tokens")),
                    patch_runtime_tokens=_to_int((summary or {}).get("patch_runtime_tokens")),
                    total_cost_tokens=_to_int((summary or {}).get("total_cost_tokens")),
                    setup_tokens_graph_built=setup_graph,
                    setup_tokens_rag_built=setup_rag,
                    setup_tokens_method_accounted=method_setup,
                    timeout_count=timeout_count,
                )
            )
    return cells


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_resolved_rate_table(cells: list[Cell]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    repos = sorted({cell.repo for cell in cells})
    by_key = {(cell.repo, cell.method): cell for cell in cells}
    for repo in repos:
        row: dict[str, Any] = {"repo": repo}
        for method in METHODS:
            cell = by_key[(repo, method)]
            prefix = method.replace("_progressive", "")
            row[f"{prefix}_run_id"] = cell.run_id or ""
            row[f"{prefix}_completed"] = "yes" if cell.completed else "no"
            row[f"{prefix}_completion_marker"] = cell.completion_marker
            row[f"{prefix}_n_instances"] = cell.n_instances if cell.n_instances is not None else ""
            row[f"{prefix}_n_resolved"] = cell.n_resolved if cell.n_resolved is not None else ""
            row[f"{prefix}_resolved_rate"] = (
                f"{cell.resolved_rate:.4f}" if cell.resolved_rate is not None else ""
            )
        rows.append(row)
    return rows


def _compute_dual_accounting(cells: list[Cell]) -> list[dict[str, Any]]:
    by_key = {(cell.repo, cell.method): cell for cell in cells}
    rows: list[dict[str, Any]] = []
    for repo in sorted({cell.repo for cell in cells}):
        gm_cell = by_key[(repo, GM_METHOD)]
        rag_cell = by_key[(repo, RAG_METHOD)]
        for method in METHODS:
            cell = by_key[(repo, method)]
            method_setup = cell.setup_tokens_method_accounted
            if method in {GM_METHOD, RAG_METHOD}:
                if cell.setup_tokens_graph_built is not None or cell.setup_tokens_rag_built is not None:
                    as_run_setup = _to_int(cell.setup_tokens_graph_built) + _to_int(cell.setup_tokens_rag_built)
                    approx = "direct_summary_fields"
                else:
                    paired_setup = (
                        rag_cell.setup_tokens_method_accounted
                        if method == GM_METHOD
                        else gm_cell.setup_tokens_method_accounted
                    )
                    as_run_setup = method_setup + paired_setup
                    approx = "frozen_dual_build_proxy_from_paired_method_setup_tokens"
            else:
                as_run_setup = method_setup
                approx = "single_setup_path"

            runtime_total = cell.retrieval_runtime_tokens + cell.patch_runtime_tokens
            method_total = runtime_total + method_setup
            as_run_total = runtime_total + as_run_setup

            cpr_method = None
            cpr_as_run = None
            if isinstance(cell.n_resolved, int) and cell.n_resolved > 0:
                cpr_method = method_total / cell.n_resolved
                cpr_as_run = as_run_total / cell.n_resolved

            rows.append(
                {
                    "repo": repo,
                    "method": method,
                    "run_id": cell.run_id or "",
                    "completed": "yes" if cell.completed else "no",
                    "completion_marker": cell.completion_marker,
                    "n_instances": cell.n_instances if cell.n_instances is not None else "",
                    "n_resolved": cell.n_resolved if cell.n_resolved is not None else "",
                    "method_accounted_setup_tokens": method_setup,
                    "as_run_setup_tokens": as_run_setup,
                    "setup_delta_tokens": as_run_setup - method_setup,
                    "retrieval_runtime_tokens": cell.retrieval_runtime_tokens,
                    "patch_runtime_tokens": cell.patch_runtime_tokens,
                    "method_accounted_total_tokens": method_total,
                    "as_run_total_tokens": as_run_total,
                    "total_delta_tokens": as_run_total - method_total,
                    "cost_per_resolved_method_accounted": (
                        f"{cpr_method:.6f}" if cpr_method is not None else ""
                    ),
                    "cost_per_resolved_as_run": f"{cpr_as_run:.6f}" if cpr_as_run is not None else "",
                    "as_run_setup_approximation": approx,
                }
            )
    return rows


def _aggregate_pooled_cpr(dual_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method in METHODS:
        method_rows = [row for row in dual_rows if row["method"] == method and row["completed"] == "yes"]
        for view in ("method_accounted", "as_run_consumed"):
            if view == "method_accounted":
                total_tokens = sum(int(row["method_accounted_total_tokens"]) for row in method_rows)
            else:
                total_tokens = sum(int(row["as_run_total_tokens"]) for row in method_rows)
            resolved_total = sum(int(row["n_resolved"]) for row in method_rows if str(row["n_resolved"]).isdigit())
            instances_total = sum(int(row["n_instances"]) for row in method_rows if str(row["n_instances"]).isdigit())
            cpr = None
            if resolved_total > 0:
                cpr = total_tokens / resolved_total
            rows.append(
                {
                    "accounting_view": view,
                    "method": method,
                    "n_repos_included": len(method_rows),
                    "n_instances_total": instances_total,
                    "n_resolved_total": resolved_total,
                    "total_cost_tokens": total_tokens,
                    "cost_per_resolved_issue": f"{cpr:.6f}" if cpr is not None else "",
                }
            )
    return rows


def _build_timeout_sensitivity(cells: list[Cell]) -> tuple[list[dict[str, Any]], dict[str, float | None]]:
    rows: list[dict[str, Any]] = []
    method_rates: dict[str, dict[str, float | None]] = {}
    for method in METHODS:
        method_cells = [cell for cell in cells if cell.method == method and cell.completed]
        n_instances = sum(cell.n_instances or 0 for cell in method_cells)
        n_resolved = sum(cell.n_resolved or 0 for cell in method_cells if cell.n_resolved is not None)
        n_timeouts = sum(cell.timeout_count for cell in method_cells)
        all_in_rate = (n_resolved / n_instances) if n_instances > 0 else None
        timeout_excluded_denom = n_instances - n_timeouts
        timeout_excluded_rate = (
            n_resolved / timeout_excluded_denom if timeout_excluded_denom > 0 else None
        )
        method_rates[method] = {
            "all_in_rate": all_in_rate,
            "timeout_excluded_rate": timeout_excluded_rate,
        }
        rows.append(
            {
                "method": method,
                "n_repos_included": len(method_cells),
                "n_instances": n_instances,
                "n_resolved": n_resolved,
                "n_timeouts": n_timeouts,
                "resolved_rate_all_in": f"{all_in_rate:.6f}" if all_in_rate is not None else "",
                "resolved_rate_timeout_excluded": (
                    f"{timeout_excluded_rate:.6f}" if timeout_excluded_rate is not None else ""
                ),
            }
        )

    gm_all_in = method_rates.get(GM_METHOD, {}).get("all_in_rate")
    rag_all_in = method_rates.get(RAG_METHOD, {}).get("all_in_rate")
    gm_timeout = method_rates.get(GM_METHOD, {}).get("timeout_excluded_rate")
    rag_timeout = method_rates.get(RAG_METHOD, {}).get("timeout_excluded_rate")

    gap_all_in = (gm_all_in - rag_all_in) if gm_all_in is not None and rag_all_in is not None else None
    gap_timeout = (gm_timeout - rag_timeout) if gm_timeout is not None and rag_timeout is not None else None
    shift_pp = abs((gap_timeout - gap_all_in) * 100.0) if gap_all_in is not None and gap_timeout is not None else None
    rows.append(
        {
            "method": "gm_minus_rag_gap",
            "n_repos_included": "",
            "n_instances": "",
            "n_resolved": "",
            "n_timeouts": "",
            "resolved_rate_all_in": f"{gap_all_in:.6f}" if gap_all_in is not None else "",
            "resolved_rate_timeout_excluded": f"{gap_timeout:.6f}" if gap_timeout is not None else "",
            "shift_pp": f"{shift_pp:.6f}" if shift_pp is not None else "",
        }
    )
    return rows, {"gap_all_in": gap_all_in, "gap_timeout": gap_timeout, "shift_pp": shift_pp}


def _exact_binomial_two_sided_p(b: int, c: int) -> float:
    n = b + c
    if n <= 0:
        return 1.0
    k = min(b, c)
    prob = 0.0
    for i in range(0, k + 1):
        prob += math.comb(n, i) * (0.5 ** n)
    return min(1.0, 2.0 * prob)


def _build_pairwise_outputs(cells: list[Cell]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    by_key = {(cell.repo, cell.method): cell for cell in cells}
    discordant_rows: list[dict[str, Any]] = []
    a = b = c = d = 0
    skipped_repos: list[str] = []
    for repo in sorted({cell.repo for cell in cells}):
        gm_cell = by_key[(repo, GM_METHOD)]
        rag_cell = by_key[(repo, RAG_METHOD)]
        if not (gm_cell.completed and rag_cell.completed):
            skipped_repos.append(repo)
            continue
        gm_resolved = set(gm_cell.resolved_instances)
        rag_resolved = set(rag_cell.resolved_instances)
        gm_map = {
            str(item.get("instance_id")): str(item.get("patch_status"))
            for item in (gm_cell.summary or {}).get("per_instance", [])
            if isinstance(item, dict) and item.get("instance_id")
        }
        rag_map = {
            str(item.get("instance_id")): str(item.get("patch_status"))
            for item in (rag_cell.summary or {}).get("per_instance", [])
            if isinstance(item, dict) and item.get("instance_id")
        }
        all_instances = sorted(set(gm_map) | set(rag_map))
        for instance_id in all_instances:
            gm_yes = instance_id in gm_resolved
            rag_yes = instance_id in rag_resolved
            if gm_yes and rag_yes:
                a += 1
            elif gm_yes and not rag_yes:
                b += 1
            elif not gm_yes and rag_yes:
                c += 1
            else:
                d += 1

            if gm_yes == rag_yes:
                continue
            winner = GM_METHOD if gm_yes else RAG_METHOD
            loser = RAG_METHOD if gm_yes else GM_METHOD
            loser_status = rag_map.get(instance_id, "") if gm_yes else gm_map.get(instance_id, "")
            winner_status = gm_map.get(instance_id, "") if gm_yes else rag_map.get(instance_id, "")
            timeout_confounded = loser_status == "timeout_budget_exceeded"
            discordant_rows.append(
                {
                    "repo": repo,
                    "instance_id": instance_id,
                    "winner": winner,
                    "loser": loser,
                    "winner_patch_status": winner_status,
                    "loser_patch_status": loser_status,
                    "timeout_confounded": "yes" if timeout_confounded else "no",
                }
            )

    n_discordant = b + c
    mcnemar = {
        "contingency": {"both_resolved": a, "gm_only": b, "rag_only": c, "both_unresolved": d},
        "n_pairs": a + b + c + d,
        "n_discordant": n_discordant,
        "exact_binomial_two_sided_p": _exact_binomial_two_sided_p(b, c),
        "chi_square_cc": (((abs(b - c) - 1) ** 2) / n_discordant) if n_discordant > 0 else 0.0,
        "skipped_repos": skipped_repos,
    }
    timeout_confounded_count = sum(1 for row in discordant_rows if row["timeout_confounded"] == "yes")
    timeout_confounded_majority = (
        timeout_confounded_count > (len(discordant_rows) / 2) if discordant_rows else False
    )
    meta = {
        "discordant_count": len(discordant_rows),
        "timeout_confounded_count": timeout_confounded_count,
        "timeout_confounded_majority": timeout_confounded_majority,
    }
    return mcnemar, discordant_rows, meta


def _gate_decision(
    pooled_rows: list[dict[str, Any]],
    timeout_meta: dict[str, float | None],
    discordant_meta: dict[str, Any],
) -> dict[str, Any]:
    pooled_map = {
        (row["accounting_view"], row["method"]): row
        for row in pooled_rows
    }

    def cpr(view: str, method: str) -> float | None:
        value = pooled_map.get((view, method), {}).get("cost_per_resolved_issue", "")
        if value == "":
            return None
        return float(value)

    gm_method_cpr = cpr("method_accounted", GM_METHOD)
    rag_method_cpr = cpr("method_accounted", RAG_METHOD)
    gm_as_run_cpr = cpr("as_run_consumed", GM_METHOD)
    rag_as_run_cpr = cpr("as_run_consumed", RAG_METHOD)

    criterion_1 = False
    if None not in (gm_method_cpr, rag_method_cpr, gm_as_run_cpr, rag_as_run_cpr):
        method_sign = gm_method_cpr - rag_method_cpr
        as_run_sign = gm_as_run_cpr - rag_as_run_cpr
        criterion_1 = (method_sign * as_run_sign) < 0

    shift_pp = timeout_meta.get("shift_pp")
    criterion_2 = (shift_pp is not None) and (shift_pp > 5.0)

    criterion_3 = bool(discordant_meta.get("timeout_confounded_majority", False))
    rerun_trigger = criterion_1 or criterion_2 or criterion_3
    return {
        "criterion_1_cpr_ranking_reversal": criterion_1,
        "criterion_2_timeout_shift_gt_5pp": criterion_2,
        "criterion_3_timeout_confounded_discordant_majority": criterion_3,
        "rerun_trigger": rerun_trigger,
        "supporting_metrics": {
            "gm_method_accounted_cpr": gm_method_cpr,
            "rag_method_accounted_cpr": rag_method_cpr,
            "gm_as_run_cpr": gm_as_run_cpr,
            "rag_as_run_cpr": rag_as_run_cpr,
            "gm_minus_rag_gap_all_in": timeout_meta.get("gap_all_in"),
            "gm_minus_rag_gap_timeout_excluded": timeout_meta.get("gap_timeout"),
            "gap_shift_pp": shift_pp,
            "discordant_count": discordant_meta.get("discordant_count"),
            "timeout_confounded_discordant_count": discordant_meta.get("timeout_confounded_count"),
        },
    }


def _write_rerun_gate_markdown(
    *,
    path: Path,
    gate: dict[str, Any],
    cells: list[Cell],
) -> None:
    none_cells = [cell for cell in cells if cell.method == "none"]
    none_completed = sum(1 for cell in none_cells if cell.completed)
    lines = [
        "# Rerun Gate Decision (v4)",
        "",
        "## Decision",
        "",
        f"- Trigger targeted rerun: **{'YES' if gate['rerun_trigger'] else 'NO'}**",
        "- Targeted rerun scope if YES: `sympy/sympy`, `sphinx-doc/sphinx`, `matplotlib/matplotlib` for GM+RAG only.",
        "",
        "## Criteria",
        "",
        f"- Criterion 1 (CPR ranking reversal method-accounted vs as-run): **{'PASS' if gate['criterion_1_cpr_ranking_reversal'] else 'NO'}**",
        f"- Criterion 2 (timeout sensitivity shifts GM-RAG gap by >5pp): **{'PASS' if gate['criterion_2_timeout_shift_gt_5pp'] else 'NO'}**",
        (
            "- Criterion 3 (timeout-confounded majority among discordant instances): "
            f"**{'PASS' if gate['criterion_3_timeout_confounded_discordant_majority'] else 'NO'}**"
        ),
        "",
        "## Supporting Metrics",
        "",
        f"- GM CPR (method-accounted): {gate['supporting_metrics']['gm_method_accounted_cpr']}",
        f"- RAG CPR (method-accounted): {gate['supporting_metrics']['rag_method_accounted_cpr']}",
        f"- GM CPR (as-run-consumed): {gate['supporting_metrics']['gm_as_run_cpr']}",
        f"- RAG CPR (as-run-consumed): {gate['supporting_metrics']['rag_as_run_cpr']}",
        f"- GM-RAG gap (all-in): {gate['supporting_metrics']['gm_minus_rag_gap_all_in']}",
        f"- GM-RAG gap (timeout-excluded): {gate['supporting_metrics']['gm_minus_rag_gap_timeout_excluded']}",
        f"- Gap shift (pp): {gate['supporting_metrics']['gap_shift_pp']}",
        f"- Discordant count: {gate['supporting_metrics']['discordant_count']}",
        (
            "- Timeout-confounded discordant count: "
            f"{gate['supporting_metrics']['timeout_confounded_discordant_count']}"
        ),
        "",
        "## Phase 2 Completion Snapshot",
        "",
        f"- none completed cells: {none_completed}/{len(none_cells)}",
        "- Completion criterion: `harness_results.n_resolved` OR `harness_error` OR `harness_skipped_reason`.",
        "",
        "## Dual-Accounting Assumption",
        "",
        "- Frozen GM/RAG runs were produced under a dual-build pipeline. When explicit built-token fields are absent,",
        "  as-run setup is approximated as: method-accounted setup + paired-method setup on the same repo",
        "  (GM row uses RAG setup proxy; RAG row uses GM setup proxy).",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = _build_cells()

    resolved_rows = _build_resolved_rate_table(cells)
    _write_csv(
        OUTPUT_DIR / "resolved_rate_4method_table.csv",
        resolved_rows,
        fieldnames=list(resolved_rows[0].keys()),
    )

    dual_rows = _compute_dual_accounting(cells)
    _write_csv(
        OUTPUT_DIR / "dual_accounting_table.csv",
        dual_rows,
        fieldnames=list(dual_rows[0].keys()),
    )

    pooled_rows = _aggregate_pooled_cpr(dual_rows)
    _write_csv(
        OUTPUT_DIR / "pooled_cpr_table.csv",
        pooled_rows,
        fieldnames=list(pooled_rows[0].keys()),
    )

    timeout_rows, timeout_meta = _build_timeout_sensitivity(cells)
    _write_csv(
        OUTPUT_DIR / "timeout_sensitivity_table.csv",
        timeout_rows,
        fieldnames=[
            "method",
            "n_repos_included",
            "n_instances",
            "n_resolved",
            "n_timeouts",
            "resolved_rate_all_in",
            "resolved_rate_timeout_excluded",
            "shift_pp",
        ],
    )

    mcnemar, discordant_rows, discordant_meta = _build_pairwise_outputs(cells)
    (OUTPUT_DIR / "mcnemar_gm_vs_rag.json").write_text(json.dumps(mcnemar, indent=2))
    _write_csv(
        OUTPUT_DIR / "discordant_instances.csv",
        discordant_rows,
        fieldnames=[
            "repo",
            "instance_id",
            "winner",
            "loser",
            "winner_patch_status",
            "loser_patch_status",
            "timeout_confounded",
        ],
    )

    gate = _gate_decision(pooled_rows, timeout_meta, discordant_meta)
    _write_rerun_gate_markdown(
        path=OUTPUT_DIR / "rerun_gate_decision.md",
        gate=gate,
        cells=cells,
    )

    print(f"Wrote v4 analysis artifacts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
