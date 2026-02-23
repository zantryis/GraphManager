"""
profile_runs.py — Analyze where time and tokens go across retrieval runs.

Reads existing results/runs/*/summary.json and detailed_results.json.
Produces a breakdown of setup cost, runtime cost, and agent behavior.

Usage:
    ./.venv/bin/python tools/profile_runs.py
    ./.venv/bin/python tools/profile_runs.py --run-id 20260222_033353
    ./.venv/bin/python tools/profile_runs.py --repo yt-dlp
"""

import argparse
import json
import os
import glob
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results" / "runs"

METHODS = [
    "gm_deterministic",
    "gm_progressive",
    "gm_baseline",
    "rag_progressive",
    "rag_baseline",
    "raw_rag_function",
    "raw_rag_fixed",
]

METHOD_LABELS = {
    "gm_deterministic": "GM-det   ",
    "gm_progressive":   "GM-prog  ",
    "gm_baseline":      "GM-base  ",
    "rag_progressive":  "RAG-prog ",
    "rag_baseline":     "RAG-base ",
    "raw_rag_function": "raw-func ",
    "raw_rag_fixed":    "raw-fixed",
}


def load_runs(run_id_filter=None, repo_filter=None):
    pattern = str(RESULTS_DIR / "*/summary.json")
    summaries = glob.glob(pattern)
    runs = []
    for path in sorted(summaries):
        run_dir = os.path.dirname(path)
        run_id = os.path.basename(run_dir)
        if run_id_filter and run_id != run_id_filter:
            continue
        detail_path = os.path.join(run_dir, "detailed_results.json")
        try:
            with open(path) as f:
                summary = json.load(f)
            detail = None
            if os.path.exists(detail_path):
                with open(detail_path) as f:
                    detail = json.load(f)
            meta = summary.get("_meta", {})
            repo = meta.get("repo_name", "unknown")
            if repo_filter and repo_filter not in repo:
                continue
            runs.append({
                "run_id": run_id,
                "path": run_dir,
                "summary": summary,
                "detail": detail,
                "meta": meta,
                "repo": repo,
                "track": meta.get("evaluation_track", "unknown"),
                "n_issues": meta.get("n_issues_evaluated", 0),
            })
        except Exception as e:
            print(f"  [skip] {path}: {e}")
    return runs


def fmt_k(n):
    if n is None:
        return "    —    "
    return f"{n/1000:8.1f}K"


def fmt_s(n):
    if n is None:
        return "   —   "
    return f"{n:7.1f}s"


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def subsection(title):
    print()
    print(f"  --- {title} ---")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Token cost breakdown per method (aggregated across selected runs)
# ─────────────────────────────────────────────────────────────────────────────

def report_token_breakdown(runs):
    section("TOKEN COST BREAKDOWN (per method, per issue average)")

    # Aggregate per method across all runs
    agg = defaultdict(lambda: {
        "setup_tok": [], "llm_tok": [], "query_tok": [],
        "total_tok": [], "f1": [], "setup_time_s": [], "n_issues": [],
    })

    for run in runs:
        s = run["summary"]
        n = run["n_issues"]
        for method in METHODS:
            if method not in s:
                continue
            m = s[method]
            n_iss = m.get("n_issues", n) or 1
            agg[method]["setup_tok"].append(m.get("setup_embedding_tokens", 0))
            agg[method]["llm_tok"].append(m.get("total_llm_tokens", 0) / n_iss)
            agg[method]["query_tok"].append(m.get("total_query_embedding_tokens", 0) / n_iss)
            agg[method]["total_tok"].append(m.get("avg_total_cost_tokens_per_issue_unamortized_setup", 0))
            agg[method]["f1"].append(m.get("mean_f1", 0))
            if m.get("setup_time_s"):
                agg[method]["setup_time_s"].append(m["setup_time_s"])
            agg[method]["n_issues"].append(n_iss)

    def avg(lst):
        return sum(lst) / len(lst) if lst else None

    print(f"\n  {'Method':<12} {'Setup(K)':<10} {'LLM/iss(K)':<12} {'Qry/iss(K)':<12} {'Total/iss(K)':<14} {'Setup(s)':<10} {'F1':<6}")
    print(f"  {'-'*12} {'-'*10} {'-'*12} {'-'*12} {'-'*14} {'-'*10} {'-'*6}")
    for method in METHODS:
        d = agg[method]
        if not d["setup_tok"]:
            continue
        print(f"  {METHOD_LABELS[method]:<12} "
              f"{fmt_k(avg(d['setup_tok']))} "
              f"{fmt_k(avg(d['llm_tok']))} "
              f"{fmt_k(avg(d['query_tok']))} "
              f"{fmt_k(avg(d['total_tok']))} "
              f"{fmt_s(avg(d['setup_time_s']) if d['setup_time_s'] else None)} "
              f"{avg(d['f1']):.3f}")

    print()
    print("  Notes:")
    print("  - Setup tokens: one-time index build cost (amortized over n_issues in same-snapshot)")
    print("  - LLM/iss:      prompt+candidate tokens per issue (LLM-guided methods only)")
    print("  - Qry/iss:      query embedding tokens per issue (semantic search calls)")
    print("  - Total/iss:    unamortized — includes full setup per issue")
    print("  - Setup(s):     wall-clock for index build (no per-phase breakdown currently)")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Agent behavior: tool call distribution and stop reasons
# ─────────────────────────────────────────────────────────────────────────────

def report_agent_behavior(runs):
    section("AGENT BEHAVIOR (tool calls and stop reasons per issue)")

    agentic_methods = ["gm_progressive", "gm_baseline", "rag_progressive", "rag_baseline"]

    # Collect per-issue stats
    per_method = defaultdict(lambda: {
        "tool_calls": [],
        "tool_by_name": defaultdict(list),
        "cache_hits": [],
        "stop_reasons": defaultdict(int),
        "prompt_tokens": [],
        "candidate_tokens": [],
    })

    for run in runs:
        if not run["detail"]:
            continue
        for issue in run["detail"]:
            for method in agentic_methods:
                if method not in issue.get("methods", {}):
                    continue
                m = issue["methods"][method]
                tok = m.get("tokens", {})
                total_calls = tok.get("tool_calls", 0)
                cache_hits = tok.get("tool_cache_hits", 0)
                stop = tok.get("stop_reason", "unknown")
                by_name = tok.get("tool_calls_by_name", {})

                d = per_method[method]
                d["tool_calls"].append(total_calls)
                d["cache_hits"].append(cache_hits)
                d["stop_reasons"][stop] += 1
                d["prompt_tokens"].append(tok.get("prompt_tokens", 0))
                d["candidate_tokens"].append(tok.get("candidate_tokens", 0))
                for name, count in by_name.items():
                    d["tool_by_name"][name].append(count)

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    for method in agentic_methods:
        d = per_method[method]
        if not d["tool_calls"]:
            continue
        n = len(d["tool_calls"])
        subsection(f"{method} (n={n} issues)")
        print(f"    avg tool calls/issue:    {avg(d['tool_calls']):.1f}  "
              f"(cache hits: {avg(d['cache_hits']):.1f})")
        print(f"    avg prompt tokens/issue: {avg(d['prompt_tokens']):,.0f}")
        print(f"    avg output tokens/issue: {avg(d['candidate_tokens']):,.0f}")
        print(f"    tool breakdown (avg calls/issue):")
        all_tools = sorted(set(k for issue_counts in [d["tool_by_name"]] for k in issue_counts))
        for tool in all_tools:
            counts = d["tool_by_name"][tool]
            print(f"      {tool:<25} {avg(counts):.1f}  (over {len(counts)} issues with this tool)")
        print(f"    stop reasons:")
        for reason, count in sorted(d["stop_reasons"].items(), key=lambda x: -x[1]):
            pct = 100 * count / n
            print(f"      {reason:<30} {count:3d} ({pct:.0f}%)")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Per-run setup time vs. repo size proxy (setup tokens)
# ─────────────────────────────────────────────────────────────────────────────

def report_setup_scaling(runs):
    section("SETUP COST SCALING (wall-clock time vs embedding tokens)")

    print(f"\n  {'Run ID':<22} {'Repo':<35} {'Track':<16} {'N':<4} "
          f"{'GM setup(K)':<13} {'RAG setup(K)':<14} {'GM time(s)':<12} {'RAG time(s)'}")
    print(f"  {'-'*22} {'-'*35} {'-'*16} {'-'*4} {'-'*13} {'-'*14} {'-'*12} {'-'*11}")

    for run in sorted(runs, key=lambda r: r["repo"]):
        s = run["summary"]
        gm = s.get("gm_progressive", {})
        rag = s.get("rag_progressive", {})
        gm_setup_tok = gm.get("setup_embedding_tokens", 0)
        rag_setup_tok = rag.get("setup_embedding_tokens", 0)
        gm_time = gm.get("setup_time_s")
        rag_time = rag.get("setup_time_s")
        print(f"  {run['run_id']:<22} {run['repo']:<35} {run['track']:<16} {run['n_issues']:<4} "
              f"{fmt_k(gm_setup_tok)} "
              f"{fmt_k(rag_setup_tok)} "
              f"{fmt_s(gm_time)} "
              f"{fmt_s(rag_time)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Per-issue token variance — who's expensive?
# ─────────────────────────────────────────────────────────────────────────────

def report_per_issue_variance(runs):
    section("PER-ISSUE TOKEN VARIANCE (runtime tokens, excluding setup)")

    agentic = ["gm_progressive", "rag_progressive"]

    per_method = defaultdict(list)
    for run in runs:
        if not run["detail"]:
            continue
        for issue in run["detail"]:
            iid = issue.get("instance_id", "?")
            for method in agentic:
                if method not in issue.get("methods", {}):
                    continue
                m = issue["methods"][method]
                tok = m.get("tokens", {})
                total = tok.get("total_tokens", 0) + tok.get("query_embedding_tokens", 0)
                tool_calls = tok.get("tool_calls", 0)
                stop = tok.get("stop_reason", "?")
                f1 = m.get("metrics", {}).get("f1", 0)
                per_method[method].append({
                    "iid": iid, "tokens": total, "tool_calls": tool_calls,
                    "stop": stop, "f1": f1
                })

    for method in agentic:
        issues = per_method[method]
        if not issues:
            continue
        issues_sorted = sorted(issues, key=lambda x: -x["tokens"])
        total_tok = [i["tokens"] for i in issues]
        avg_tok = sum(total_tok) / len(total_tok) if total_tok else 0
        subsection(f"{method} — top 5 most expensive issues (by runtime tokens)")
        print(f"    avg runtime tokens/issue: {avg_tok:,.0f}")
        print(f"    {'instance_id':<45} {'tokens':>8}  {'tool_calls':>10}  {'stop':<20}  {'F1'}")
        print(f"    {'-'*45} {'-'*8}  {'-'*10}  {'-'*20}  {'-'*5}")
        for i in issues_sorted[:5]:
            print(f"    {i['iid']:<45} {i['tokens']:>8,}  {i['tool_calls']:>10}  {i['stop']:<20}  {i['f1']:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. What we can't see — instrumentation gaps
# ─────────────────────────────────────────────────────────────────────────────

def report_gaps():
    section("INSTRUMENTATION GAPS (what's still dark)")
    print("""
  The following are NOT captured in current run outputs:

  1. Setup time breakdown — setup_time_s is total wall-clock for the full index
     build phase, but we can't see:
       a) time in tree-sitter parsing (local, CPU-bound)
       b) time in Gemini embedding API calls (network-bound)
       c) time in FAISS index construction (local)
     Recommended probe: add time.time() around each sub-phase in
     GraphIndex.build() (graph_builder.py ~line 431) and RAGIndex.build()
     (rag_baseline.py ~line 105).

  2. Per-issue wall-clock time for retrieval — we have token counts per issue
     but not how long each issue took in seconds. For LLM-guided methods, this
     is dominated by API latency per turn. For deterministic, it's local.
     Recommended probe: wrap find_relevant_files() calls in evaluation.py
     with time.time() and store as issue_wall_clock_s in detailed_results.

  3. LLM API latency per turn — we have total LLM tokens per issue but not
     how long each turn took. High-variance issues (many tokens, many turns)
     may have disproportionate wall-clock cost from model latency.
     Recommended probe: record turn_start/turn_end in manager_agent.py's
     tool-calling loop.

  4. Tree-sitter parse time per file — for large repos (sympy, LangChain),
     parsing may be the dominant setup cost. Currently invisible.
     Recommended probe: time _parse_file() in graph_builder.py per file,
     log top-10 slowest files.

  5. Harness wall-clock (patching) — the SWE-bench Docker harness is likely
     a major time sink in patch runs but isn't tracked separately from the
     instance_wall_clock_cap_s ceiling.
  """)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Quick recommendations
# ─────────────────────────────────────────────────────────────────────────────

def report_recommendations():
    section("QUICK PROFILING ADDITIONS (to answer the dark questions)")
    print("""
  To fill the gaps above without changing external interfaces:

  A) SETUP TIME SPLIT — add to graph_builder.py GraphIndex.build():
     t0 = time.time()
     # ... tree-sitter parsing ...
     t_parse = time.time()
     # ... embedding API calls ...
     t_embed = time.time()
     # ... FAISS construction ...
     t_faiss = time.time()
     return {"parse_s": t_parse-t0, "embed_s": t_embed-t_parse, "faiss_s": t_faiss-t_embed}
     Store in summary under setup_time_breakdown.

  B) PER-ISSUE WALL-CLOCK — wrap in evaluation.py ~line 726:
     t0 = time.time()
     result = method.find_relevant_files(issue)
     result["wall_clock_s"] = time.time() - t0

  C) TURN-LEVEL LATENCY — in manager_agent.py's tool-calling loop, store
     turn timestamps in manager_telemetry. This directly answers
     "how much of LLM runtime is API wait vs. local processing?"

  D) FILE-LEVEL PARSE TIME — in graph_builder._parse_file(), time each file
     and log the top-10 slowest to a debug file. One-line addition:
     if elapsed > 0.5: logger.debug(f"slow parse: {path} {elapsed:.2f}s")
  """)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Profile GraphManager retrieval runs")
    parser.add_argument("--run-id", help="Filter to specific run ID")
    parser.add_argument("--repo", help="Filter to runs containing this repo name substring")
    parser.add_argument("--section", choices=["tokens", "agent", "setup", "variance", "gaps", "all"],
                        default="all", help="Which section to show")
    args = parser.parse_args()

    runs = load_runs(run_id_filter=args.run_id, repo_filter=args.repo)
    if not runs:
        print(f"No runs found in {RESULTS_DIR}")
        return

    print(f"\nLoaded {len(runs)} run(s)")
    for r in runs:
        print(f"  {r['run_id']}  {r['repo']:<35}  {r['track']:<20}  n={r['n_issues']}")

    show = args.section
    if show in ("tokens", "all"):
        report_token_breakdown(runs)
    if show in ("agent", "all"):
        report_agent_behavior(runs)
    if show in ("setup", "all"):
        report_setup_scaling(runs)
    if show in ("variance", "all"):
        report_per_issue_variance(runs)
    if show in ("gaps", "all"):
        report_gaps()
        report_recommendations()


if __name__ == "__main__":
    main()
