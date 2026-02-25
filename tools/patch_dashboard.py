#!/usr/bin/env python3
"""Live dashboard for GraphManager patch runs.

Usage:
  ./.venv/bin/python tools/patch_dashboard.py --port 5051
Open:
  http://localhost:5051
"""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.patch_dashboard import collect_dashboard_status, load_manifest_plan_summary, summarize_dashboard_runs


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GraphManager Patch Dashboard</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Mono", "Fira Code", "Cascadia Code", ui-monospace, monospace;
      background: radial-gradient(circle at 15% 0%, #12214a 0%, #0b132a 45%, #060b1b 100%);
      color: #dae2ff;
      min-height: 100vh;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 18px;
      border-bottom: 1px solid #213062;
      background: rgba(6, 11, 27, 0.88);
      backdrop-filter: blur(8px);
    }
    .title-wrap { display: flex; flex-direction: column; gap: 2px; }
    .title { font-size: 16px; font-weight: 700; color: #eef2ff; letter-spacing: 0.02em; }
    .subtitle { font-size: 11px; color: #9fb0e8; }
    .live-wrap { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #a9b7e5; }
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .dot-ok { background: #48d597; box-shadow: 0 0 8px #48d59799; }
    .dot-idle { background: #6f7ca7; }
    .wrap { max-width: 1500px; margin: 0 auto; padding: 14px 18px 26px 18px; }
    .meta { color: #9fb0e8; font-size: 12px; margin-bottom: 10px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
    .controls {
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 12px;
      padding: 10px 12px;
      border: 1px solid #213062;
      border-radius: 10px;
      background: #0f1a3b;
    }
    .controls label {
      font-size: 12px;
      color: #d8e1ff;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      user-select: none;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .stat-card {
      border: 1px solid #24336a;
      border-radius: 10px;
      background: #0f1a3b;
      padding: 10px 12px;
    }
    .stat-value { font-size: 20px; font-weight: 700; color: #f1f4ff; line-height: 1.1; }
    .stat-label { font-size: 10px; color: #9eb0e7; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 3px; }
    .not-started-help {
      margin-bottom: 12px;
      border: 1px solid #3d2f19;
      background: #1d1810;
      color: #f4db9a;
      border-radius: 9px;
      padding: 9px 11px;
      font-size: 11px;
      display: none;
    }
    details.method-group {
      border: 1px solid #24336a;
      border-radius: 10px;
      background: #0d1735;
      margin-bottom: 10px;
      overflow: hidden;
    }
    details.method-group[open] { background: #0f1a3b; }
    summary.method-summary {
      list-style: none;
      cursor: pointer;
      padding: 11px 12px;
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 1px solid #223368;
    }
    summary.method-summary::-webkit-details-marker { display: none; }
    .arrow {
      width: 10px;
      height: 10px;
      border-right: 2px solid #8ea2db;
      border-bottom: 2px solid #8ea2db;
      transform: rotate(-45deg);
      transition: transform .15s ease;
      margin-right: 2px;
      flex-shrink: 0;
    }
    details[open] .arrow { transform: rotate(45deg); }
    .method-name { font-size: 13px; font-weight: 700; color: #ebefff; min-width: 170px; }
    .pill {
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .05em;
      border: 1px solid #2b3f7b;
      color: #b6c6f2;
      background: #15244e;
      white-space: nowrap;
    }
    .pill-running { border-color: #226e4b; color: #7ef1ba; background: #143827; }
    .pill-not-started { border-color: #4e5a82; color: #d0d6eb; background: #2a3147; }
    .pill-complete { border-color: #2f5f9b; color: #86bfff; background: #1a3051; }
    .pill-stalled { border-color: #87363c; color: #ff9ba6; background: #4a1f24; }
    .method-summary-right {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .method-body { padding: 8px 10px 12px 10px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      background: #0a132e;
      border: 1px solid #1f2f62;
      border-radius: 9px;
      overflow: hidden;
    }
    th, td { text-align: left; padding: 7px; border-bottom: 1px solid #1b2a58; vertical-align: top; }
    th {
      color: #b8c6f1;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: .03em;
      background: #0e1a3a;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tr:hover td { background: #101f46; }
    .sub { color: #7c8fca; font-size: 11px; margin-top: 2px; }
    .dim { color: #90a1d7; }
    .warn { color: #f4db9a; }
    .good { color: #7ef1ba; }
    .bad { color: #ff9ba6; }
    .progress-bar {
      position: relative;
      margin-top: 4px;
      height: 6px;
      border-radius: 99px;
      background: #192a59;
      overflow: hidden;
    }
    .progress-fill {
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      background: linear-gradient(90deg, #4ea8ff 0%, #67d4ff 100%);
    }
    .empty {
      border: 1px dashed #31457f;
      border-radius: 10px;
      background: #0f1a3b;
      color: #9eb0e7;
      padding: 18px;
      text-align: center;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="title-wrap">
      <div class="title">GraphManager Patch Dashboard</div>
      <div class="subtitle">Grouped by retrieval method with manifest-level run attempts</div>
    </div>
    <div class="live-wrap">
      <span id="liveDot" class="dot dot-idle"></span>
      <span id="updated">Loading…</span>
    </div>
  </div>
  <div class="wrap">
    <div class="meta">
      One row = one manifest run attempt · Auto-refresh every 10s · Results root: <span id="root" class="mono"></span>
    </div>
    <div class="controls">
      <label><input type="checkbox" id="activeOnly" checked /> Active only</label>
      <label><input type="checkbox" id="includeComplete" /> Include complete</label>
      <label><input type="checkbox" id="includeStale" /> Include stalled / stale</label>
    </div>
    <div class="stats-grid" id="stats"></div>
    <div class="not-started-help" id="notStartedHelp"></div>
    <div id="methodGroups"></div>
  </div>
  <script>
    function fmtNum(x) {
      if (x === null || x === undefined) return "—";
      return new Intl.NumberFormat().format(x);
    }
    function fmtPct(x) {
      if (x === null || x === undefined) return "—";
      return `${x.toFixed(1)}%`;
    }
    function fmtRate(x) {
      if (x === null || x === undefined) return "—";
      return `${(x * 100).toFixed(1)}%`;
    }
    function fmtCpr(x) {
      if (x === null || x === undefined) return "—";
      return fmtNum(Math.round(x));
    }
    function toQ(v) { return v ? "1" : "0"; }
    function statusCounts(rows) {
      const out = { running: 0, not_started: 0, complete: 0, stalled: 0 };
      for (const r of rows) {
        const s = (r.status || "not_started");
        out[s] = (out[s] || 0) + 1;
      }
      return out;
    }
    function statusPill(status, label=null) {
      const s = status || "not_started";
      const text = label || s.toUpperCase();
      return `<span class="pill pill-${s.replace("_", "-")}">${text}</span>`;
    }
    function rowPhaseHint(r) {
      if ((r.status || "not_started") !== "not_started") return "";
      if (r.meta_pid_alive === false) return "stopped before first completed instance (stale attempt)";
      if (r.meta_pid_alive === true) return "setup/queued: run is alive but has not completed an instance yet";
      return "setup/queued: run initialized but no completed instances yet";
    }
    function _ratioText(num, den) {
      if (den === null || den === undefined || den <= 0) {
        return `${fmtNum(num || 0)} / ?`;
      }
      return `${fmtNum(num || 0)} / ${fmtNum(den)} (${fmtPct(((num || 0) / den) * 100)})`;
    }
    function renderStats(rows, visibleSummary, startedSummary, planSummary) {
      const c = (visibleSummary && visibleSummary.status_counts) ? visibleSummary.status_counts : statusCounts(rows);
      const methods = new Set(rows.map(r => r.retrieval_method || "unknown"));
      const visiblePatched = (visibleSummary && visibleSummary.n_patched_total !== undefined)
        ? visibleSummary.n_patched_total
        : rows.reduce((s, r) => s + (r.n_patched || 0), 0);
      const visibleTotal = (visibleSummary && visibleSummary.n_instances_total !== undefined)
        ? visibleSummary.n_instances_total
        : rows.reduce((s, r) => s + (r.n_instances || 0), 0);
      const startedPatched = (startedSummary && startedSummary.n_patched_total !== undefined)
        ? startedSummary.n_patched_total
        : visiblePatched;
      const startedTotal = (startedSummary && startedSummary.n_instances_total !== undefined)
        ? startedSummary.n_instances_total
        : visibleTotal;
      const plannedTotal = (planSummary && planSummary.exists) ? (planSummary.n_instances_planned || 0) : 0;
      const cards = [
        { label: "Visible Patched / Total", value: _ratioText(visiblePatched, visibleTotal) },
        { label: "Started Patched / Total", value: _ratioText(startedPatched, startedTotal) },
        { label: "Campaign Patched / Planned", value: _ratioText(startedPatched, plannedTotal) },
        { label: "Run Attempts", value: rows.length },
        { label: "Methods Visible", value: methods.size },
        { label: "Running", value: c.running || 0 },
        { label: "Pending (No Completed Instance Yet)", value: c.not_started || 0 },
        { label: "Complete", value: c.complete || 0 },
        { label: "Stalled", value: c.stalled || 0 },
      ];
      document.getElementById("stats").innerHTML = cards.map(card => (
        `<div class="stat-card"><div class="stat-value">${typeof card.value === "number" ? fmtNum(card.value) : card.value}</div><div class="stat-label">${card.label}</div></div>`
      )).join("");
      const help = document.getElementById("notStartedHelp");
      if ((c.not_started || 0) > 0) {
        help.style.display = "block";
        help.textContent = `${c.not_started} run(s) are pending. "Not started" means run metadata exists, but 0 instances are completed so far (often setup/index build before first result).`;
      } else {
        help.style.display = "none";
        help.textContent = "";
      }
    }
    function sortRows(rows) {
      const rank = { running: 0, not_started: 1, complete: 2, stalled: 3 };
      return [...rows].sort((a, b) => {
        const sa = rank[a.status || "not_started"] ?? 9;
        const sb = rank[b.status || "not_started"] ?? 9;
        if (sa !== sb) return sa - sb;
        return (b.last_seen_ts || 0) - (a.last_seen_ts || 0);
      });
    }
    function groupByMethod(rows) {
      const groups = new Map();
      for (const row of rows) {
        const method = row.retrieval_method || "unknown";
        if (!groups.has(method)) groups.set(method, []);
        groups.get(method).push(row);
      }
      const entries = Array.from(groups.entries());
      entries.sort((a, b) => {
        const ac = statusCounts(a[1]).running || 0;
        const bc = statusCounts(b[1]).running || 0;
        if (ac !== bc) return bc - ac;
        return a[0].localeCompare(b[0]);
      });
      return entries;
    }
    function renderMethodGroups(rows) {
      const grouped = groupByMethod(rows);
      if (!grouped.length) {
        document.getElementById("methodGroups").innerHTML = `<div class="empty">No runs found for current filters.</div>`;
        return;
      }

      const html = grouped.map(([method, methodRows], idx) => {
        const c = statusCounts(methodRows);
        const openByDefault = (c.running || 0) > 0 || idx === 0;
        const sortedRows = sortRows(methodRows);
        const totalN = sortedRows.reduce((s, r) => s + (r.n_instances || 0), 0);
        const totalDone = sortedRows.reduce((s, r) => s + (r.n_completed || 0), 0);
        const donePct = totalN > 0 ? ((totalDone / totalN) * 100.0).toFixed(1) : "—";
        const rowsHtml = sortedRows.map(r => {
          const cls = r.status || "not_started";
          const progress = r.n_instances > 0 ? `${r.n_completed}/${r.n_instances} (${fmtPct(r.progress_pct)})` : `${r.n_completed} / ?`;
          const resolved = r.n_resolved === null ? "—" : `${r.n_resolved}/${r.n_instances} (${fmtRate(r.resolved_rate)})`;
          const updatedAge = r.updated_age_minutes ?? r.seen_age_minutes;
          const updated = updatedAge === null || updatedAge === undefined ? "—" : `${updatedAge}m ago`;
          const phaseHint = rowPhaseHint(r);
          const progressBar = (r.progress_pct === null || r.progress_pct === undefined)
            ? ""
            : `<div class="progress-bar"><div class="progress-fill" style="width:${Math.max(0, Math.min(100, r.progress_pct))}%"></div></div>`;
          return `<tr>
            <td><div class="mono">${r.manifest_name || "—"}</div><div class="sub mono">${r.manifest_path || ""}</div></td>
            <td>${r.repo_name || "—"}</td>
            <td><div class="mono">${r.run_id}</div><div class="sub mono">${r.run_dir}</div></td>
            <td>${statusPill(cls)}</td>
            <td>${progress}${progressBar}</td>
            <td>${phaseHint ? `<span class="warn">${phaseHint}</span>` : '<span class="dim">—</span>'}</td>
            <td>${r.n_patched} <span class="dim">(apply_failed=${r.n_apply_failed})</span></td>
            <td>${resolved}</td>
            <td>${fmtCpr(r.cost_per_resolved_issue)}</td>
            <td>${updated}</td>
          </tr>`;
        }).join("");

        return `<details class="method-group" ${openByDefault ? "open" : ""}>
          <summary class="method-summary">
            <span class="arrow"></span>
            <span class="method-name">${method}</span>
            <span class="pill">${methodRows.length} run(s)</span>
            <span class="pill">progress ${totalDone}/${totalN || "?"} (${donePct === "—" ? "—" : `${donePct}%`})</span>
            <span class="method-summary-right">
              ${statusPill("running", `RUNNING ${c.running || 0}`)}
              ${statusPill("not_started", `PENDING ${c.not_started || 0}`)}
              ${statusPill("complete", `COMPLETE ${c.complete || 0}`)}
              ${statusPill("stalled", `STALLED ${c.stalled || 0}`)}
            </span>
          </summary>
          <div class="method-body">
            <table>
              <thead>
                <tr>
                  <th>Manifest</th>
                  <th>Repo</th>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Phase</th>
                  <th>Patched</th>
                  <th>Resolved</th>
                  <th>Cost / Resolved</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>
        </details>`;
      }).join("");
      document.getElementById("methodGroups").innerHTML = html;
    }
    async function refresh() {
      const activeOnly = document.getElementById("activeOnly").checked;
      const includeComplete = document.getElementById("includeComplete").checked;
      const includeStale = document.getElementById("includeStale").checked;
      const qs = new URLSearchParams({
        active_only: toQ(activeOnly),
        include_complete: toQ(includeComplete),
        include_stale: toQ(includeStale),
      });
      const resp = await fetch(`/api/status?${qs.toString()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      const rows = payload.runs || [];
      const visibleSummary = payload.summary_visible || payload.summary || null;
      const startedSummary = payload.summary_started || visibleSummary || null;
      const planSummary = payload.summary_plan || null;

      renderStats(rows, visibleSummary, startedSummary, planSummary);
      renderMethodGroups(rows);
      document.getElementById("root").textContent = payload.results_root || "";

      const nowText = `Updated ${new Date().toLocaleTimeString()}`;
      document.getElementById("updated").textContent = nowText;
      const anyRunning = rows.some(r => (r.status || "not_started") === "running");
      document.getElementById("liveDot").className = anyRunning ? "dot dot-ok" : "dot dot-idle";
    }
    async function tick() {
      try { await refresh(); } catch (e) { console.error(e); }
    }
    for (const id of ["activeOnly", "includeComplete", "includeStale"]) {
      document.getElementById(id).addEventListener("change", tick);
    }
    tick();
    setInterval(tick, 10000);
  </script>
</body>
</html>
"""


def make_handler(results_root: Path, stale_after_minutes: float, manifest_list_path: Path | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                active_only = query.get("active_only", ["1"])[0] == "1"
                include_complete = query.get("include_complete", ["0"])[0] == "1"
                include_stale = query.get("include_stale", ["0"])[0] == "1"
                runs = collect_dashboard_status(
                    results_root,
                    stale_after_minutes=stale_after_minutes,
                    active_only=active_only,
                    include_complete=include_complete,
                    include_stale=include_stale,
                )
                all_started_runs = collect_dashboard_status(
                    results_root,
                    stale_after_minutes=stale_after_minutes,
                    active_only=False,
                    include_complete=True,
                    include_stale=True,
                )
                summary_visible = summarize_dashboard_runs(runs)
                summary_started = summarize_dashboard_runs(all_started_runs)
                summary_plan = (
                    load_manifest_plan_summary(manifest_list_path, root_dir=ROOT)
                    if manifest_list_path is not None
                    else None
                )
                payload = {
                    "results_root": str(results_root),
                    "run_count": len(runs),
                    "summary": summary_visible,
                    "summary_visible": summary_visible,
                    "summary_started": summary_started,
                    "summary_plan": summary_plan,
                    "runs": runs,
                }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            # keep stdout clean while polling
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="GraphManager patch run dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5051, help="Bind port (default: 5051)")
    parser.add_argument(
        "--results-root",
        default="results",
        help="Results root directory to scan (default: results)",
    )
    parser.add_argument(
        "--stale-after-minutes",
        type=float,
        default=15.0,
        help="Mark in-flight runs as stalled if no updates after this many minutes (default: 15)",
    )
    parser.add_argument(
        "--manifest-list",
        default=None,
        help="Optional manifest-list file to compute campaign planned totals.",
    )
    args = parser.parse_args()

    results_root = Path(args.results_root).resolve()
    manifest_list_path = Path(args.manifest_list).resolve() if args.manifest_list else None
    handler_cls = make_handler(
        results_root,
        stale_after_minutes=args.stale_after_minutes,
        manifest_list_path=manifest_list_path,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"Dashboard listening on http://{args.host}:{args.port}")
    print(f"Scanning results root: {results_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
