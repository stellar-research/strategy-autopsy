#!/usr/bin/env python3
"""
random_walk.py - generate pure random-walk 1-minute bars for an "honesty check" of a backtest engine

A random walk has no predictable structure. Any rule run on it should:
  - have a win rate close to the random baseline (slightly below, because of costs);
  - lose money after costs.
If a strategy reliably makes money on random data, the backtest itself is broken
(look-ahead, fills that are too optimistic, and so on).

Usage:
  python tools/random_walk.py --days 500 --out data/random_walk.csv
  python brooks/backtest.py data/random_walk.csv --symbol MES --strategy ai --out results/random_ai
  python tools/report.py results/random_ai/trades.csv --symbol MES
"""
import argparse

import numpy as np
import pandas as pd


def make(days, start_price, daily_range, tick, seed):
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2020-01-02", periods=days)
    per_min = daily_range / (1.6 * np.sqrt(390))    # a random walk's daily range is about 1.6 x per-minute sd x sqrt(390)
    rows, price = [], start_price
    for d in sessions:
        stamps = pd.date_range(f"{d.date()} 09:30", periods=390, freq="1min", tz="America/New_York")
        for ts in stamps:
            path = price + np.cumsum(rng.normal(0, per_min / 2, 4))
            o, c = price, path[-1]
            h, l = max(o, path.max()), min(o, path.min())
            q = lambda x: round(x / tick) * tick
            rows.append((ts.isoformat(), q(o), q(h), q(l), q(c), int(rng.integers(50, 500))))
            price = c
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def main():
    ap = argparse.ArgumentParser(description="Generate random-walk 1-minute data")
    ap.add_argument("--days", type=int, default=500)
    ap.add_argument("--price", type=float, default=5000.0)
    ap.add_argument("--daily-range", type=float, default=45.0, help="target average daily range (points); MES is about 40-60 in recent years")
    ap.add_argument("--tick", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/random_walk.csv")
    a = ap.parse_args()
    df = make(a.days, a.price, a.daily_range, a.tick, a.seed)
    df.to_csv(a.out, index=False)
    rng = (df.assign(d=df.timestamp.str[:10]).groupby("d").agg(h=("high", "max"), l=("low", "min")))
    print(f"Wrote {a.out}: {a.days} days, {len(df):,} bars, average daily range about {(rng.h - rng.l).mean():.1f} points")


if __name__ == "__main__":
    main()
