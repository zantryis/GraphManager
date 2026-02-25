"""Figure 3: Scatter — per-method mean F1 vs per-issue cost (log scale).

Data source: 05_results.tex tab:main_results (F1) + tab:cost_cross_repo (costs).
Three completed SWE-bench repos: Flask, Requests, Pytest (30 issues total, single run).
Per-issue cost = total_cost / n_issues.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Data: (method, repo, mean_f1, total_cost_tokens, n_issues) ─────────────
# Costs from tab:cost_cross_repo (30 issues total, 3 repos).
# Per-method per-repo F1 from tab:main_results.
# Per-issue cost is total / 30 (equal share for single-run cross-repo aggregate).
# Individual per-repo costs are estimated pro-rata (setup distributed evenly across repos).

# Setup token costs (shared across all 30 issues)
setup = {
    "gm":       701_054,
    "rag_func":  2_268_044,
    "rag_fixed": 1_478_791,
}
# Runtime token costs (total across 30 issues)
runtime = {
    "gm_det":   5_404,
    "gm_prog": 297_690,
    "gm_base": 333_893,
    "rag_prog": 123_317,
    "rag_base": 354_930,
    "raw_func":  12_769,
    "raw_fixed": 12_769,
}

# Method → (label, family, marker, color)
METHOD_STYLE = {
    "gm_det":   ("GM-det",   "graph", "D", "#1a9641"),
    "gm_prog":  ("GM-prog",  "graph", "o", "#1a9641"),
    "gm_base":  ("GM-base",  "graph", "s", "#1a9641"),
    "rag_prog": ("RAG-prog", "rag",   "o", "#d73027"),
    "rag_base": ("RAG-base", "rag",   "s", "#d73027"),
    "raw_func": ("Raw-func", "raw",   "^", "#984ea3"),
    "raw_fixed":("Raw-fixed","raw",   "v", "#984ea3"),
}

# Mean F1 per method per repo (strict track)
f1_data = {
    "gm_det":   {"Flask": 0.679, "Requests": 0.520, "Pytest": 0.473},
    "gm_prog":  {"Flask": 0.803, "Requests": 0.700, "Pytest": 0.550},
    "gm_base":  {"Flask": 0.809, "Requests": 0.534, "Pytest": 0.473},
    "rag_prog": {"Flask": 0.704, "Requests": 0.733, "Pytest": 0.602},
    "rag_base": {"Flask": 0.802, "Requests": 0.733, "Pytest": 0.567},
    "raw_func": {"Flask": 0.340, "Requests": 0.256, "Pytest": 0.242},
    "raw_fixed":{"Flask": 0.321, "Requests": 0.221, "Pytest": 0.185},
}

# Setup cost per repo (1/3 of total setup)
setup_per_repo = {k: v / 3 for k, v in setup.items()}
# Runtime per repo (approximate 1/3 of total — single-run, roughly balanced)
runtime_per_repo = {k: v / 3 for k, v in runtime.items()}

method_setup_key = {
    "gm_det":    "gm",
    "gm_prog":   "gm",
    "gm_base":   "gm",
    "rag_prog":  "rag_func",
    "rag_base":  "rag_func",
    "raw_func":  "rag_func",
    "raw_fixed": "rag_fixed",
}

# ── Plot ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6.5, 3.6))

repos = ["Flask", "Requests", "Pytest"]
repo_alpha = {"Flask": 1.0, "Requests": 0.8, "Pytest": 0.6}
repo_size  = {"Flask": 80,  "Requests": 80,  "Pytest": 80}

legend_handles = {}

for method, (label, family, marker, color) in METHOD_STYLE.items():
    setup_key = method_setup_key[method]
    for repo in repos:
        f1 = f1_data[method][repo]
        cost = setup_per_repo[setup_key] + runtime_per_repo[method]
        sc = ax.scatter(
            cost, f1,
            marker=marker, color=color,
            s=repo_size[repo], alpha=repo_alpha[repo],
            edgecolors="white", linewidths=0.5,
            zorder=3,
        )
    if label not in legend_handles:
        legend_handles[label] = ax.scatter(
            [], [], marker=marker, color=color, s=70,
            label=label, edgecolors="white", linewidths=0.5,
        )

ax.set_xscale("log")
ax.set_xlabel("Per-issue cost (tokens, log scale)", fontsize=9)
ax.set_ylabel("Mean F1 (strict track)", fontsize=9)
ax.tick_params(labelsize=8)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
    lambda v, _: f"{int(v):,}"
))

# Cluster annotations
ax.text(6_000, 0.61, "GM cluster\n(low cost)", ha="center", va="bottom",
        fontsize=7.5, color="#1a9641",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#1a9641", alpha=0.7))
ax.text(75_000, 0.66, "RAG cluster\n(high cost)", ha="center", va="bottom",
        fontsize=7.5, color="#d73027",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#d73027", alpha=0.7))

ax.legend(handles=list(legend_handles.values()),
          loc="lower right", fontsize=7.5, ncol=2, framealpha=0.85)
ax.set_title("Retrieval F1 vs. Per-Issue Cost (Flask / Requests / Pytest)", fontsize=9, pad=5)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, which="both", ls=":", alpha=0.35)

plt.tight_layout()
plt.savefig("fig_retrieval_f1_cost.pdf", bbox_inches="tight", dpi=150)
print("Saved fig_retrieval_f1_cost.pdf")
