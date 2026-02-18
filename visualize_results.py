#!/usr/bin/env python3
"""
Generate an interactive HTML dashboard comparing retrieval methods.

Usage:
    python visualize_results.py                          # latest run
    python visualize_results.py --run results/runs/20260210_164949
    python visualize_results.py --run results/repeat_sets/20260210_185844.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

METHODS = [
    "gm_deterministic",
    "gm_progressive", "gm_baseline",
    "rag_progressive", "rag_baseline",
    "raw_rag_function", "raw_rag_fixed",
]
METHOD_LABELS = {
    "gm_deterministic": "GM (deterministic)",
    "gm_progressive": "GM (progressive)",
    "gm_baseline": "GM (baseline)",
    "rag_progressive": "RAG (progressive)",
    "rag_baseline": "RAG (baseline)",
    "raw_rag_function": "Raw-RAG (func)",
    "raw_rag_fixed": "Raw-RAG (fixed)",
}
METHOD_COLORS = {
    "gm_deterministic": "#1f7a4a",
    "gm_progressive": "#0b7285",
    "gm_baseline": "#0e9aa7",
    "rag_progressive": "#c2410c",
    "rag_baseline": "#ea580c",
    "raw_rag_function": "#6d28d9",
    "raw_rag_fixed": "#9333ea",
}


def _infer_benchmark(dataset_name: str) -> str:
    name = (dataset_name or "").lower()
    if "polybench" in name:
        return "SWE-PolyBench"
    if "swe-bench" in name:
        return "SWE-bench"
    return "other"


def _infer_domain(repo_name: str, explicit_domain: str | None = None) -> str:
    if explicit_domain:
        return str(explicit_domain)
    repo = (repo_name or "").lower()
    if any(tag in repo for tag in ("flask", "django", "fastapi")):
        return "web_framework"
    if any(tag in repo for tag in ("requests", "httpx", "urllib")):
        return "networking"
    if any(tag in repo for tag in ("pytest", "nose", "tox")):
        return "testing_tooling"
    if any(tag in repo for tag in ("pandas", "keras", "transformers", "langchain", "scikit")):
        return "data_ml"
    if any(tag in repo for tag in ("yt-dlp", "autogpt", "cli")):
        return "app_cli"
    return "library"


def _normalize_method_summary(raw_method_summary: dict[str, Any]) -> dict[str, Any]:
    """Normalize per-method summary values across single runs and repeat aggregates."""
    normalized: dict[str, Any] = {}
    for key, value in (raw_method_summary or {}).items():
        if isinstance(value, dict) and "mean" in value:
            normalized[key] = value.get("mean", 0)
            normalized[f"{key}_std"] = value.get("std", 0)
            normalized[f"{key}_min"] = value.get("min", 0)
            normalized[f"{key}_max"] = value.get("max", 0)
        else:
            normalized[key] = value
    return normalized


def _normalize_summary(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize all method summaries."""
    return {
        method: _normalize_method_summary(summary.get(method, {}))
        for method in METHODS
    }


def _is_dominated(point: dict[str, Any], points: list[dict[str, Any]]) -> bool:
    """Return True when another point has lower/equal cost and higher/equal quality."""
    for candidate in points:
        if candidate is point:
            continue
        better_cost = float(candidate.get("cost_per_issue", float("inf"))) <= float(
            point.get("cost_per_issue", float("inf"))
        )
        better_quality = float(candidate.get("mean_f1", 0.0)) >= float(point.get("mean_f1", 0.0))
        strictly_better = (
            float(candidate.get("cost_per_issue", float("inf"))) < float(
                point.get("cost_per_issue", float("inf"))
            )
            or float(candidate.get("mean_f1", 0.0)) > float(point.get("mean_f1", 0.0))
        )
        if better_cost and better_quality and strictly_better:
            return True
    return False


def build_global_method_points(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build run-level method points for global cost-quality analyses.

    Each point represents one (run, method) tuple.
    """
    points: list[dict[str, Any]] = []
    for run in runs:
        meta = dict(run.get("meta", {}) or {})
        repo_name = str(meta.get("repo_name", "unknown"))
        dataset_name = str(meta.get("dataset_name", "unknown"))
        benchmark = _infer_benchmark(dataset_name)
        domain = _infer_domain(repo_name, meta.get("domain"))
        track = _effective_track(run) or "unknown"
        issue_set_id = str(meta.get("issue_set_id", ""))
        n_issues = int(
            meta.get("n_issues_evaluated")
            or meta.get("n_issues")
            or 0
        )
        for method in METHODS:
            summary = dict(run.get("summary", {}).get(method, {}) or {})
            mean_f1 = float(summary.get("mean_f1", 0.0) or 0.0)
            n_issues_method = int(summary.get("n_issues", 0) or 0)
            denom = n_issues or n_issues_method
            cost_per_issue = summary.get("avg_total_cost_tokens_per_issue_amortized_setup")
            if cost_per_issue is None:
                total_cost = summary.get("total_cost_tokens")
                if total_cost is not None and denom > 0:
                    cost_per_issue = float(total_cost) / float(denom)
            if cost_per_issue is None:
                runtime = float(summary.get("avg_runtime_tokens_per_issue", 0) or 0)
                setup = float(summary.get("setup_embedding_tokens", 0) or 0)
                if denom > 0:
                    cost_per_issue = runtime + (setup / float(denom))
                else:
                    cost_per_issue = runtime + setup
            tokens_per_f1 = (
                float(cost_per_issue) / mean_f1
                if mean_f1 > 0
                else None
            )
            points.append(
                {
                    "run_id": str(run.get("run_id", "")),
                    "method": method,
                    "mean_f1": mean_f1,
                    "cost_per_issue": float(cost_per_issue),
                    "tokens_per_f1": tokens_per_f1,
                    "repo_name": repo_name,
                    "dataset_name": dataset_name,
                    "benchmark": benchmark,
                    "domain": domain,
                    "track": track,
                    "issue_set_id": issue_set_id,
                    "run_type": str(meta.get("run_type", "single")),
                }
            )

    for point in points:
        point["is_pareto_frontier"] = not _is_dominated(point, points)
    return points


def load_run(run_dir: Path) -> dict[str, Any] | None:
    """Load summary + detailed results from a run directory."""
    summary_path = run_dir / "summary.json"
    detailed_path = run_dir / "detailed_results.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text())
    detailed = json.loads(detailed_path.read_text()) if detailed_path.exists() else []
    meta = dict(summary.get("_meta", {}))
    run_id = meta.get("run_id", run_dir.name)
    meta.setdefault("run_id", run_id)
    meta.setdefault("run_type", "single")
    meta.setdefault("benchmark", _infer_benchmark(str(meta.get("dataset_name", ""))))
    meta.setdefault("domain", _infer_domain(str(meta.get("repo_name", "")), meta.get("domain")))
    amortization = dict(summary.get("_amortization", {}) or {})
    if not meta.get("evaluation_track") and amortization.get("track_name"):
        meta["evaluation_track"] = amortization.get("track_name")
    return {
        "run_id": run_id,
        "meta": meta,
        "summary": _normalize_summary(summary),
        "amortization": amortization,
        "issues": detailed,
        "component_run_ids": [run_id],
        "pairwise_deltas": {},
        "gates": {},
    }


def load_repeat_set(repeat_path: Path) -> dict[str, Any] | None:
    """Load one repeat aggregate from results/repeat_sets/*.json.

    Returns None for repeat sets explicitly marked ``valid: false`` (e.g.
    cells that produced empty indices due to a wrong source_prefix).
    """
    if not repeat_path.exists() or repeat_path.suffix != ".json":
        return None
    data = json.loads(repeat_path.read_text())
    if "methods" not in data:
        return None
    if data.get("valid") is False:
        return None

    meta = dict(data.get("_meta", {}))
    run_id = f"repeat_{repeat_path.stem}"
    component_run_ids = [rid for rid in data.get("run_ids", []) if isinstance(rid, str)]
    amortization = dict(data.get("_amortization", {}) or {})
    meta.setdefault("run_id", run_id)
    meta["run_type"] = "repeat_aggregate"
    meta.setdefault("benchmark", _infer_benchmark(str(meta.get("dataset_name", ""))))
    meta.setdefault("domain", _infer_domain(str(meta.get("repo_name", "")), meta.get("domain")))
    meta.setdefault("repeats", data.get("n_runs", len(component_run_ids)))
    meta["aggregate_run_ids"] = component_run_ids
    if not meta.get("evaluation_track") and amortization.get("track_name"):
        meta["evaluation_track"] = amortization.get("track_name")

    return {
        "run_id": run_id,
        "meta": meta,
        "summary": _normalize_summary(data.get("methods", {})),
        "amortization": amortization,
        "issues": [],
        "component_run_ids": component_run_ids,
        "pairwise_deltas": dict(data.get("pairwise_deltas", {}) or {}),
        "gates": dict(data.get("gates", {}) or {}),
    }


def load_all_repeat_sets(results_dir: Path) -> list[dict[str, Any]]:
    """Load all repeat aggregate files under results/repeat_sets/."""
    aggregates: list[dict[str, Any]] = []
    repeat_dir = results_dir / "repeat_sets"
    if not repeat_dir.exists():
        return aggregates
    for path in sorted(repeat_dir.glob("*.json")):
        loaded = load_repeat_set(path)
        if loaded:
            aggregates.append(loaded)
    return aggregates


def _sort_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort runs by creation time then run id."""
    return sorted(
        runs,
        key=lambda run: (
            str(run.get("meta", {}).get("created_at", "")),
            str(run.get("run_id", "")),
        ),
    )


def load_run_path(path: Path) -> dict[str, Any] | None:
    """Load either a single run directory or a repeat aggregate json file."""
    if path.is_dir():
        return load_run(path)
    if path.is_file() and path.suffix == ".json":
        return load_repeat_set(path)
    return None


def _collapse_repeated_single_runs(
    runs: list[dict[str, Any]],
    repeat_aggregates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Hide component single runs when their repeat aggregate is available."""
    covered_run_ids = set()
    for agg in repeat_aggregates:
        for run_id in agg.get("component_run_ids", []):
            covered_run_ids.add(run_id)
    return [
        run for run in runs
        if run.get("run_id") not in covered_run_ids
    ]


def _effective_track(run: dict[str, Any]) -> str:
    meta = run.get("meta", {})
    track = str(meta.get("evaluation_track") or "").strip()
    if track:
        return track
    amortization = run.get("amortization", {})
    return str(amortization.get("track_name") or "").strip()


def _is_stale_run(run: dict[str, Any]) -> bool:
    """Treat runs without explicit evaluation track as stale/legacy artifacts."""
    return not _effective_track(run)


def _run_recency_key(run: dict[str, Any]) -> tuple[str, str]:
    meta = run.get("meta", {})
    return (
        str(meta.get("created_at", "")),
        str(run.get("run_id", "")),
    )


def _collapse_superseded_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the newest run for each comparable config key."""
    latest_by_key: dict[tuple, dict[str, Any]] = {}
    for run in runs:
        meta = run.get("meta", {})
        key = (
            str(meta.get("run_type", "")),
            str(meta.get("repo_name", "")),
            str(meta.get("dataset_name", "")),
            str(meta.get("issue_set_id", "")),
            _effective_track(run),
            str(meta.get("snapshot_commit", "")),
            int(meta.get("n_issues_evaluated", 0) or 0),
            tuple(meta.get("source_prefixes", []) or []),
        )
        existing = latest_by_key.get(key)
        if existing is None or _run_recency_key(run) > _run_recency_key(existing):
            latest_by_key[key] = run
    return list(latest_by_key.values())


def load_all_runs(results_dir: Path, include_stale: bool = False) -> list[dict[str, Any]]:
    """Load visible runs, preferring repeat aggregates and excluding stale by default."""
    runs: list[dict[str, Any]] = []
    runs_dir = results_dir / "runs"
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir()):
            if d.is_dir() and d.name[:1].isdigit():
                run = load_run(d)
                if run:
                    runs.append(run)
    repeat_aggregates = load_all_repeat_sets(results_dir)
    collapsed_runs = _collapse_repeated_single_runs(runs, repeat_aggregates)
    visible_runs = collapsed_runs + repeat_aggregates
    if not include_stale:
        visible_runs = [run for run in visible_runs if not _is_stale_run(run)]
    visible_runs = _collapse_superseded_runs(visible_runs)
    return _sort_runs(visible_runs)


def load_experiment_config(results_dir: Path) -> dict[str, Any] | None:
    """Load experiment_config.yaml if present."""
    for name in ["experiment_config.yaml", "experiment_config.yml"]:
        path = results_dir / name
        if path.exists():
            import yaml
            return yaml.safe_load(path.read_text())
    return None


def build_html(runs: list[dict[str, Any]], config: dict[str, Any] | None = None) -> str:
    """Build a self-contained HTML dashboard."""
    global_points = build_global_method_points(runs)
    data = json.dumps({
        "runs": runs,
        "global_points": global_points,
        "methods": METHODS,
        "labels": METHOD_LABELS,
        "colors": METHOD_COLORS,
        "config": config,
    })

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>GraphManager Results</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root {{
  --bg: #f8fafc; --surface: #fff; --ink: #0f172a; --muted: #64748b;
  --border: #e2e8f0; --accent: #0b7285; --accent2: #c2410c;
  --hit: #059669; --miss: #dc2626; --radius: 10px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: "Inter","Segoe UI",system-ui,sans-serif; color: var(--ink); background: var(--bg); }}
.wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px; }}
header {{ margin-bottom: 24px; }}
header h1 {{ font-size: 1.5rem; font-weight: 700; }}
header p {{ color: var(--muted); margin-top: 4px; font-size: 0.9rem; }}
.controls {{ display: flex; gap: 12px; align-items: center; margin: 16px 0; flex-wrap: wrap; }}
.controls label {{ font-size: 0.85rem; color: var(--muted); }}
.controls select {{ border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.9rem; min-width: 300px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }}
.card h2 {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 14px; }}
.grid {{ display: grid; gap: 16px; }}
.grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
.grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }}
.kpi {{ text-align: center; padding: 16px 12px; }}
.kpi .value {{ font-size: 1.6rem; font-weight: 700; margin: 6px 0 2px; }}
.kpi .label {{ font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
.kpi .sub {{ font-size: 0.82rem; color: var(--muted); }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
th, td {{ padding: 10px 8px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.3px; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
th.num {{ text-align: right; }}
tr:hover {{ background: #f8fafc; }}
.winner {{ font-weight: 700; color: var(--accent); }}
.f1-bar {{ display: inline-block; height: 8px; border-radius: 4px; vertical-align: middle; margin-right: 6px; }}

/* File tags */
.file-list {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }}
.file-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem; font-family: "JetBrains Mono",monospace; }}
.file-tag.hit {{ background: #d1fae5; color: #065f46; }}
.file-tag.miss {{ background: #fee2e2; color: #991b1b; }}
.file-tag.gold {{ background: #e0e7ff; color: #3730a3; }}

/* Expandable rows */
.expand-btn {{ cursor: pointer; user-select: none; color: var(--accent); font-size: 0.85rem; }}
.expand-btn:hover {{ text-decoration: underline; }}
.detail-row td {{ padding: 12px 8px; background: #f8fafc; }}
.detail-row.hidden {{ display: none; }}
.method-detail {{ margin-bottom: 10px; }}
.method-detail .name {{ font-weight: 600; font-size: 0.85rem; margin-bottom: 4px; }}
.method-detail .stats {{ font-size: 0.82rem; color: var(--muted); }}

/* Meta grid */
.meta-grid {{ display: grid; grid-template-columns: 160px 1fr; gap: 4px 12px; font-size: 0.88rem; }}
.meta-grid .k {{ color: var(--muted); }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
.badge.ok {{ background: #dcfce7; color: #166534; }}
.badge.warn {{ background: #fef9c3; color: #854d0e; }}
.badge.fail {{ background: #fee2e2; color: #991b1b; }}
.mini-list {{ display: grid; gap: 6px; font-size: 0.86rem; }}
.mini-list .row {{ display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px dashed var(--border); padding-bottom: 4px; }}
.mini-list .name {{ color: var(--muted); }}
.mono {{ font-family: "JetBrains Mono","Consolas","Menlo",monospace; font-size: 0.82rem; }}

/* Chart containers */
.chart-box {{ position: relative; height: 300px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Graph-Augmented Manager &mdash; Experiment Results</h1>
    <p>Cross-benchmark retrieval evidence with global cost-quality tradeoff analysis</p>
  </header>

  <div id="configBanner" class="card" style="display:none;margin-bottom:16px;">
    <h2 id="configTitle"></h2>
    <p id="configDesc" style="color:var(--muted);font-size:0.9rem;"></p>
  </div>

  <div class="controls">
    <label for="benchmarkFilter">Benchmark:</label>
    <select id="benchmarkFilter"><option value="all">All benchmarks</option></select>
    <label for="domainFilter">Domain:</label>
    <select id="domainFilter"><option value="all">All domains</option></select>
    <label for="trackFilter">Track:</label>
    <select id="trackFilter"><option value="all">All tracks</option></select>
    <label for="repoFilter">Repo:</label>
    <select id="repoFilter"><option value="all">All repos</option></select>
    <label for="runSelect">Run:</label>
    <select id="runSelect"></select>
  </div>

  <div class="grid grid-2">
    <div class="card">
      <h2>Global Cost-Quality Frontier</h2>
      <div class="chart-box" style="height:340px;"><canvas id="globalFrontierChart"></canvas></div>
    </div>
    <div class="card">
      <h2>Tradeoff Outliers</h2>
      <table>
        <thead>
          <tr>
            <th>Benchmark</th>
            <th>Repo</th>
            <th>Method</th>
            <th class="num">Mean F1</th>
            <th class="num">Cost / Issue</th>
            <th class="num">Tokens / F1</th>
          </tr>
        </thead>
        <tbody id="outlierBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>Regime Shift Detector</h2>
    <table>
      <thead>
        <tr>
          <th>Repo</th>
          <th>Method</th>
          <th class="num">&Delta; F1 (snapshot - strict)</th>
          <th class="num">&Delta; Cost / Issue</th>
          <th>Issue Set</th>
        </tr>
      </thead>
      <tbody id="regimeBody"></tbody>
    </table>
  </div>

  <!-- KPI cards -->
  <div class="grid grid-4" id="kpis"></div>

  <div class="grid grid-2">
    <div class="card">
      <h2>Amortization & Track</h2>
      <div id="amortizationCard" class="mini-list"></div>
    </div>
    <div class="card">
      <h2>Repeat CI & Gates</h2>
      <div id="ciCard" class="mini-list"></div>
    </div>
  </div>

  <div class="card">
    <h2>Manager Telemetry</h2>
    <div id="telemetryCard" class="mini-list"></div>
  </div>

  <div class="card">
    <h2>Method Error Counts</h2>
    <table>
      <thead>
        <tr>
          <th>Method</th>
          <th class="num">Errors</th>
          <th class="num">Error Rate</th>
        </tr>
      </thead>
      <tbody id="errorBody"></tbody>
    </table>
  </div>

  <!-- Charts row -->
  <div class="grid grid-2">
    <div class="card">
      <h2>Retrieval Quality (per method)</h2>
      <div class="chart-box"><canvas id="qualityChart"></canvas></div>
    </div>
    <div class="card">
      <h2>Token Cost Breakdown</h2>
      <div class="chart-box"><canvas id="costChart"></canvas></div>
    </div>
  </div>

  <!-- Per-issue table -->
  <div class="card">
    <h2>Per-Issue Results</h2>
    <table id="issueTable">
      <thead>
        <tr>
          <th style="width:28px"></th>
          <th>Issue</th>
          <th>Gold</th>
          <th class="num">GM(d)</th>
          <th class="num">GM(p)</th>
          <th class="num">GM(b)</th>
          <th class="num">RAG(p)</th>
          <th class="num">RAG(b)</th>
          <th class="num">Raw-F</th>
          <th class="num">Raw-X</th>
          <th>Best</th>
        </tr>
      </thead>
      <tbody id="issueBody"></tbody>
    </table>
  </div>

  <!-- Aggregate comparison across runs -->
  <div class="card" id="crossRunCard" style="display:none;">
    <h2>Cross-Run Comparison</h2>
    <table id="crossRunTable">
      <thead>
        <tr>
          <th>Benchmark</th>
          <th>Domain</th>
          <th>Track</th>
          <th>Repo</th>
          <th class="num">n</th>
          <th class="num">GM(d)</th>
          <th class="num">GM(p)</th>
          <th class="num">GM(b)</th>
          <th class="num">RAG(p)</th>
          <th class="num">RAG(b)</th>
          <th class="num">Raw-F</th>
          <th class="num">Raw-X</th>
        </tr>
      </thead>
      <tbody id="crossRunBody"></tbody>
    </table>
  </div>

  <!-- Run metadata -->
  <div class="card">
    <h2>Run Configuration</h2>
    <div id="metaGrid" class="meta-grid"></div>
  </div>
</div>

<script>
const D = {data};
const METHODS = D.methods;
const LABELS = D.labels;
const COLORS = D.colors;

let qualityChart = null, costChart = null, globalFrontierChart = null;

// --- Config banner ---
if (D.config) {{
  const banner = document.getElementById("configBanner");
  banner.style.display = "";
  document.getElementById("configTitle").textContent = D.config.suite || "Experiment Suite";
  document.getElementById("configDesc").textContent = (D.config.description || "").trim();
}}

// --- Global filters ---
const benchmarkFilter = document.getElementById("benchmarkFilter");
const domainFilter = document.getElementById("domainFilter");
const trackFilter = document.getElementById("trackFilter");
const repoFilter = document.getElementById("repoFilter");
const runSel = document.getElementById("runSelect");

function populateFilter(selectEl, values) {{
  for (const value of values) {{
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    selectEl.appendChild(opt);
  }}
}}

populateFilter(
  benchmarkFilter,
  [...new Set(D.runs.map(r => r.meta.benchmark || "other"))].sort(),
);
populateFilter(
  domainFilter,
  [...new Set(D.runs.map(r => r.meta.domain || "library"))].sort(),
);
populateFilter(
  trackFilter,
  [...new Set(D.runs.map(r => r.meta.evaluation_track || r.amortization?.track_name || "unknown"))].sort(),
);
populateFilter(
  repoFilter,
  [...new Set(D.runs.map(r => r.meta.repo_name || "?"))].sort(),
);

function runMatchesFilters(run) {{
  const m = run.meta || {{}};
  const benchmark = m.benchmark || "other";
  const domain = m.domain || "library";
  const track = m.evaluation_track || run.amortization?.track_name || "unknown";
  const repo = m.repo_name || "?";
  if (benchmarkFilter.value !== "all" && benchmark !== benchmarkFilter.value) return false;
  if (domainFilter.value !== "all" && domain !== domainFilter.value) return false;
  if (trackFilter.value !== "all" && track !== trackFilter.value) return false;
  if (repoFilter.value !== "all" && repo !== repoFilter.value) return false;
  return true;
}}

function filteredRuns() {{
  return D.runs.filter(runMatchesFilters);
}}

function filteredGlobalPoints() {{
  return (D.global_points || []).filter(point => {{
    if (benchmarkFilter.value !== "all" && point.benchmark !== benchmarkFilter.value) return false;
    if (domainFilter.value !== "all" && point.domain !== domainFilter.value) return false;
    if (trackFilter.value !== "all" && point.track !== trackFilter.value) return false;
    if (repoFilter.value !== "all" && point.repo_name !== repoFilter.value) return false;
    return true;
  }});
}}

function rebuildRunSelect() {{
  const prev = runSel.value;
  const runs = filteredRuns();
  runSel.innerHTML = "";
  for (const run of runs) {{
    const opt = document.createElement("option");
    const m = run.meta || {{}};
    const runType = m.run_type === "repeat_aggregate"
      ? `repeat-agg x${{m.repeats || run.component_run_ids?.length || "?"}}`
      : "single";
    opt.value = run.run_id;
    opt.textContent = `${{m.repo_name || "?"}} | ${{m.benchmark || "other"}} | n=${{m.n_issues_evaluated || "?"}} | ${{runType}}`;
    runSel.appendChild(opt);
  }}
  const ids = runs.map(r => r.run_id);
  if (ids.includes(prev)) runSel.value = prev;
  else if (ids.length) runSel.value = ids[ids.length - 1];
}}

for (const filterEl of [benchmarkFilter, domainFilter, trackFilter, repoFilter]) {{
  filterEl.addEventListener("change", () => {{
    rebuildRunSelect();
    buildCrossRunTable();
    render();
  }});
}}
rebuildRunSelect();

// --- Cross-run table ---
function buildCrossRunTable() {{
  const runs = filteredRuns();
  const card = document.getElementById("crossRunCard");
  const tbody = document.getElementById("crossRunBody");
  tbody.innerHTML = "";
  if (runs.length < 2) {{ card.style.display = "none"; return; }}
  card.style.display = "";

  for (const run of runs) {{
    const m = run.meta;
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => {{ runSel.value = run.run_id; render(); }});
    tr.innerHTML = `
      <td>${{m.benchmark || "other"}}</td>
      <td>${{m.domain || "library"}}</td>
      <td class="mono">${{m.evaluation_track || run.amortization?.track_name || "unknown"}}</td>
      <td><strong>${{m.repo_name || "?"}}</strong></td>
      <td class="num">${{m.n_issues_evaluated || "?"}}</td>
      ${{METHODS.map(method => `<td class="num">${{fmt3((run.summary[method] || {{}}).mean_f1)}}</td>`).join("")}}
    `;
    tbody.appendChild(tr);
  }}
}}
buildCrossRunTable();

// --- Helpers ---
function fmt3(v) {{ return (v || 0).toFixed(3); }}
function fmtK(v) {{ const n = Number(v || 0); return n >= 1000 ? (n / 1000).toFixed(1) + "k" : Math.round(n).toLocaleString(); }}
function fmtN(v) {{ return Math.round(Number(v || 0)).toLocaleString(); }}
function fmtPct(v) {{ return ((Number(v || 0)) * 100).toFixed(1) + "%"; }}

function getRun(id) {{ return D.runs.find(r => r.run_id === id); }}

function bestMethod(issue) {{
  let best = "", bestF1 = -1;
  for (const m of METHODS) {{
    const f1 = issue.methods?.[m]?.metrics?.f1 ?? -1;
    if (f1 > bestF1) {{ bestF1 = f1; best = m; }}
  }}
  return best;
}}

function renderGlobalFrontier() {{
  const ctx = document.getElementById("globalFrontierChart");
  if (!ctx) return;
  if (globalFrontierChart) globalFrontierChart.destroy();
  const points = filteredGlobalPoints();

  const datasets = METHODS.map(method => {{
    const methodPoints = points
      .filter(point => point.method === method)
      .map(point => ({{
        x: Number(point.cost_per_issue || 0),
        y: Number(point.mean_f1 || 0),
        label: `${{point.repo_name}} :: ${{point.run_id}}`,
        benchmark: point.benchmark,
        domain: point.domain,
        track: point.track,
        isFrontier: !!point.is_pareto_frontier,
      }}));
    return {{
      label: LABELS[method],
      data: methodPoints,
      backgroundColor: COLORS[method] + "cc",
      pointRadius: (ctx) => ctx.raw?.isFrontier ? 7 : 5,
      pointHoverRadius: 8,
      pointBorderColor: (ctx) => ctx.raw?.isFrontier ? "#0f172a" : "transparent",
      pointBorderWidth: (ctx) => ctx.raw?.isFrontier ? 1.5 : 0,
    }};
  }});

  globalFrontierChart = new Chart(ctx, {{
    type: "scatter",
    data: {{ datasets }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {{
        x: {{ title: {{ display: true, text: "Cost tokens per issue (amortized)" }} }},
        y: {{ title: {{ display: true, text: "Mean F1" }}, min: 0, max: 1.05 }},
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: (ctx) => {{
              const raw = ctx.raw || {{}};
              const frontier = raw.isFrontier ? " | frontier" : "";
              return `${{ctx.dataset.label}} | ${{raw.label}} | F1=${{raw.y.toFixed(3)}} | cost=${{Math.round(raw.x).toLocaleString()}}${{frontier}}`;
            }},
          }},
        }},
      }},
    }},
  }});
}}

function renderOutlierTable() {{
  const tbody = document.getElementById("outlierBody");
  const points = filteredGlobalPoints()
    .filter(point => point.tokens_per_f1 != null)
    .sort((a, b) => Number(b.tokens_per_f1) - Number(a.tokens_per_f1))
    .slice(0, 10);
  tbody.innerHTML = "";
  if (!points.length) {{
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" style="color:var(--muted);">No data for current filters.</td>';
    tbody.appendChild(tr);
    return;
  }}
  for (const point of points) {{
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${{point.benchmark}}</td>
      <td>${{point.repo_name}}</td>
      <td>${{LABELS[point.method] || point.method}}</td>
      <td class="num">${{fmt3(point.mean_f1)}}</td>
      <td class="num">${{fmtN(point.cost_per_issue)}}</td>
      <td class="num">${{fmtN(point.tokens_per_f1)}}</td>
    `;
    tbody.appendChild(tr);
  }}
}}

function renderRegimeShiftTable() {{
  const tbody = document.getElementById("regimeBody");
  const points = filteredGlobalPoints();
  const byKey = {{}};
  for (const point of points) {{
    const key = [
      point.repo_name,
      point.dataset_name,
      point.issue_set_id,
      point.method,
    ].join("::");
    byKey[key] = byKey[key] || {{}};
    byKey[key][point.track] = point;
  }}
  const rows = [];
  for (const cell of Object.values(byKey)) {{
    const strictPoint = cell["strict_commit_fidelity"];
    const snapshotPoint = cell["same_snapshot_amortized"];
    if (!strictPoint || !snapshotPoint) continue;
    rows.push({{
      repo_name: strictPoint.repo_name,
      method: strictPoint.method,
      issue_set_id: strictPoint.issue_set_id || "\u2014",
      delta_f1: Number(snapshotPoint.mean_f1 || 0) - Number(strictPoint.mean_f1 || 0),
      delta_cost: Number(snapshotPoint.cost_per_issue || 0) - Number(strictPoint.cost_per_issue || 0),
    }});
  }}

  rows.sort((a, b) => Math.abs(b.delta_f1) - Math.abs(a.delta_f1));
  tbody.innerHTML = "";
  if (!rows.length) {{
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5" style="color:var(--muted);">No strict/snapshot matched cells for current filters.</td>';
    tbody.appendChild(tr);
    return;
  }}
  for (const row of rows.slice(0, 20)) {{
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${{row.repo_name}}</td>
      <td>${{LABELS[row.method] || row.method}}</td>
      <td class="num">${{fmt3(row.delta_f1)}}</td>
      <td class="num">${{fmtN(row.delta_cost)}}</td>
      <td class="mono">${{row.issue_set_id}}</td>
    `;
    tbody.appendChild(tr);
  }}
}}

// --- Render ---
function render() {{
  renderGlobalFrontier();
  renderOutlierTable();
  renderRegimeShiftTable();
  const run = getRun(runSel.value);
  if (!run) {{
    document.getElementById("kpis").innerHTML = "";
    document.getElementById("amortizationCard").innerHTML = "";
    document.getElementById("ciCard").innerHTML = "";
    document.getElementById("telemetryCard").innerHTML = "";
    document.getElementById("errorBody").innerHTML = "";
    document.getElementById("issueBody").innerHTML = "";
    document.getElementById("metaGrid").innerHTML = "";
    return;
  }}
  renderKPIs(run);
  renderAmortizationCard(run);
  renderRepeatCiCard(run);
  renderTelemetryCard(run);
  renderErrorTable(run);
  renderQualityChart(run);
  renderCostChart(run);
  renderIssueTable(run);
  renderMeta(run);
}}

function renderKPIs(run) {{
  const s = run.summary;
  const n = run.meta.n_issues_evaluated || 0;
  const gmp = s.gm_progressive || {{}};
  const gmb = s.gm_baseline || {{}};
  const ragp = s.rag_progressive || {{}};
  const ragb = s.rag_baseline || {{}};

  // Find best F1 method
  let bestM = "", bestF1 = -1;
  for (const m of METHODS) {{
    const f1 = s[m]?.mean_f1 ?? 0;
    if (f1 > bestF1) {{ bestF1 = f1; bestM = m; }}
  }}

  document.getElementById("kpis").innerHTML = `
    <div class="card kpi">
      <div class="label">Best F1</div>
      <div class="value">${{fmt3(bestF1)}}</div>
      <div class="sub">${{LABELS[bestM]}}</div>
    </div>
    <div class="card kpi">
      <div class="label">GM F1 (p / b)</div>
      <div class="value">${{fmt3(gmp.mean_f1)}} / ${{fmt3(gmb.mean_f1)}}</div>
      <div class="sub">&Delta; ${{(((gmp.mean_f1 || 0) - (gmb.mean_f1 || 0)) * 100).toFixed(1)}}%</div>
    </div>
    <div class="card kpi">
      <div class="label">RAG F1 (p / b)</div>
      <div class="value">${{fmt3(ragp.mean_f1)}} / ${{fmt3(ragb.mean_f1)}}</div>
      <div class="sub">&Delta; ${{(((ragp.mean_f1 || 0) - (ragb.mean_f1 || 0)) * 100).toFixed(1)}}%</div>
    </div>
    <div class="card kpi">
      <div class="label">Issues Evaluated</div>
      <div class="value">${{n}}</div>
      <div class="sub">${{run.meta.repo_name || "?"}}</div>
    </div>
  `;
}}

function renderAmortizationCard(run) {{
  const el = document.getElementById("amortizationCard");
  const amort = run.amortization || {{}};
  const track = amort.track_name || run.meta.evaluation_track || "unknown";
  const repeatRatio = amort.commit_repeat_ratio != null ? fmtPct(amort.commit_repeat_ratio) : "\u2014";
  const cacheHitRate = amort.cache_hit_rate != null ? fmtPct(amort.cache_hit_rate) : "\u2014";
  const nIssues = amort.n_issues != null ? fmtN(amort.n_issues) : (run.meta.n_issues_evaluated || "\u2014");
  const nCommits = amort.n_unique_commits != null ? fmtN(amort.n_unique_commits) : "\u2014";
  const snapshot = run.meta.snapshot_commit || "\u2014";

  el.innerHTML = `
    <div class="row"><span class="name">Track</span><span class="mono">${{track}}</span></div>
    <div class="row"><span class="name">Snapshot commit</span><span class="mono">${{snapshot}}</span></div>
    <div class="row"><span class="name">Issues</span><span>${{nIssues}}</span></div>
    <div class="row"><span class="name">Unique commits</span><span>${{nCommits}}</span></div>
    <div class="row"><span class="name">Commit repeat ratio</span><span>${{repeatRatio}}</span></div>
    <div class="row"><span class="name">Cache hit rate</span><span>${{cacheHitRate}}</span></div>
  `;
}}

function renderRepeatCiCard(run) {{
  const el = document.getElementById("ciCard");
  const gates = run.gates || {{}};
  const pairwise = run.pairwise_deltas || {{}};
  const key = "gm_progressive__minus__rag_progressive__mean_f1";
  const delta = pairwise[key];
  const gateBadge = (value) => value
    ? `<span class="badge ok">pass</span>`
    : `<span class="badge warn">pending</span>`;

  let deltaHtml = '<div class="row"><span class="name">GM(p) - RAG(p) mean F1</span><span>\u2014</span></div>';
  if (delta) {{
    const ci = Array.isArray(delta.bootstrap_ci_95) ? delta.bootstrap_ci_95 : [0, 0];
    deltaHtml = `
      <div class="row"><span class="name">GM(p) - RAG(p) mean F1</span><span>${{fmt3(delta.mean_delta)}}</span></div>
      <div class="row"><span class="name">Bootstrap 95% CI</span><span>[${{fmt3(ci[0])}}, ${{fmt3(ci[1])}}]</span></div>
      <div class="row"><span class="name">Paired runs</span><span>${{fmtN(delta.n_runs || 0)}}</span></div>
    `;
  }}

  el.innerHTML = `
    <div class="row"><span class="name">Min repeats (>=3)</span><span>${{gateBadge(!!gates.min_repeats_met)}}</span></div>
    <div class="row"><span class="name">Pairwise bootstrap</span><span>${{gateBadge(!!gates.pairwise_bootstrap_available)}}</span></div>
    <div class="row"><span class="name">CI ready</span><span>${{gateBadge(!!gates.ci_ready)}}</span></div>
    ${{deltaHtml}}
  `;
}}

function renderTelemetryCard(run) {{
  const el = document.getElementById("telemetryCard");
  const issues = run.issues || [];
  if (!issues.length) {{
    el.innerHTML = '<div class="row"><span class="name">Status</span><span>No per-issue telemetry for this run selection.</span></div>';
    return;
  }}
  const methods = ["gm_progressive", "gm_baseline"];
  const lines = [];
  for (const method of methods) {{
    let toolCalls = 0;
    let cacheHits = 0;
    const stopReasons = {{}};
    const byTool = {{}};
    for (const issue of issues) {{
      const tokens = issue.methods?.[method]?.tokens || {{}};
      const tel = tokens.manager_telemetry || {{}};
      toolCalls += Number(tel.tool_calls || tokens.tool_calls || 0);
      cacheHits += Number(tel.tool_cache_hits || tokens.tool_cache_hits || 0);
      const stopReason = String(tel.stop_reason || tokens.stop_reason || "").trim();
      if (stopReason) stopReasons[stopReason] = (stopReasons[stopReason] || 0) + 1;
      const callsByName = tel.tool_calls_by_name || tokens.tool_calls_by_name || {{}};
      for (const [k, v] of Object.entries(callsByName)) {{
        byTool[k] = (byTool[k] || 0) + Number(v || 0);
      }}
    }}
    const topTool = Object.entries(byTool).sort((a, b) => b[1] - a[1])[0];
    const topStop = Object.entries(stopReasons).sort((a, b) => b[1] - a[1])[0];
    lines.push(`
      <div class="row"><span class="name">${{LABELS[method]}} tool calls</span><span>${{fmtN(toolCalls)}} (cache hits: ${{fmtN(cacheHits)}})</span></div>
      <div class="row"><span class="name">${{LABELS[method]}} top tool</span><span>${{topTool ? `${{topTool[0]}}:${{fmtN(topTool[1])}}` : "\u2014"}}</span></div>
      <div class="row"><span class="name">${{LABELS[method]}} top stop reason</span><span>${{topStop ? `${{topStop[0]}}:${{fmtN(topStop[1])}}` : "\u2014"}}</span></div>
    `);
  }}
  el.innerHTML = lines.join("");
}}

function renderErrorTable(run) {{
  const tbody = document.getElementById("errorBody");
  tbody.innerHTML = "";
  for (const m of METHODS) {{
    const summary = run.summary[m] || {{}};
    const nErrors = summary.n_errors || 0;
    const errRate = summary.error_rate != null
      ? summary.error_rate
      : ((run.meta.n_issues_evaluated || 0) > 0 ? nErrors / run.meta.n_issues_evaluated : 0);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${{LABELS[m]}}</td>
      <td class="num">${{Number(nErrors).toFixed(2)}}</td>
      <td class="num">${{(errRate * 100).toFixed(1)}}%</td>
    `;
    tbody.appendChild(tr);
  }}
}}

function renderQualityChart(run) {{
  const ctx = document.getElementById("qualityChart");
  if (qualityChart) qualityChart.destroy();

  const labels = METHODS.map(m => LABELS[m]);
  const precisions = METHODS.map(m => run.summary[m]?.mean_precision || 0);
  const recalls = METHODS.map(m => run.summary[m]?.mean_recall || 0);
  const f1s = METHODS.map(m => run.summary[m]?.mean_f1 || 0);

  qualityChart = new Chart(ctx, {{
    type: "bar",
    data: {{
      labels,
      datasets: [
        {{ label: "Precision", data: precisions, backgroundColor: "#0b7285cc" }},
        {{ label: "Recall", data: recalls, backgroundColor: "#0891b2cc" }},
        {{ label: "F1", data: f1s, backgroundColor: "#06b6d4cc" }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ y: {{ beginAtZero: true, max: 1, title: {{ display: true, text: "Score" }} }} }},
      plugins: {{ legend: {{ position: "top" }} }},
    }},
  }});
}}

function renderCostChart(run) {{
  const ctx = document.getElementById("costChart");
  if (costChart) costChart.destroy();

  const labels = METHODS.map(m => LABELS[m]);
  const setup = METHODS.map(m => run.summary[m]?.setup_embedding_tokens || 0);
  const llm = METHODS.map(m => run.summary[m]?.total_llm_tokens || 0);
  const queryEmbed = METHODS.map(m => run.summary[m]?.total_query_embedding_tokens || 0);

  costChart = new Chart(ctx, {{
    type: "bar",
    data: {{
      labels,
      datasets: [
        {{ label: "Setup (embedding)", data: setup, backgroundColor: "#6366f1cc" }},
        {{ label: "LLM (per-issue total)", data: llm, backgroundColor: "#f59e0bcc" }},
        {{ label: "Query embedding", data: queryEmbed, backgroundColor: "#a78bfacc" }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, title: {{ display: true, text: "Tokens" }} }} }},
      plugins: {{ legend: {{ position: "top" }} }},
    }},
  }});
}}

function renderScatterChart(run) {{
  const ctx = document.getElementById("scatterChart");
  if (scatterChart) scatterChart.destroy();

  const agenticMethods = ["gm_progressive", "gm_baseline", "rag_progressive", "rag_baseline"];
  const datasets = [];
  for (const m of agenticMethods) {{
    const points = [];
    for (const issue of (run.issues || [])) {{
      const md = issue.methods?.[m];
      if (!md || md.error) continue;
      points.push({{
        x: md.tokens?.total_tokens || 0,
        y: md.metrics?.f1 || 0,
        label: issue.instance_id,
      }});
    }}
    datasets.push({{
      label: LABELS[m],
      data: points,
      backgroundColor: COLORS[m] + "cc",
      pointRadius: 5,
      pointHoverRadius: 8,
    }});
  }}

  scatterChart = new Chart(ctx, {{
    type: "scatter",
    data: {{ datasets }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      parsing: false,
      scales: {{
        x: {{ title: {{ display: true, text: "LLM tokens (per issue)" }} }},
        y: {{ title: {{ display: true, text: "F1 score" }}, min: 0, max: 1.05 }},
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: (ctx) => `${{ctx.dataset.label}} | ${{ctx.raw.label}}: F1=${{ctx.raw.y.toFixed(3)}}, tok=${{Math.round(ctx.raw.x).toLocaleString()}}`,
          }},
        }},
      }},
    }},
  }});
}}

function renderIssueTable(run) {{
  const tbody = document.getElementById("issueBody");
  tbody.innerHTML = "";
  if (!(run.issues || []).length) {{
    const tr = document.createElement("tr");
    const runType = run.meta?.run_type;
    const msg = runType === "repeat_aggregate"
      ? "Repeat aggregate selected. Per-issue rows are shown in component runs only."
      : "No per-issue data found for this run.";
    tr.innerHTML = `<td colspan="11" style="color:var(--muted);">${{msg}}</td>`;
    tbody.appendChild(tr);
    return;
  }}

  for (const issue of (run.issues || [])) {{
    const best = bestMethod(issue);
    const goldStr = (issue.gold_files || []).map(f => f.split("/").pop()).join(", ");

    // Summary row
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="expand-btn" data-id="${{issue.instance_id}}">+</span></td>
      <td>${{issue.instance_id}}</td>
      <td style="font-family:monospace;font-size:0.82rem;">${{goldStr}}</td>
      ${{METHODS.map(m => {{
        const md = issue.methods?.[m];
        const hasError = !!md?.error;
        const f1 = md?.metrics?.f1;
        const cls = m === best ? ' class="num winner"' : ' class="num"';
        const bar = f1 != null ? `<span class="f1-bar" style="width:${{Math.round((f1||0)*40)}}px;background:${{COLORS[m]}}"></span>` : "";
        return `<td${{cls}}>${{hasError ? "err" : (f1 != null ? bar + f1.toFixed(3) : "err")}}</td>`;
      }}).join("")}}
      <td>${{LABELS[best] || "?"}}</td>
    `;
    tbody.appendChild(tr);

    // Detail row (hidden)
    const detailTr = document.createElement("tr");
    detailTr.className = "detail-row hidden";
    detailTr.id = `detail-${{issue.instance_id}}`;

    let detailHtml = '<td colspan="11">';
    detailHtml += `<div style="margin-bottom:8px;"><strong>Gold files:</strong> <span class="file-list" style="display:inline-flex;">`;
    for (const f of (issue.gold_files || [])) {{
      detailHtml += `<span class="file-tag gold">${{f}}</span>`;
    }}
    detailHtml += `</span></div>`;

    for (const m of METHODS) {{
      const md = issue.methods?.[m];
      if (!md || md.error) {{
        const msg = md?.error ? String(md.error) : "Unknown error";
        detailHtml += `<div class="method-detail"><div class="name">${{LABELS[m]}}</div><div class="stats">Error: ${{msg}}</div></div>`;
        continue;
      }}
      const goldSet = new Set(issue.gold_files || []);
      const predicted = md.predicted_files || [];
      const metrics = md.metrics || {{}};
      const tokens = md.tokens || {{}};

      detailHtml += `<div class="method-detail">`;
      detailHtml += `<div class="name">${{LABELS[m]}}</div>`;
      detailHtml += `<div class="stats">P=${{(metrics.precision||0).toFixed(3)}} R=${{(metrics.recall||0).toFixed(3)}} F1=${{(metrics.f1||0).toFixed(3)}}`;
      if (tokens.total_tokens) detailHtml += ` | ${{fmtN(tokens.total_tokens)}} tok (${{tokens.tool_calls||0}} calls)`;
      detailHtml += `</div>`;
      detailHtml += `<div class="file-list">`;
      for (const f of predicted) {{
        const isHit = goldSet.has(f);
        detailHtml += `<span class="file-tag ${{isHit ? 'hit' : 'miss'}}">${{f.split("/").pop()}}</span>`;
      }}
      // Show missed gold files
      for (const f of (issue.gold_files || [])) {{
        if (!predicted.includes(f)) {{
          detailHtml += `<span class="file-tag gold" style="opacity:0.5;text-decoration:line-through;">${{f.split("/").pop()}}</span>`;
        }}
      }}
      detailHtml += `</div></div>`;
    }}
    detailHtml += "</td>";
    detailTr.innerHTML = detailHtml;
    tbody.appendChild(detailTr);
  }}

  // Toggle expand/collapse
  tbody.querySelectorAll(".expand-btn").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const id = btn.dataset.id;
      const row = document.getElementById(`detail-${{id}}`);
      const hidden = row.classList.toggle("hidden");
      btn.textContent = hidden ? "+" : "\u2212";
    }});
  }});
}}

function renderMeta(run) {{
  const m = run.meta;
  const aggregateRunIds = m.aggregate_run_ids || run.component_run_ids || [];
  const gates = run.gates || {{}};
  const rows = [
    ["Run ID", m.run_id || run.run_id],
    ["Run type", m.run_type || "single"],
    ["Repeats", m.repeats || (m.run_type === "repeat_aggregate" ? aggregateRunIds.length : 1)],
    ["Created", m.created_at || "?"],
    ["Benchmark", m.benchmark || "?"],
    ["Domain", m.domain || "?"],
    ["Repository", m.repo_name || "?"],
    ["Dataset", m.dataset_name || "?"],
    ["Issue set ID", m.issue_set_id || "\u2014"],
    ["Evaluation track", m.evaluation_track || run.amortization?.track_name || "?"],
    ["Snapshot commit", m.snapshot_commit || "\u2014"],
    ["Issues evaluated", m.n_issues_evaluated || "?"],
    ["Manager max turns", m.manager_max_turns || "?"],
    ["RAG max turns", m.rag_max_turns || "?"],
    ["Repeat CI ready", gates.ci_ready == null ? "\u2014" : (gates.ci_ready ? "yes" : "no")],
    ["Source prefixes", (m.source_prefixes || []).join(", ") || "?"],
    ["LLM model", m.model || m.manager_model || "?"],
    ["Aggregate run IDs", aggregateRunIds.join(", ") || "\u2014"],
    ["Notes", m.notes || "\u2014"],
  ];
  document.getElementById("metaGrid").innerHTML = rows
    .map(([k, v]) => `<div class="k">${{k}}</div><div>${{v}}</div>`)
    .join("");
}}

runSel.addEventListener("change", render);
render();
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate experiment results dashboard")
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help="Path to a specific run directory OR a repeat aggregate JSON file",
    )
    parser.add_argument("--results-dir", type=str, default="results", help="Root results directory")
    parser.add_argument("--output", type=str, default="results/compare.html", help="Output HTML path")
    parser.add_argument(
        "--include-stale",
        action="store_true",
        help="Include stale/legacy runs (default: stale runs excluded).",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    if args.run:
        run = load_run_path(Path(args.run))
        if not run:
            raise SystemExit(f"No valid run found at {args.run}")
        runs = [run]
    else:
        runs = load_all_runs(results_dir, include_stale=args.include_stale)
        # Also try loading latest/ as fallback
        if not runs:
            latest = results_dir / "latest"
            if latest.exists():
                run = load_run(latest)
                if run:
                    runs = [run]

    if not runs:
        raise SystemExit(f"No valid runs found under {results_dir}")

    config = load_experiment_config(results_dir)
    html = build_html(runs, config=config)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    print(f"Dashboard written to {output_path} ({len(runs)} run(s))")


if __name__ == "__main__":
    main()
