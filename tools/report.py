#!/usr/bin/env python3
"""
report.py - turn a trades.csv into a "is there any edge?" report

Checks four things:
  1. Actual win rate vs the random baseline (the probability that a random entry hits
     the target first, given each trade's actual stop and target distance)
  2. Whether the gap is significant (binomial z score)
  3. Performance by year
  4. Slippage sensitivity (profit factor with 1 and 2 extra ticks per side)

Usage:
  python tools/report.py results/xxx/trades.csv --symbol MES
  python tools/report.py results/xxx/trades.csv --symbol MES --out results/xxx/REPORT.md

Required columns in trades.csv: entry_time, entry, target, risk_pts, pnl_usd, qty
(the output of brooks/backtest.py works as is)
"""
import argparse
import math
import os

import pandas as pd

SPECS = {  # tick size, point value (USD)
    "MES": (0.25, 5.0), "ES": (0.25, 50.0),
    "MNQ": (0.25, 2.0), "NQ": (0.25, 20.0),
}


def profit_factor(pnl):
    win, loss = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    return float("inf") if loss == 0 else win / loss


def random_baseline(t):
    """Per trade: chance a random walk hits the target first ~ stop distance / (stop distance + target distance)."""
    rr = (t["target"] - t["entry"]).abs() / t["risk_pts"]
    ok = rr.notna() & (rr > 0) & t["risk_pts"].gt(0)
    return (1 / (1 + rr[ok])), ok


def build(t, symbol):
    tick, pv = SPECS[symbol]
    n = len(t)
    if n == 0:
        return "No trades.\n"
    wins = (t["pnl_usd"] > 0)
    lines = [f"# Backtest report ({symbol}, {n} trades)", ""]

    base, ok = random_baseline(t)
    lines += ["## 1. Is there directional information?", "", "| Metric | Result |", "|---|---|",
              f"| Trades | {n:,} |", f"| Actual win rate | {wins.mean():.1%} |"]
    if ok.sum() > 0:
        p = base.mean()
        k = wins[ok].sum()
        m = int(ok.sum())
        z = (k - m * p) / math.sqrt(m * p * (1 - p)) if 0 < p < 1 else float("nan")
        lines += [f"| Random baseline win rate | {p:.1%} (from {m:,} trades with a fixed target) |",
                  f"| z score | {z:+.2f} (>= 1.65 is roughly one-sided 5% significance) |"]
    else:
        lines += ["| Random baseline win rate | not available (trades have no fixed target, e.g. closed at session end) |"]
    lines += [f"| Profit factor | {profit_factor(t['pnl_usd']):.2f} |",
              f"| Total P&L (USD, after costs) | {t['pnl_usd'].sum():+,.1f} |",
              f"| Expectancy per trade (USD) | {t['pnl_usd'].mean():+.2f} |", ""]

    lines += ["## 2. Slippage sensitivity", "", "| Extra slippage per side | Total P&L | Profit factor |", "|---|---|---|"]
    for extra in (0, 1, 2):
        adj = t["pnl_usd"] - extra * 2 * tick * pv * t["qty"]
        lines.append(f"| {extra} tick(s) | {adj.sum():+,.1f} | {profit_factor(adj):.2f} |")
    lines.append("")

    yr = pd.to_datetime(t["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.year
    g = t.assign(year=yr.values).groupby("year")
    lines += ["## 3. By year", "", "| Year | Trades | Win rate | P&L (USD) | Profit factor |", "|---|---|---|---|---|"]
    for y, d in g:
        lines.append(f"| {y} | {len(d)} | {(d['pnl_usd'] > 0).mean():.1%} | "
                     f"{d['pnl_usd'].sum():+,.1f} | {profit_factor(d['pnl_usd']):.2f} |")
    lines += ["", "> The yearly table is for observation only. Picking years or sessions after seeing results is overfitting.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="trades.csv -> is-there-an-edge report")
    ap.add_argument("trades")
    ap.add_argument("--symbol", default="MES", choices=list(SPECS))
    ap.add_argument("--out", help="also save the report as Markdown")
    a = ap.parse_args()
    if not os.path.exists(a.trades):
        raise SystemExit(f"{a.trades} not found. The backtest writes no trades.csv when it produces no trades.")
    md = build(pd.read_csv(a.trades), a.symbol)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    main()
