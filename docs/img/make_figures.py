#!/usr/bin/env python3
"""
Rebuild the README figures from the numbers in registry/.

  python docs/img/make_figures.py

Writes brooks_vs_random_{light,dark}.png and ict_r_{light,dark}.png next to this file.
For fixed-R targets the random baseline is 1 / (1 + R); for Brooks-06 and Brooks-07 it was
computed per trade from the actual stop and target distances.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", grid="#e4e3df",
                  s1="#2a78d6", s2="#eb6834"),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", grid="#383835",
                 s1="#3987e5", s2="#d95926"),
}

# (label, random baseline %, actual win rate %, trades, never-used data?)
BROOKS = [
    ("01 pullback 1R", 50.0, 47.3, 624, False),
    ("01 pullback 2R", 33.3, 32.5, 597, False),
    ("02 refined 1R", 50.0, 45.5, 44, False),
    ("02 refined 2R", 33.3, 27.3, 44, False),
    ("03 open trend 2R", 33.3, 46.2, 65, False),
    ("05 ABC 2R", 33.3, 50.0, 12, False),
    ("04 open trend, ES", 33.3, 36.8, 190, True),
    ("04 open trend, NQ", 33.3, 31.2, 80, True),
    ("05 ABC, ES", 33.3, 24.5, 49, True),
    ("06 fade, ES 2010-18", 41.4, 37.4, 171, True),
    ("06 fade, ES 2019-23", 37.7, 35.7, 115, True),
    ("07 always-in, NQ", 50.9, 51.8, 1556, True),
]
LABEL = {"03 open trend 2R", "05 ABC 2R", "04 open trend, ES", "05 ABC, ES", "07 always-in, NQ"}

# ICT-01 by period: (period, avg R before costs, avg R after costs, trades)
ICT = [
    ("ES 2010-18", 0.003, -0.197, 3697),
    ("ES 2019-23", -0.024, -0.149, 2727),
    ("NQ 2010-23", -0.020, -0.263, 9448),
    ("NQ 2023-25", -0.018, -0.073, 1090),
    ("MES 2023-25", 0.030, -0.090, 1174),
]


def style(ax, fig, t):
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(t["grid"])
    ax.tick_params(colors=t["ink2"], labelsize=9, length=0)
    ax.grid(True, color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def brooks(theme):
    t = THEMES[theme]
    fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=200)
    style(ax, fig, t)
    ax.plot([20, 56], [20, 56], color=t["ink2"], linewidth=1.2, linestyle=(0, (4, 3)), zorder=1)
    ax.text(27.0, 25.0, "actual = random", color=t["ink2"], fontsize=8.5, ha="left", rotation=36)
    for new, color, marker, name in [(False, t["s2"], "^", "In-sample (2 years of MES)"),
                                     (True, t["s1"], "o", "Never-used data (ES / NQ, 2010-2025)")]:
        pts = [b for b in BROOKS if b[4] == new]
        ax.scatter([p[1] for p in pts], [p[2] for p in pts], s=58, marker=marker, color=color,
                   edgecolors=t["surface"], linewidths=2, zorder=3, label=name)
    for lab, x, y, n, new in BROOKS:
        if lab in LABEL:
            left = x > 45 or lab.startswith("04")
            ax.annotate(f"{lab} (n={n:,})", (x, y), xytext=(x - 0.9 if left else x + 0.9, y + (0.9 if x > 45 else -0.35)),
                        fontsize=8, color=t["ink"], ha="right" if left else "left")
    ax.set_xlim(20, 56)
    ax.set_ylim(20, 56)
    ax.set_xlabel("Random baseline win rate (%)", color=t["ink2"], fontsize=9.5)
    ax.set_ylabel("Actual win rate (%)", color=t["ink2"], fontsize=9.5)
    fig.suptitle("Brooks rules: win rate vs. a random entry", x=0.08, ha="left",
                 color=t["ink"], fontsize=13, fontweight="bold")
    ax.set_title("Above the line = better than random. Big in-sample gaps vanished on data never used before.",
                 loc="left", color=t["ink2"], fontsize=9, pad=10)
    leg = ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    for txt in leg.get_texts():
        txt.set_color(t["ink"])
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"brooks_vs_random_{theme}.png"), facecolor=t["surface"])
    plt.close(fig)


def ict(theme):
    t = THEMES[theme]
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    style(ax, fig, t)
    ax.grid(False, axis="x")
    w = 0.36
    xs = range(len(ICT))
    b1 = ax.bar([x - w / 2 - 0.01 for x in xs], [r[1] for r in ICT], w, color=t["s1"], label="Before costs")
    b2 = ax.bar([x + w / 2 + 0.01 for x in xs], [r[2] for r in ICT], w, color=t["s2"], label="After costs")
    for bars in (b1, b2):
        for b in bars:
            b.set_capstyle("round")
    ax.axhline(0, color=t["ink2"], linewidth=1)
    for x, (_, pre, post, n) in zip(xs, ICT):
        ax.text(x + w / 2 + 0.01, post - 0.012, f"{post:+.2f}", ha="center", va="top", fontsize=8, color=t["ink"])
        ax.text(x, 0.045, f"n={n:,}", ha="center", fontsize=7.5, color=t["ink2"])
    ax.set_xticks(list(xs))
    ax.set_xticklabels([r[0] for r in ICT], color=t["ink2"], fontsize=8.5)
    ax.set_ylim(-0.31, 0.07)
    ax.set_ylabel("Average R per trade", color=t["ink2"], fontsize=9.5)
    fig.suptitle("ICT 2022 model: about zero before costs, negative after", x=0.08, ha="left",
                 color=t["ink"], fontsize=13, fontweight="bold")
    ax.set_title("18,136 trades on ES / NQ / MES. No period is positive after commission and slippage.",
                 loc="left", color=t["ink2"], fontsize=9, pad=10)
    leg = ax.legend(loc="lower left", frameon=False, fontsize=8.5, ncol=2)
    for txt in leg.get_texts():
        txt.set_color(t["ink"])
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"ict_r_{theme}.png"), facecolor=t["surface"])
    plt.close(fig)


if __name__ == "__main__":
    for th in THEMES:
        brooks(th)
        ict(th)
    print("figures written to", HERE)
