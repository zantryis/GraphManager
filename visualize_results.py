#!/usr/bin/env python3
"""
Generate an interactive HTML dashboard comparing retrieval methods.

Usage:
    python visualize_results.py                          # latest run
    python visualize_results.py --run results/runs/20260210_164949
    python visualize_results.py --all-runs               # compare across runs
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

METHODS = ["graph_manager", "rag_agent", "raw_rag_function", "raw_rag_fixed"]
METHOD_LABELS = {
    "graph_manager": "Graph-Manager",
    "rag_agent": "RAG-Agent",
    "raw_rag_function": "Raw-RAG (func)",
    "raw_rag_fixed": "Raw-RAG (fixed)",
}
METHOD_COLORS = {
    "graph_manager": "#0b7285",
    "rag_agent": "#c2410c",
    "raw_rag_function": "#6d28d9",
    "raw_rag_fixed": "#9333ea",
}


def load_run(run_dir: Path) -> dict[str, Any] | None:
    """Load summary + detailed results from a run directory."""
    summary_path = run_dir / "summary.json"
    detailed_path = run_dir / "detailed_results.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text())
    detailed = json.loads(detailed_path.read_text()) if detailed_path.exists() else []
    meta = summary.get("_meta", {})
    return {
        "run_id": meta.get("run_id", run_dir.name),
        "meta": meta,
        "summary": {m: summary.get(m, {}) for m in METHODS},
        "issues": detailed,
    }


def load_all_runs(results_dir: Path) -> list[dict[str, Any]]:
    """Load all runs from results/runs/."""
    runs = []
    runs_dir = results_dir / "runs"
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir()):
            if d.is_dir() and d.name[:1].isdigit():
                run = load_run(d)
                if run:
                    runs.append(run)
    return runs


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
    data = json.dumps({
        "runs": runs,
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

/* Chart containers */
.chart-box {{ position: relative; height: 300px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Graph-Augmented Manager &mdash; Experiment Results</h1>
    <p>Comparing knowledge-graph retrieval vs RAG baselines on SWE-bench issues</p>
  </header>

  <div id="configBanner" class="card" style="display:none;margin-bottom:16px;">
    <h2 id="configTitle"></h2>
    <p id="configDesc" style="color:var(--muted);font-size:0.9rem;"></p>
  </div>

  <div class="controls">
    <label for="repoFilter">Repo:</label>
    <select id="repoFilter"><option value="all">All repos</option></select>
    <label for="runSelect">Run:</label>
    <select id="runSelect"></select>
  </div>

  <!-- KPI cards -->
  <div class="grid grid-4" id="kpis"></div>

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

  <!-- Cost vs Quality scatter -->
  <div class="card">
    <h2>Cost-Quality Trade-off (per issue)</h2>
    <div class="chart-box" style="height:340px;"><canvas id="scatterChart"></canvas></div>
  </div>

  <!-- Per-issue table -->
  <div class="card">
    <h2>Per-Issue Results</h2>
    <table id="issueTable">
      <thead>
        <tr>
          <th style="width:28px"></th>
          <th>Issue</th>
          <th>Gold Files</th>
          <th class="num">GM F1</th>
          <th class="num">RAG F1</th>
          <th class="num">Raw-func F1</th>
          <th class="num">Raw-fixed F1</th>
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
          <th>Repo</th>
          <th>Mode (GM / RAG)</th>
          <th class="num">Issues</th>
          <th class="num">GM F1</th>
          <th class="num">RAG F1</th>
          <th class="num">GM Tok/Issue</th>
          <th class="num">RAG Tok/Issue</th>
          <th class="num">GM Setup</th>
          <th class="num">RAG Setup</th>
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

let qualityChart = null, costChart = null, scatterChart = null;

// --- Config banner ---
if (D.config) {{
  const banner = document.getElementById("configBanner");
  banner.style.display = "";
  document.getElementById("configTitle").textContent = D.config.suite || "Experiment Suite";
  document.getElementById("configDesc").textContent = (D.config.description || "").trim();
}}

// --- Repo filter ---
const repoFilter = document.getElementById("repoFilter");
const repos = [...new Set(D.runs.map(r => r.meta.repo_name || "?"))].sort();
for (const repo of repos) {{
  const opt = document.createElement("option");
  opt.value = repo;
  opt.textContent = repo;
  repoFilter.appendChild(opt);
}}

function filteredRuns() {{
  const repo = repoFilter.value;
  return repo === "all" ? D.runs : D.runs.filter(r => (r.meta.repo_name || "?") === repo);
}}

function rebuildRunSelect() {{
  const runSel = document.getElementById("runSelect");
  const prev = runSel.value;
  runSel.innerHTML = "";
  for (const run of filteredRuns()) {{
    const opt = document.createElement("option");
    const m = run.meta;
    opt.value = run.run_id;
    opt.textContent = `${{m.repo_name || "?"}} | GM=${{m.manager_mode || "?"}} RAG=${{m.rag_mode || "?"}} | n=${{m.n_issues_evaluated || "?"}}`;
    runSel.appendChild(opt);
  }}
  const ids = filteredRuns().map(r => r.run_id);
  if (ids.includes(prev)) runSel.value = prev;
  else if (ids.length) runSel.value = ids[ids.length - 1];
  render();
}}

const runSel = document.getElementById("runSelect");
repoFilter.addEventListener("change", () => {{ rebuildRunSelect(); buildCrossRunTable(); }});
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
    const gm = run.summary.graph_manager || {{}};
    const ra = run.summary.rag_agent || {{}};
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => {{ runSel.value = run.run_id; render(); }});
    tr.innerHTML = `
      <td><strong>${{m.repo_name || "?"}}</strong></td>
      <td>${{m.manager_mode || "?"}} / ${{m.rag_mode || "?"}}</td>
      <td class="num">${{m.n_issues_evaluated || "?"}}</td>
      <td class="num">${{fmt3(gm.mean_f1)}}</td>
      <td class="num">${{fmt3(ra.mean_f1)}}</td>
      <td class="num">${{fmtK(gm.avg_llm_tokens_per_issue)}}</td>
      <td class="num">${{fmtK(ra.avg_llm_tokens_per_issue)}}</td>
      <td class="num">${{fmtK(gm.setup_embedding_tokens)}}</td>
      <td class="num">${{fmtK(ra.setup_embedding_tokens)}}</td>
    `;
    tbody.appendChild(tr);
  }}
}}
buildCrossRunTable();

// --- Helpers ---
function fmt3(v) {{ return (v || 0).toFixed(3); }}
function fmtK(v) {{ const n = Number(v || 0); return n >= 1000 ? (n / 1000).toFixed(1) + "k" : Math.round(n).toLocaleString(); }}
function fmtN(v) {{ return Math.round(Number(v || 0)).toLocaleString(); }}

function getRun(id) {{ return D.runs.find(r => r.run_id === id); }}

function bestMethod(issue) {{
  let best = "", bestF1 = -1;
  for (const m of METHODS) {{
    const f1 = issue.methods?.[m]?.metrics?.f1 ?? -1;
    if (f1 > bestF1) {{ bestF1 = f1; best = m; }}
  }}
  return best;
}}

// --- Render ---
function render() {{
  const run = getRun(runSel.value);
  if (!run) return;
  renderKPIs(run);
  renderQualityChart(run);
  renderCostChart(run);
  renderScatterChart(run);
  renderIssueTable(run);
  renderMeta(run);
}}

function renderKPIs(run) {{
  const s = run.summary;
  const gm = s.graph_manager || {{}};
  const ra = s.rag_agent || {{}};
  const n = run.meta.n_issues_evaluated || 0;

  // Find best F1 method
  let bestM = "", bestF1 = -1;
  for (const m of METHODS) {{
    const f1 = s[m]?.mean_f1 ?? 0;
    if (f1 > bestF1) {{ bestF1 = f1; bestM = m; }}
  }}

  // Find cheapest agentic method
  const gmCost = gm.total_cost_tokens || Infinity;
  const raCost = ra.total_cost_tokens || Infinity;
  const cheapest = gmCost <= raCost ? "graph_manager" : "rag_agent";
  const cheapCost = Math.min(gmCost, raCost);

  document.getElementById("kpis").innerHTML = `
    <div class="card kpi">
      <div class="label">Best F1</div>
      <div class="value">${{fmt3(bestF1)}}</div>
      <div class="sub">${{LABELS[bestM]}}</div>
    </div>
    <div class="card kpi">
      <div class="label">GM vs RAG F1</div>
      <div class="value">${{fmt3(gm.mean_f1)}} / ${{fmt3(ra.mean_f1)}}</div>
      <div class="sub">&Delta; ${{(((gm.mean_f1 || 0) - (ra.mean_f1 || 0)) * 100).toFixed(1)}}%</div>
    </div>
    <div class="card kpi">
      <div class="label">Total Cost (tokens)</div>
      <div class="value">${{fmtK(gm.total_cost_tokens)}} / ${{fmtK(ra.total_cost_tokens)}}</div>
      <div class="sub">GM / RAG (setup+LLM)</div>
    </div>
    <div class="card kpi">
      <div class="label">Issues Evaluated</div>
      <div class="value">${{n}}</div>
      <div class="sub">${{run.meta.repo_name || "?"}}</div>
    </div>
  `;
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

  const datasets = [];
  for (const m of ["graph_manager", "rag_agent"]) {{
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
      pointRadius: 6,
      pointHoverRadius: 9,
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
        const f1 = issue.methods?.[m]?.metrics?.f1;
        const cls = m === best ? ' class="num winner"' : ' class="num"';
        const bar = f1 != null ? `<span class="f1-bar" style="width:${{Math.round((f1||0)*60)}}px;background:${{COLORS[m]}}"></span>` : "";
        return `<td${{cls}}>${{bar}}${{f1 != null ? f1.toFixed(3) : "err"}}</td>`;
      }}).join("")}}
      <td>${{LABELS[best] || "?"}}</td>
    `;
    tbody.appendChild(tr);

    // Detail row (hidden)
    const detailTr = document.createElement("tr");
    detailTr.className = "detail-row hidden";
    detailTr.id = `detail-${{issue.instance_id}}`;

    let detailHtml = '<td colspan="8">';
    detailHtml += `<div style="margin-bottom:8px;"><strong>Gold files:</strong> <span class="file-list" style="display:inline-flex;">`;
    for (const f of (issue.gold_files || [])) {{
      detailHtml += `<span class="file-tag gold">${{f}}</span>`;
    }}
    detailHtml += `</span></div>`;

    for (const m of METHODS) {{
      const md = issue.methods?.[m];
      if (!md || md.error) {{
        detailHtml += `<div class="method-detail"><div class="name">${{LABELS[m]}}</div><div class="stats">Error</div></div>`;
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
  const rows = [
    ["Run ID", m.run_id || run.run_id],
    ["Created", m.created_at || "?"],
    ["Repository", m.repo_name || "?"],
    ["Dataset", m.dataset_name || "?"],
    ["Issues evaluated", m.n_issues_evaluated || "?"],
    ["Manager mode", m.manager_mode || "?"],
    ["RAG mode", m.rag_mode || "?"],
    ["Manager max turns", m.manager_max_turns || "?"],
    ["RAG max turns", m.rag_max_turns || "?"],
    ["Source prefixes", (m.source_prefixes || []).join(", ") || "?"],
    ["LLM model", m.manager_model || "?"],
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
    parser.add_argument("--run", type=str, default=None, help="Path to a specific run directory")
    parser.add_argument("--results-dir", type=str, default="results", help="Root results directory")
    parser.add_argument("--output", type=str, default="results/compare.html", help="Output HTML path")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    if args.run:
        run = load_run(Path(args.run))
        if not run:
            raise SystemExit(f"No valid run found at {args.run}")
        runs = [run]
    else:
        runs = load_all_runs(results_dir)
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
