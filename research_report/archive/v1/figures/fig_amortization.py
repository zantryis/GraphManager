"""Figure 4: Strict vs same-snapshot cost comparison with F1 overlay.

Data source: 05_results.tex tab:amortization (psf/requests, n=10).
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Data (psf/requests, tab:amortization) ──────────────────────────────────
methods = ["GM-prog", "GM-det", "RAG-prog"]

strict_cost  = [150_840, 109_284, 429_669]
snap_cost    = [ 51_154,  10_745,  52_081]
strict_f1    = [0.467,    0.520,   0.286]
snap_f1      = [0.544,    0.603,   0.259]

x = np.arange(len(methods))
w = 0.32

C_STRICT = "#4575b4"
C_SNAP   = "#74add1"

# ── Plot ───────────────────────────────────────────────────────────────────
fig, ax1 = plt.subplots(figsize=(3.25, 2.9))

b1 = ax1.bar(x - w/2, strict_cost, w, label="Strict",        color=C_STRICT, alpha=0.88)
b2 = ax1.bar(x + w/2, snap_cost,   w, label="Same-snapshot", color=C_SNAP,   alpha=0.88)

ax1.set_ylabel("Total cost (tokens)", fontsize=8, color="black")
ax1.set_xticks(x)
ax1.set_xticklabels(methods, fontsize=8)
ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
    lambda v, _: f"{int(v/1000)}K"
))
ax1.tick_params(axis="y", labelsize=7.5)
ax1.set_ylim(0, 500_000)

# F1 overlay
ax2 = ax1.twinx()
ax2.plot(x - w/2, strict_f1, "D-", color=C_STRICT, lw=1.4, ms=5, zorder=5,
         label="F1 Strict")
ax2.plot(x + w/2, snap_f1,   "o--", color=C_SNAP,   lw=1.4, ms=5, zorder=5,
         label="F1 Same-snap")
ax2.set_ylabel("Mean F1", fontsize=8, color="#555555")
ax2.set_ylim(0, 0.85)
ax2.tick_params(axis="y", labelsize=7.5, labelcolor="#555555")
ax2.spines["right"].set_color("#555555")

# Reduction factor annotations
for i, (s, n_) in enumerate(zip(strict_cost, snap_cost)):
    ratio = s / n_
    ax1.text(i, max(s, n_) + 12_000, f"{ratio:.1f}×\nreduc.", ha="center",
             va="bottom", fontsize=6.5, color="black")

# Legend
bars_leg = [
    matplotlib.patches.Patch(color=C_STRICT, label="Cost: Strict"),
    matplotlib.patches.Patch(color=C_SNAP,   label="Cost: Same-snap"),
    matplotlib.lines.Line2D([0], [0], color=C_STRICT, marker="D", ms=4,
                             linestyle="-",  label="F1: Strict"),
    matplotlib.lines.Line2D([0], [0], color=C_SNAP,   marker="o", ms=4,
                             linestyle="--", label="F1: Same-snap"),
]
ax1.legend(handles=bars_leg, fontsize=6, loc="upper right",
           framealpha=0.85, ncol=2)

ax1.set_title("Amortization: psf/requests (n=10)", fontsize=8.5, pad=5)
ax1.spines["top"].set_visible(False)
ax2.spines["top"].set_visible(False)

plt.tight_layout()
plt.savefig("fig_amortization.pdf", bbox_inches="tight", dpi=150)
print("Saved fig_amortization.pdf")
