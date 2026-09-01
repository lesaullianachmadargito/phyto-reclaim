# -*- coding: utf-8 -*-
"""Generate Figure 5 of the paper: annual economic build-up and cumulative
discounted cash flow.

This figure is missing from the submitted PDF — only its caption renders.
Building it from the model means that if a number changes, the figure is
regenerated rather than redrawn by hand.

    python figure5.py

Outputs figure5.png (300 dpi, ready to paste into Word) and figure5.pdf (vector).
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from phyto_model import Assumptions, evaluate, MILLION

# Palette follows the paper: navy for section headings, teal for sub-headings.
NAVY = "#17365D"
TEAL = "#1C8C87"
RED = "#B3352F"
GREY = "#8A949A"
RULE = "#C8CFD2"


def _n(x, d=0):
    return f"{x:,.{d}f}"


def build_figure5(a: Assumptions | None = None):
    a = a or Assumptions()
    r = evaluate(a)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(9.4, 3.9),
        gridspec_kw={"width_ratios": [1, 1.15], "wspace": 0.3})

    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(RULE)
        ax.tick_params(colors=GREY, labelsize=8.5, length=3)

    # ------------- panel (a): annual economic build-up -------------
    product = r["product_revenue"] / MILLION
    disposal = r["disposal_avoided"] / MILLION
    opex = a.opex / MILLION
    net = r["net_benefit"] / MILLION

    labels = ["Product\nvalue", "Disposal\navoided", "OPEX", "Net\nbenefit"]
    bottoms = [0, product, net, 0]
    heights = [product, disposal, opex, net]
    colours = [TEAL, TEAL, RED, NAVY]

    for i, (b, h, c) in enumerate(zip(bottoms, heights, colours)):
        ax1.bar(i, h, bottom=b, color=c, width=0.6, zorder=3)
        sign = "−" if c == RED else "+" if i < 2 else ""
        ax1.text(i, b + h + 20, f"{sign}{_n(h, 1)}", ha="center", va="bottom",
                 fontsize=9.5, color=c, fontweight="bold", zorder=4)

    # dotted connectors carry the eye from one bar to the next
    for x0, y in ((0, product), (1, product + disposal), (2, net)):
        ax1.plot([x0 + 0.30, x0 + 0.70], [y, y], color=GREY, lw=0.9,
                 ls=":", zorder=2)

    ax1.set_xticks(range(4))
    ax1.set_xticklabels(labels, fontsize=8.8, color="#333")
    ax1.set_ylabel("IDR million per year", fontsize=9, color="#333")
    ax1.set_ylim(0, max(product + disposal, net) * 1.24)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _n(v)))
    ax1.set_title("(a) Annual economic build-up", fontsize=10, color=NAVY,
                  fontweight="bold", pad=10)

    # ------------- panel (b): cumulative discounted cash flow -------------
    cum = r["cumulative"] / MILLION
    years = list(range(0, a.life + 1))

    ax2.axhline(0, color="#333", lw=1.0, zorder=3)
    ax2.plot(years, cum, color=NAVY, lw=2.0, marker="o", ms=4.2,
             mfc="white", mec=NAVY, mew=1.4, zorder=4)
    ax2.fill_between(years, cum, 0, where=[c < 0 for c in cum],
                     color=RED, alpha=0.10, zorder=1)
    ax2.fill_between(years, cum, 0, where=[c >= 0 for c in cum],
                     color=TEAL, alpha=0.13, zorder=1)

    # discounted breakeven: linear interpolation at the zero crossing
    crossing = None
    for i in range(1, len(cum)):
        if cum[i - 1] < 0 <= cum[i]:
            crossing = (i - 1) + (-cum[i - 1]) / (cum[i] - cum[i - 1])
            break
    if crossing is not None:
        ax2.axvline(crossing, color=RED, lw=1.1, ls="--", zorder=2)
        # placed in the empty lower-right quadrant so it never crosses the curve
        ax2.annotate(f"discounted breakeven {_n(crossing, 1)} yr\n"
                     f"(simple payback {_n(r['payback'], 1)} yr)",
                     xy=(crossing, 0), xytext=(crossing + 0.55, cum[0] * 0.42),
                     fontsize=8.2, color=RED, ha="left", va="center",
                     arrowprops=dict(arrowstyle="-", color=RED, lw=0.8,
                                     connectionstyle="arc3,rad=-0.15"))

    ax2.text(a.life, cum[-1], f"  NPV {_n(cum[-1])}", fontsize=9.5,
             color=NAVY, fontweight="bold", va="center", ha="left")

    ax2.set_xlabel("Year", fontsize=9, color="#333")
    ax2.set_ylabel("Cumulative discounted (IDR million)", fontsize=9, color="#333")
    ax2.set_xticks(years)
    ax2.set_xlim(-0.35, a.life + 1.6)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _n(v)))
    ax2.set_title("(b) Cumulative discounted cash flow", fontsize=10,
                  color=NAVY, fontweight="bold", pad=10)

    fig.text(0.5, -0.02,
             f"Basis: installed CAPEX IDR {_n(a.capex / MILLION, 1)} million  ·  "
             f"{_n(a.discount_rate * 100)}% discount  ·  {a.life} years  ·  "
             f"no residual value  ·  no carbon revenue",
             ha="center", fontsize=8, color=GREY, style="italic")

    fig.tight_layout()
    return fig


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = Assumptions()
    r = evaluate(a)
    fig = build_figure5(a)
    fig.savefig("figure5.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig("figure5.pdf", bbox_inches="tight", facecolor="white")
    print("Saved: figure5.png (300 dpi) and figure5.pdf")
    print(f"  Net benefit : IDR {_n(r['net_benefit'] / MILLION, 1)} million/year")
    print(f"  NPV         : IDR {_n(r['npv'] / MILLION, 0)} million")
    print(f"  IRR         : {_n(r['irr'] * 100, 1)}%")
    print(f"  Payback     : {_n(r['payback'], 1)} years")
