#!/usr/bin/env python3
"""Live dashboard for GraphManager V2 campaign.

Serves three tabs: Retrieval (T0 grid), Patching (T1/T2 progress), Campaign (queue status).

Usage:
  ./.venv/bin/python tools/patch_dashboard.py --port 5051
Open:
  http://localhost:5051
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.patch_dashboard import (
    build_retrieval_status,
    collect_dashboard_status,
    load_campaign_state,
    load_manifest_plan_summary,
    summarize_dashboard_runs,
)

# V2 canonical populations (mirrored from aggregate_v2_results.py)
_V2_REPOS = [
    "astropy/astropy", "django/django", "matplotlib/matplotlib", "mwaskom/seaborn",
    "pallets/flask", "psf/requests", "pydata/xarray", "pylint-dev/pylint",
    "pytest-dev/pytest", "scikit-learn/scikit-learn", "sphinx-doc/sphinx", "sympy/sympy",
]
_V2_METHODS = [
    "gm_deterministic", "gm_progressive", "gm_baseline",
    "rag_progressive", "rag_baseline",
    "raw_rag_function", "raw_rag_fixed",
    "bm25", "repomap_like", "agentless_like_localization", "agentic_cold_start",
]

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GraphManager V2</title>
  <style>
    :root {
      --bg: #0f172a; --surface: #1e293b; --surface2: #263348;
      --border: #334155; --text: #f1f5f9; --muted: #94a3b8;
      --green: #22c55e; --amber: #f59e0b; --blue: #3b82f6;
      --red: #ef4444; --gray: #475569;
      --green-bg: #052e16; --amber-bg: #3d2000; --red-bg: #3d0000; --gray-bg: #1e2330;
      --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      --mono: ui-monospace, 'SF Mono', 'Fira Code', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 13px; line-height: 1.5; }
    a { color: var(--blue); }

    /* ── Header ── */
    .header {
      position: fixed; top: 0; left: 0; right: 0; z-index: 200;
      height: 50px; background: var(--surface); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; padding: 0 20px; gap: 14px;
    }
    .header-title { font-weight: 700; font-size: 14px; letter-spacing: 0.01em; }
    .header-spacer { flex: 1; }
    .live-dot {
      width: 8px; height: 8px; border-radius: 50%; background: var(--green);
      box-shadow: 0 0 6px var(--green);
    }
    .live-dot.idle { background: var(--gray); box-shadow: none; }
    @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
    .live-dot.active { animation: blink 2s infinite; }
    .header-ts { color: var(--muted); font-size: 11px; }

    /* ── Tabs ── */
    .tabs {
      position: fixed; top: 50px; left: 0; right: 0; z-index: 199;
      background: var(--surface); border-bottom: 1px solid var(--border);
      display: flex; gap: 0; padding: 0 20px;
    }
    .tab-btn {
      padding: 9px 18px; background: none; border: none; cursor: pointer;
      font-family: var(--font); font-size: 13px; font-weight: 500; color: var(--muted);
      border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color 0.15s;
    }
    .tab-btn:hover { color: var(--text); }
    .tab-btn.active { color: var(--blue); border-bottom-color: var(--blue); }

    /* ── Content ── */
    .content { margin-top: 90px; padding: 20px 24px; max-width: 1700px; margin-left: auto; margin-right: auto; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* ── Chips / Summary bar ── */
    .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; align-items: center; }
    .chip {
      padding: 3px 11px; border-radius: 20px; font-size: 11px; font-weight: 600;
      background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
    }
    .chip.green { color: var(--green); border-color: #166534; background: var(--green-bg); }
    .chip.amber { color: var(--amber); border-color: #78350f; background: var(--amber-bg); }
    .chip.red   { color: var(--red);   border-color: #7f1d1d; background: var(--red-bg); }
    .chip.blue  { color: var(--blue);  border-color: #1e3a5f; background: #172036; }

    /* ── Retrieval grid ── */
    .grid-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid var(--border); }
    .rgrid { border-collapse: collapse; font-size: 11px; white-space: nowrap; width: 100%; }
    .rgrid th {
      background: var(--surface); color: var(--muted); padding: 6px 10px;
      border: 1px solid var(--border); font-weight: 600; text-align: center; font-size: 10px;
      text-transform: uppercase; letter-spacing: 0.04em; position: sticky; top: 0; z-index: 1;
    }
    .rgrid th.repo-col { text-align: left; min-width: 130px; position: sticky; left: 0; z-index: 2; }
    .rgrid td.repo-name {
      background: var(--surface); color: var(--text); padding: 5px 10px;
      border: 1px solid var(--border); font-weight: 600; position: sticky; left: 0; z-index: 1;
    }
    .rgrid td.cell {
      text-align: center; padding: 4px 8px; border: 1px solid var(--border);
      min-width: 56px; font-size: 11px; font-family: var(--mono); cursor: default;
      transition: background 0.2s;
    }
    .cell.done    { background: var(--green-bg); color: var(--green); font-weight: 700; }
    .cell.pending { background: transparent; color: var(--gray); }
    @keyframes shimmer { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
    .cell.in-progress { background: var(--amber-bg); color: var(--amber); animation: shimmer 1.4s infinite; }

    /* ── Patching table ── */
    .section-label {
      font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--muted); margin-bottom: 10px; margin-top: 22px;
    }
    .section-label:first-child { margin-top: 0; }
    .method-group { margin-bottom: 12px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .method-hdr {
      display: flex; align-items: center; gap: 10px; padding: 10px 14px;
      background: var(--surface); cursor: pointer; user-select: none;
    }
    .method-hdr:hover { background: var(--surface2); }
    .method-hdr-name { font-weight: 700; font-size: 13px; flex: 1; }
    .method-hdr-stats { color: var(--muted); font-size: 11px; }
    .chevron { color: var(--muted); font-size: 10px; transition: transform 0.15s; }
    .method-hdr.open .chevron { transform: rotate(90deg); }
    .method-body { display: none; }
    .method-body.open { display: block; }
    .ptable { width: 100%; border-collapse: collapse; }
    .ptable th {
      text-align: left; padding: 7px 12px; font-size: 11px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    .ptable td { padding: 7px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    .ptable tr:last-child td { border-bottom: none; }
    .ptable tr:hover td { background: rgba(255,255,255,0.025); }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    }
    .badge.running    { background: var(--amber-bg); color: var(--amber); }
    .badge.complete   { background: var(--green-bg); color: var(--green); }
    .badge.stalled    { background: var(--red-bg);   color: var(--red);   }
    .badge.not_started{ background: var(--gray-bg);  color: var(--muted); }
    .pbar { height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; width: 80px; display: inline-block; vertical-align: middle; margin-left: 6px; }
    .pbar-fill { height: 100%; background: var(--blue); border-radius: 2px; }
    .pbar-fill.done { background: var(--green); }
    .muted { color: var(--muted); }

    /* ── Campaign tab ── */
    .csteps { display: flex; flex-direction: column; gap: 8px; max-width: 680px; }
    .cstep {
      display: flex; align-items: flex-start; gap: 12px; padding: 12px 16px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    }
    .cstep-icon {
      width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center;
      justify-content: center; font-size: 11px; font-weight: 800; flex-shrink: 0; margin-top: 1px;
    }
    .cstep-icon.done    { background: #166534; color: var(--green); }
    .cstep-icon.running { background: #78350f; color: var(--amber); animation: blink 1.5s infinite; }
    .cstep-icon.failed  { background: #7f1d1d; color: var(--red); }
    .cstep-icon.pending { background: var(--border); color: var(--gray); }
    .cstep-name { font-weight: 700; font-size: 13px; }
    .cstep-desc { color: var(--muted); font-size: 11px; margin-top: 1px; }
    .cstep-time { margin-left: auto; color: var(--muted); font-size: 11px; white-space: nowrap; padding-left: 12px; }
    .no-data { color: var(--muted); font-size: 12px; padding: 16px 0; }

    /* ── Controls ── */
    .controls { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 14px; }
    .controls label { display: flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px; cursor: pointer; }
    .controls input[type=checkbox] { accent-color: var(--blue); }
  </style>
</head>
<body>
  <div class="header">
    <div class="header-title">GraphManager V2 Campaign</div>
    <div class="header-spacer"></div>
    <div class="live-dot idle" id="liveDot"></div>
    <div class="header-ts" id="headerTs">—</div>
  </div>
  <div class="tabs">
    <button class="tab-btn active" id="tab-btn-retrieval" onclick="switchTab('retrieval')">Retrieval</button>
    <button class="tab-btn" id="tab-btn-patching" onclick="switchTab('patching')">Patching</button>
    <button class="tab-btn" id="tab-btn-campaign" onclick="switchTab('campaign')">Campaign</button>
  </div>
  <div class="content">

    <!-- ── Retrieval Tab ── -->
    <div class="tab-pane active" id="tab-retrieval">
      <div class="chips" id="ret-chips"></div>
      <div class="grid-wrap">
        <table class="rgrid" id="ret-grid"></table>
      </div>
    </div>

    <!-- ── Patching Tab ── -->
    <div class="tab-pane" id="tab-patching">
      <div class="chips" id="pat-chips"></div>
      <div class="controls">
        <label><input type="checkbox" id="chkActive" checked> Active only</label>
        <label><input type="checkbox" id="chkComplete"> Include complete</label>
        <label><input type="checkbox" id="chkStale"> Include stalled</label>
      </div>
      <div id="pat-body"></div>
    </div>

    <!-- ── Campaign Tab ── -->
    <div class="tab-pane" id="tab-campaign">
      <div class="section-label">Campaign Queue</div>
      <div class="csteps" id="camp-body"></div>
    </div>
  </div>

  <script>
    /* ─ Tab switching ─ */
    function switchTab(name) {
      ['retrieval','patching','campaign'].forEach(t => {
        document.getElementById('tab-btn-' + t).classList.toggle('active', t === name);
        document.getElementById('tab-' + t).classList.toggle('active', t === name);
      });
    }

    /* ─ Formatting helpers ─ */
    function fmtF1(v) { return v != null ? v.toFixed(3) : '—'; }
    function fmtPct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
    function fmtAge(m) {
      if (m == null) return '—';
      if (m < 1) return 'just now';
      if (m < 60) return Math.round(m) + 'm ago';
      return Math.round(m / 60) + 'h ago';
    }
    function fmtEta(s) {
      if (!s || s <= 0) return '';
      if (s < 60) return '< 1m';
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return '~' + (h > 0 ? h + 'h ' : '') + m + 'm';
    }
    function fmtElapsed(s) {
      if (s == null) return '';
      if (s < 60) return s.toFixed(0) + 's';
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
    }

    /* ─ Retrieval tab ─ */
    const abbrev = {
      gm_deterministic:'GM-D', gm_progressive:'GM-P', gm_baseline:'GM-B',
      rag_progressive:'RAG-P', rag_baseline:'RAG-B',
      raw_rag_function:'RRF', raw_rag_fixed:'RRX',
      bm25:'BM25', repomap_like:'RPM',
      agentless_like_localization:'AGL', agentic_cold_start:'ACS'
    };

    let prevRetDone = 0, retCompletionRate = null;

    function renderRetrieval(data) {
      const s = data.summary || {}, grid = data.grid || {};
      const repos = data.repos || [], methods = data.methods || [];
      const done = s.n_done || 0, total = s.n_total || 1, inProg = s.n_in_progress || 0;
      const eta = s.eta_seconds;

      // Update ETA from client-side rate tracking
      if (done > prevRetDone) {
        const delta = done - prevRetDone;
        const rate = delta / 10.0;  // cells per second (10s poll interval)
        retCompletionRate = retCompletionRate ? retCompletionRate * 0.7 + rate * 0.3 : rate;
        prevRetDone = done;
      }
      const clientEta = (retCompletionRate && done < total)
        ? Math.round((total - done) / retCompletionRate) : null;
      const displayEta = eta || clientEta;

      const chips = [
        `<span class="chip green">Done ${done}/${total}</span>`,
        inProg > 0 ? `<span class="chip amber">Building ${inProg}</span>` : '',
        total - done - inProg > 0 ? `<span class="chip">Pending ${total - done - inProg}</span>` : '',
        displayEta ? `<span class="chip blue">ETA ${fmtEta(displayEta)}</span>` : '',
      ].join('');
      document.getElementById('ret-chips').innerHTML = chips;

      let html = '<thead><tr>';
      html += '<th class="repo-col">Repo</th>';
      methods.forEach(m => html += `<th title="${m}">${abbrev[m] || m}</th>`);
      html += '</tr></thead><tbody>';
      repos.forEach(repo => {
        const short = repo.split('/')[1];
        html += `<tr><td class="repo-name" title="${repo}">${short}</td>`;
        methods.forEach(m => {
          const cell = (grid[repo] || {})[m] || {status:'pending'};
          const cls = cell.status === 'done' ? 'done' : cell.status === 'in_progress' ? 'in-progress' : 'pending';
          const label = cell.f1 != null ? cell.f1.toFixed(3) : '—';
          const tip = `${repo} / ${m}` + (cell.run_id ? ` [${cell.run_id}]` : '');
          html += `<td class="cell ${cls}" title="${tip}">${label}</td>`;
        });
        html += '</tr>';
      });
      html += '</tbody>';
      document.getElementById('ret-grid').innerHTML = html;
    }

    /* ─ Patching tab ─ */
    function renderPatching(data) {
      const runs = data.runs || [], sum = data.summary || {};
      const sc = sum.status_counts || {};
      const eta = data.eta_seconds;

      const chips = [
        `<span class="chip green">Done ${sc.complete || 0}/${sum.run_count || 0}</span>`,
        (sc.running || 0) > 0 ? `<span class="chip amber">Running ${sc.running}</span>` : '',
        (sc.stalled || 0) > 0 ? `<span class="chip red">Stalled ${sc.stalled}</span>` : '',
        eta ? `<span class="chip blue">ETA ${fmtEta(eta)}</span>` : '',
      ].join('');
      document.getElementById('pat-chips').innerHTML = chips;

      // Group by method
      const byMethod = {};
      runs.forEach(r => {
        const m = r.retrieval_method || 'unknown';
        (byMethod[m] = byMethod[m] || []).push(r);
      });
      // Sort: running first, then alphabetical
      const entries = Object.entries(byMethod).sort((a, b) => {
        const ar = a[1].filter(r => r.status === 'running').length;
        const br = b[1].filter(r => r.status === 'running').length;
        return br - ar || a[0].localeCompare(b[0]);
      });

      if (!entries.length) {
        document.getElementById('pat-body').innerHTML = '<p class="no-data">No runs found for current filters.</p>';
        return;
      }

      let html = '';
      entries.forEach(([method, mrs]) => {
        const nDone = mrs.filter(r => r.status === 'complete').length;
        const nRun  = mrs.filter(r => r.status === 'running').length;
        const nStall= mrs.filter(r => r.status === 'stalled').length;
        const stats = `${nDone}/${mrs.length} done` +
          (nRun ? `, ${nRun} running` : '') +
          (nStall ? `, ${nStall} stalled` : '');
        const openByDefault = nRun > 0;
        html += `<div class="method-group">
          <div class="method-hdr ${openByDefault ? 'open' : ''}" onclick="toggleMethodGroup(this)">
            <span class="method-hdr-name">${method}</span>
            <span class="method-hdr-stats">${stats}</span>
            <span class="chevron">▶</span>
          </div>
          <div class="method-body ${openByDefault ? 'open' : ''}">
            <table class="ptable">
              <thead><tr>
                <th>Repo</th><th>Status</th><th>Progress</th>
                <th>Patched</th><th>Resolved</th><th>Updated</th>
              </tr></thead><tbody>`;
        mrs.sort((a, b) => {
          const rank = {running:0, not_started:1, stalled:2, complete:3};
          return (rank[a.status]??9) - (rank[b.status]??9);
        });
        mrs.forEach(r => {
          const pct = r.progress_pct ?? 0;
          const cls = r.status === 'complete' ? 'done' : '';
          const res = r.n_resolved != null ? r.n_resolved : '—';
          html += `<tr>
            <td>${r.repo_name || '—'}</td>
            <td><span class="badge ${r.status || 'not_started'}">${r.status || 'pending'}</span></td>
            <td>
              ${r.n_completed}/${r.n_instances > 0 ? r.n_instances : '?'}
              <span class="pbar"><span class="pbar-fill ${cls}" style="width:${pct}%"></span></span>
            </td>
            <td>${r.n_patched ?? '—'}</td>
            <td>${res}</td>
            <td class="muted">${fmtAge(r.updated_age_minutes)}</td>
          </tr>`;
        });
        html += '</tbody></table></div></div>';
      });
      document.getElementById('pat-body').innerHTML = html;
    }

    function toggleMethodGroup(hdr) {
      const body = hdr.nextElementSibling;
      const isOpen = body.classList.toggle('open');
      hdr.classList.toggle('open', isOpen);
    }

    /* ─ Campaign tab ─ */
    const stepIcons = { done:'✓', running:'●', failed:'✕', pending:'○' };

    function renderCampaign(data) {
      const campaigns = data.campaigns || [];
      if (!campaigns.length) {
        document.getElementById('camp-body').innerHTML = '<p class="no-data">No campaign state files found in campaigns/ directory.</p>';
        return;
      }
      let html = '';
      campaigns.forEach(camp => {
        if (campaigns.length > 1) html += `<div class="section-label">${camp.campaign_name}</div>`;
        (camp.steps || []).forEach(step => {
          const icon = stepIcons[step.status] || '○';
          const t = step.elapsed_s ? fmtElapsed(step.elapsed_s) : (step.status === 'running' ? '…' : '');
          html += `<div class="cstep">
            <div class="cstep-icon ${step.status || 'pending'}">${icon}</div>
            <div style="flex:1">
              <div class="cstep-name">${step.name}</div>
              ${step.description ? `<div class="cstep-desc">${step.description}</div>` : ''}
            </div>
            <div class="cstep-time">${t}</div>
          </div>`;
        });
      });
      document.getElementById('camp-body').innerHTML = html;
    }

    /* ─ Polling ─ */
    async function tick() {
      const activeOnly = document.getElementById('chkActive').checked;
      const inclComplete = document.getElementById('chkComplete').checked;
      const inclStale = document.getElementById('chkStale').checked;
      const qs = `active_only=${activeOnly?1:0}&include_complete=${inclComplete?1:0}&include_stale=${inclStale?1:0}`;

      try {
        const [retData, patData, campData] = await Promise.all([
          fetch('/api/retrieval_status').then(r => r.json()),
          fetch('/api/status?' + qs).then(r => r.json()),
          fetch('/api/campaign_status').then(r => r.json()),
        ]);
        renderRetrieval(retData);
        renderPatching(patData);
        renderCampaign(campData);

        const anyRunning = (patData.runs || []).some(r => r.status === 'running');
        const dot = document.getElementById('liveDot');
        dot.className = 'live-dot ' + (anyRunning ? 'active' : '');
        document.getElementById('headerTs').textContent = 'Updated ' + new Date().toLocaleTimeString();
      } catch (e) {
        document.getElementById('liveDot').className = 'live-dot idle';
        document.getElementById('headerTs').textContent = 'Poll error';
      }
    }

    ['chkActive','chkComplete','chkStale'].forEach(id =>
      document.getElementById(id).addEventListener('change', tick));
    tick();
    setInterval(tick, 10000);
  </script>
</body>
</html>
"""


def _make_handler(
    results_root: Path,
    stale_after_minutes: float,
    manifest_list_path: Path | None,
    campaigns_dir: Path,
    target_repos: list[str],
    target_methods: list[str],
):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)

            if parsed.path == "/":
                body = _HTML.encode("utf-8")
                self._respond(HTTPStatus.OK, "text/html; charset=utf-8", body)
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
                all_runs = collect_dashboard_status(
                    results_root,
                    stale_after_minutes=stale_after_minutes,
                    active_only=False, include_complete=True, include_stale=True,
                )
                summary_plan = (
                    load_manifest_plan_summary(manifest_list_path, root_dir=ROOT)
                    if manifest_list_path else None
                )
                payload = {
                    "results_root": str(results_root),
                    "run_count": len(runs),
                    "summary": summarize_dashboard_runs(runs),
                    "summary_visible": summarize_dashboard_runs(runs),
                    "summary_started": summarize_dashboard_runs(all_runs),
                    "summary_plan": summary_plan,
                    "runs": runs,
                }
                self._json(payload)
                return

            if parsed.path == "/api/retrieval_status":
                status = build_retrieval_status(results_root, target_repos, target_methods)
                self._json(status)
                return

            if parsed.path == "/api/campaign_status":
                campaigns = load_campaign_state(campaigns_dir)
                self._json({"campaigns": campaigns})
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def _respond(self, status, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._respond(HTTPStatus.OK, "application/json", body)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return  # suppress per-request logging

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="GraphManager V2 campaign dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5051)
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--stale-after-minutes", type=float, default=15.0)
    parser.add_argument("--manifest-list", default=None)
    parser.add_argument("--campaigns-dir", default="campaigns",
                        help="Directory to scan for *_state.json campaign files (default: campaigns/)")
    args = parser.parse_args()

    results_root = (ROOT / args.results_root).resolve()
    manifest_list_path = Path(args.manifest_list).resolve() if args.manifest_list else None
    campaigns_dir = (ROOT / args.campaigns_dir).resolve()

    handler_cls = _make_handler(
        results_root=results_root,
        stale_after_minutes=args.stale_after_minutes,
        manifest_list_path=manifest_list_path,
        campaigns_dir=campaigns_dir,
        target_repos=_V2_REPOS,
        target_methods=_V2_METHODS,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"Dashboard  →  http://{args.host}:{args.port}")
    print(f"Results    →  {results_root}")
    print(f"Campaigns  →  {campaigns_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
