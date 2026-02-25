"""Figure 2: Log-scale bar chart — cost-per-resolved-issue (CPR) comparison.

Data source: locked numbers from dev_logs/2026-02-22-reruns-complete-final-lock.md.
Two views: method-accounted and as-run-consumed.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── Data ───────────────────────────────────────────────────────────────────
methods = ["Oracle", "GM-prog", "RAG-prog", "None"]

cpr_method  = [33_594,   479_354,  2_115_746,  24_291]
cpr_asrun   = [33_594, 1_250_676,  2_319_677,  24_291]

x = np.arange(len(methods))
w = 0.32

C_MA = "#4575b4"   # method-accounted: blue
C_AR = "#d73027"   # as-run: red

# ── Plot ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(3.25, 2.8))

b1 = ax.bar(x - w/2, cpr_method, w, label="Method-accounted", color=C_MA, alpha=0.88)
b2 = ax.bar(x + w/2, cpr_asrun,  w, label="As-run-consumed",  color=C_AR, alpha=0.88)

ax.set_yscale("log")
ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=8)
ax.set_ylabel("Tokens per resolved issue (log)", fontsize=7.5)
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
ax.tick_params(axis="y", labelsize=7)

# Annotate 4.4× ratio arrow between GM and RAG (method-accounted)
gm_val  = cpr_method[1]
rag_val = cpr_method[2]
ax.annotate(
    "",
    xy=(2 - w/2, rag_val * 0.9),
    xytext=(1 - w/2, gm_val * 1.05),
    arrowprops=dict(arrowstyle="<->", color="black", lw=1.2),
)
ax.text(1.5 - w/2, (gm_val * rag_val) ** 0.5 * 1.3,
        r"$4.4\times$", ha="center", va="bottom", fontsize=7.5, fontweight="bold")

ax.legend(fontsize=7, loc="upper left", framealpha=0.85)
ax.set_title("Cost per Resolved Issue", fontsize=8.5, pad=5)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig("fig_cpr_comparison.pdf", bbox_inches="tight", dpi=150)
print("Saved fig_cpr_comparison.pdf")
