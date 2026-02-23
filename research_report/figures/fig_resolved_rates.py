"""Figure 1: Grouped horizontal bar chart — patching pilot resolved rates by repo.

Data source: locked numbers from dev_logs/2026-02-22-reruns-complete-final-lock.md
and 05_results.tex tab:patching_resolved.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Data ───────────────────────────────────────────────────────────────────
repos = [
    "astropy (n=12)",
    "matplotlib (n=12)",
    "flask (n=1)",
    "requests (n=8)",
    "xarray (n=12)",
    "pytest (n=19)",
    "scikit-learn (n=12)",
    "sphinx (n=12)",
    "sympy (n=12)",
    "Pooled (N=100)",
]

oracle  = [0.500, 0.167, 1.000, 0.625, 0.500, 0.368, 0.500, 0.333, 0.667, 0.450]
gm      = [0.500, 0.250, 1.000, 0.500, 0.417, 0.526, 0.500, 0.167, 0.500, 0.430]
rag     = [0.417, 0.083, 0.000, 0.500, 0.583, 0.421, 0.417, 0.250, 0.417, 0.380]
none_b  = [0.000, 0.083, 0.000, 0.125, 0.000, 0.053, 0.000, 0.000, 0.000, 0.030]

n = len(repos)
y = np.arange(n)
bar_h = 0.18

# ── Colors ─────────────────────────────────────────────────────────────────
C_ORACLE = "#2166ac"
C_GM     = "#4dac26"
C_RAG    = "#d01c8b"
C_NONE   = "#999999"

# ── Plot ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6.5, 4.2))

offsets = [-1.5, -0.5, 0.5, 1.5]
datasets = [oracle, gm, rag, none_b]
colors = [C_ORACLE, C_GM, C_RAG, C_NONE]
labels = ["Oracle", "GM-progressive", "RAG-progressive", "None"]

for vals, off, col, lbl in zip(datasets, offsets, colors, labels):
    bars = ax.barh(y + off * bar_h, vals, bar_h * 0.95,
                   color=col, alpha=0.88, label=lbl)

# Emphasise pooled row with a light separator
ax.axhline(y=n - 1 - 0.5, color="black", linewidth=0.8, linestyle="--", alpha=0.4)

ax.set_yticks(y)
ax.set_yticklabels(repos, fontsize=8.5)
ax.set_xlabel("Resolved rate (pass@1)", fontsize=9)
ax.set_xlim(0, 1.08)
ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=1, decimals=0))
ax.tick_params(axis="x", labelsize=8)

# Bold pooled row label
labels_objs = ax.get_yticklabels()
labels_objs[-1].set_fontweight("bold")

ax.legend(loc="lower right", fontsize=8, framealpha=0.85,
          handles=[mpatches.Patch(color=c, label=l)
                   for c, l in zip(colors, labels)])
ax.set_title("Patching Pilot: Resolved Rates by Repository", fontsize=9, pad=6)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig("fig_resolved_rates.pdf", bbox_inches="tight", dpi=150)
print("Saved fig_resolved_rates.pdf")
