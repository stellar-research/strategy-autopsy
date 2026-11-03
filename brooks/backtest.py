#!/usr/bin/env python3
"""
backtest.py - intraday futures backtest for the Brooks price action engine (MES / ES / MNQ / NQ)

Rules that prevent look-ahead:
  1. Signals are computed only after a 5-minute bar closes, using closed bars only
  2. Orders are matched inside the next 5-minute bar, one 1-minute bar at a time
  3. If a 1-minute bar touches both the stop and the target, the stop is assumed (conservative)
  4. A take-profit limit fills only if price trades 1 tick through it; stop and market orders pay slippage; commission is charged
  5. No overnight positions; everything is closed before the session ends

Input: a 1-minute OHLCV CSV (Databento, a TradingView export or any other source)
Usage:
  python backtest.py mes_1m.csv --symbol MES
  python backtest.py mes_1m.csv --symbol MES --split-date 2026-03-01 --breakeven-r 1
Output: printed statistics + trades.csv + summary.csv + equity.png (in the --out folder)
"""
import argparse
import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pa_engine import BrooksPA, PAParams

SPECS = {  # tick size, point value (USD)
    "MES": (0.25, 5.0), "ES": (0.25, 50.0),
    "MNQ": (0.25, 2.0), "NQ": (0.25, 20.0),
}


# ---------------------------------------------------------------- data
def load_minutes(path, tz):
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    tcol = next((cols[k] for k in ("ts_event", "timestamp", "datetime", "time", "date") if k in cols), None)
    if tcol is None:
        raise ValueError("No time column found (need one of ts_event / timestamp / datetime / time / date)")
    ts = df[tcol]
    # In pandas 3 string columns are StringDtype and np.issubdtype raises TypeError,
    # so use pandas' own check instead.
    if pd.api.types.is_numeric_dtype(ts):
        unit = "ns" if ts.iloc[0] > 1e17 else "ms" if ts.iloc[0] > 1e11 else "s"
        idx = pd.to_datetime(ts, unit=unit, utc=True)
    elif ts.astype(str).str.contains(r"(?:[+-]\d{2}:?\d{2}|Z)$", regex=True).iloc[0]:
        # Strings with a UTC offset: across daylight saving both -05:00 and -04:00 appear, so parse everything as UTC
        idx = pd.to_datetime(ts, utc=True)
    else:
        idx = pd.to_datetime(ts, utc=False).dt.tz_localize(tz)
    out = pd.DataFrame({k: df[cols[k]].astype(float) for k in ("open", "high", "low", "close")})
    out["volume"] = df[cols["volume"]].astype(float) if "volume" in cols else 0.0
    out.index = pd.DatetimeIndex(idx).tz_convert("America/New_York")
    out = out[~out.index.duplicated()].sort_index()
    # Regular trading hours 09:30-16:00 (US Eastern), Monday to Friday
    t = out.index.hour * 100 + out.index.minute
    return out[(t >= 930) & (t < 1600) & (out.index.dayofweek < 5)]


def to_bars(m1, minutes):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    bars = m1.resample(f"{minutes}min", label="left", closed="left").agg(agg).dropna(subset=["open"])
    buckets = m1.index.floor(f"{minutes}min")
    groups = {k: g[["open", "high", "low", "close"]].to_numpy()
              for k, g in m1.groupby(buckets)}
    return bars, groups


# ---------------------------------------------------------------- backtest
@dataclass
class Order:
    dir: int
    kind: str       # stop / market
    price: float
    stop: float
    target: float
    name: str
    qty: int
    quality: float


@dataclass
class Pos:
    dir: int
    entry: float
    stop: float
    target: float
    risk: float
    name: str
    qty: int
    time: object
    quality: float
    be_done: bool = False


def run(args):
    tick, pv = SPECS[args.symbol]
    m1 = load_minutes(args.csv, args.tz)
    if args.start: m1 = m1[m1.index >= pd.Timestamp(args.start, tz="America/New_York")]
    if args.end: m1 = m1[m1.index < pd.Timestamp(args.end, tz="America/New_York")]
    if m1.empty: raise SystemExit("No data left. Check the time zone, date range or file format.")
    bars, groups = to_bars(m1, args.bar_minutes)
    print(f"Data: {m1.index[0]} -> {m1.index[-1]}, {len(bars)} bars of {args.bar_minutes} minutes, "
          f"{bars.index.normalize().nunique()} trading days")

    params = PAParams(min_trend=args.min_trend, min_signal=args.min_signal,
                      min_breakout=args.min_breakout,
                      strategy=args.strategy, dir_min=args.dir_min,
                      min_h_count=args.min_h, target_mode=args.target,
                      # v2 filter switches, all on by default; add --no-xxx to turn one off for ablation
                      warmup_sessions=args.warmup_sessions,
                      use_ttr_filter=not args.no_ttr_filter,
                      use_climax_filter=not args.no_climax_filter,
                      use_position_filter=not args.no_position_filter,
                      use_channel_flag=not args.no_channel_flag,
                      breakout_needs_trend=not args.no_breakout_trend,
                      use_two_bar_reversal=not args.no_two_bar_reversal,
                      use_small_bar_pad=not args.no_small_bar_pad,
                      min_rr=args.min_rr,
                      min_risk_frac_range=args.min_risk_frac_range,
                      stop_max_ticks=args.stop_max_ticks,
                      stop_too_wide=args.stop_too_wide)
    pa = BrooksPA(tick, params)
    slip = args.slippage * tick
    hhmm = lambda s: int(s.replace(":", ""))
    t_start, t_end, t_flat = hhmm(args.start_time), hhmm(args.end_time), hhmm(args.flatten)

    trades, pending, pos = [], None, None
    pend_age = 0                    # how many bars the pending order has lived
    prev_day, day_pnl, day_trades = None, 0.0, 0

    def close(p, price, time, reason):
        nonlocal day_pnl
        pts = p.dir * (price - p.entry)
        usd = pts * pv * p.qty - 2 * args.commission * p.qty
        day_pnl += usd
        trades.append(dict(entry_time=p.time, exit_time=time, setup=p.name,
                           dir="long" if p.dir > 0 else "short", qty=p.qty, entry=p.entry, exit=price,
                           stop=p.stop, target=p.target, risk_pts=p.risk, pnl_pts=pts,
                           pnl_usd=usd, r=pts / p.risk if p.risk else 0, reason=reason,
                           quality=p.quality))

    idx = bars.index
    for i, t in enumerate(idx):
        bar = bars.iloc[i]
        day = t.date()
        first = day != prev_day
        if first:
            if pos is not None:                         # should never happen (positions are closed at the session end)
                close(pos, bars.iloc[i - 1]["close"], idx[i - 1], "session_end")
                pos = None
            pending = None; pend_age = 0                # pending orders do not carry over to the next day
            day_pnl, day_trades, prev_day = 0.0, 0, day

        # ---- 1. match orders inside this bar using 1-minute data
        for k, (o, h, l, c) in enumerate(groups.get(t, [])):
            mt = t + pd.Timedelta(minutes=k)
            if pending is not None and pos is None:
                od, fill = pending, None
                if od.kind == "market" and k == 0:
                    fill = o + od.dir * slip
                elif od.kind == "stop":
                    if od.dir > 0 and h >= od.price: fill = max(od.price, o) + slip
                    if od.dir < 0 and l <= od.price: fill = min(od.price, o) - slip
                if fill is not None:
                    pos = Pos(od.dir, fill, od.stop, od.target, abs(fill - od.stop), od.name, od.qty, mt, od.quality)
                    pending = None; pend_age = 0
                    day_trades += 1
            if pos is not None:
                d = pos.dir
                gap_stop = (o <= pos.stop) if d > 0 else (o >= pos.stop)
                hit_stop = (l <= pos.stop) if d > 0 else (h >= pos.stop)
                hit_tgt = (h >= pos.target + tick) if d > 0 else (l <= pos.target - tick)
                if gap_stop and mt != pos.time:
                    close(pos, o - d * slip, mt, "stop_gap"); pos = None
                elif hit_stop:                              # stop and target touched together: assume the stop (conservative)
                    close(pos, pos.stop - d * slip, mt, "stop"); pos = None
                elif hit_tgt:
                    close(pos, pos.target, mt, "target"); pos = None
        # Order life: cancel after --order-life bars (Brooks' signal-bar stop orders live for one bar by default)
        if pending is not None:
            pend_age += 1
            if pend_age >= args.order_life:
                pending = None; pend_age = 0

        # ---- 2. bar closed: update features
        f = pa.update(bar["open"], bar["high"], bar["low"], bar["close"], first)
        bar_end = t + pd.Timedelta(minutes=args.bar_minutes)
        now = bar_end.hour * 100 + bar_end.minute
        last_of_day = i + 1 >= len(idx) or idx[i + 1].date() != day

        # ---- 3. manage the open position
        if pos is not None:
            if now >= t_flat or last_of_day:
                close(pos, bar["close"] - pos.dir * slip, bar_end, "flatten"); pos = None
            elif args.breakeven_r > 0 and not pos.be_done:
                reach = bar["high"] >= pos.entry + args.breakeven_r * pos.risk if pos.dir > 0 \
                    else bar["low"] <= pos.entry - args.breakeven_r * pos.risk
                if reach:
                    pos.stop, pos.be_done = pos.entry, True
            continue

        # ---- 4. new signals
        if f is None or f["signal"] == 0 or last_of_day: continue
        if now < t_start or now >= t_end: continue
        if day_trades >= args.max_trades: continue
        if args.max_daily_loss > 0 and day_pnl <= -args.max_daily_loss: continue
        is_bo = f["type"] == "breakout"
        if (is_bo and args.no_breakout) or (not is_bo and args.no_pullback): continue
        if f["quality"] < args.min_quality: continue

        risk = abs(f["entry"] - f["stop"])
        qty = args.contracts
        if args.risk_per_trade > 0:
            qty = min(int(args.risk_per_trade // ((risk + 2 * tick) * pv)), args.max_contracts)
        if qty < 1: continue
        suffix = "BO" if is_bo else {"open_trend": "OT", "fade": "FB"}.get(f["type"], "PB")
        name = ("L_" if f["signal"] > 0 else "S_") + suffix
        # Round the target to the tick size, toward the entry (conservative)
        tgt = math.floor(f["target"] / tick) * tick if f["signal"] > 0 else math.ceil(f["target"] / tick) * tick
        pending = Order(f["signal"], "market" if is_bo else "stop", f["entry"],
                        f["stop"], tgt, name, qty, f["quality"])

    return pd.DataFrame(trades)


# ---------------------------------------------------------------- statistics
def stats(df):
    if df.empty:
        return dict(trades=0)
    w, lo = df[df.pnl_usd > 0], df[df.pnl_usd <= 0]
    eq = df.pnl_usd.cumsum()
    gross_loss = -lo.pnl_usd.sum()
    return dict(
        trades=len(df),
        win_rate=f"{len(w) / len(df):.1%}",
        avg_win=round(w.pnl_usd.mean(), 2) if len(w) else 0,
        avg_loss=round(lo.pnl_usd.mean(), 2) if len(lo) else 0,
        expectancy=round(df.pnl_usd.mean(), 2),
        avg_R=round(df.r.mean(), 3),
        profit_factor=round(w.pnl_usd.sum() / gross_loss, 2) if gross_loss > 0 else math.inf,
        total_pnl=round(df.pnl_usd.sum(), 2),
        max_drawdown=round((eq - eq.cummax()).min(), 2),
    )


def report(trades, args):
    os.makedirs(args.out, exist_ok=True)
    if trades.empty:
        print("No trades. Try relaxing --min-trend / --min-signal, or check that the data is long enough.")
        return
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)

    rows = {"ALL": stats(trades)}
    for name, g in trades.groupby("setup"):
        rows[name] = stats(g)
    summary = pd.DataFrame(rows).T
    print("\n=== By setup ===")
    print(summary.to_string())

    if args.split_date:
        cut = pd.Timestamp(args.split_date, tz="America/New_York")
        ins = trades[trades.entry_time < cut]
        oos = trades[trades.entry_time >= cut]
        print(f"\n=== In-sample (before {args.split_date}) vs out-of-sample (after) ===")
        print(pd.DataFrame({"in-sample": stats(ins), "out-of-sample": stats(oos)}).T.to_string())

    tm = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"), win=trades.pnl_usd > 0)
    monthly = tm.groupby("month").agg(trades=("pnl_usd", "size"), win_rate=("win", "mean"), pnl=("pnl_usd", "sum")).round(3)
    print("\n=== By month ===")
    print(monthly.to_string())

    trades.to_csv(os.path.join(args.out, "trades.csv"), index=False, encoding="utf-8-sig")
    summary.to_csv(os.path.join(args.out, "summary.csv"), encoding="utf-8-sig")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(trades.exit_time, trades.pnl_usd.cumsum())
        ax.set_title("Equity curve (USD, after costs)")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "equity.png"), dpi=120)
    except ImportError:
        pass
    print(f"\nDetails saved to {args.out}/ (trades.csv, summary.csv, equity.png)")


def build_parser():
    ap = argparse.ArgumentParser(description="Intraday futures backtest for the Brooks price action engine")
    ap.add_argument("csv", help="1-minute OHLCV CSV file")
    ap.add_argument("--symbol", default="MES", choices=list(SPECS))
    ap.add_argument("--tz", default="America/New_York", help="time zone to assume when CSV times have none")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--split-date", help="in-sample / out-of-sample split date, e.g. 2026-03-01")
    ap.add_argument("--bar-minutes", type=int, default=5)
    ap.add_argument("--commission", type=float, default=0.85, help="commission per contract per side (USD); use your broker's rate")
    ap.add_argument("--slippage", type=int, default=1, help="slippage on stop and market orders (ticks)")
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--risk-per-trade", type=float, default=0, help="if > 0, size each trade by this risk in USD")
    ap.add_argument("--max-contracts", type=int, default=5)
    ap.add_argument("--max-trades", type=int, default=4, help="maximum trades per day")
    ap.add_argument("--max-daily-loss", type=float, default=150)
    ap.add_argument("--breakeven-r", type=float, default=0, help="move the stop to breakeven after this many R of profit; 0 = off")
    ap.add_argument("--start-time", default="09:35"); ap.add_argument("--end-time", default="15:30")
    ap.add_argument("--flatten", default="15:55")
    ap.add_argument("--min-trend", type=float, default=3)
    ap.add_argument("--min-signal", type=int, default=6)
    ap.add_argument("--min-breakout", type=int, default=7)
    ap.add_argument("--min-quality", type=float, default=0,
                    help="minimum signal quality (0 = no filter); quality = 0.5 x pattern score + 0.5 x trend score, out of 10")
    # ---- v2 filter switches: all on by default, add --no-xxx to turn one off for ablation ----
    ap.add_argument("--warmup-sessions", type=int, default=10,
                    help="number of sessions of daily range needed before signals start")
    ap.add_argument("--no-ttr-filter", action="store_true", help="turn off the tight trading range filter")
    ap.add_argument("--no-climax-filter", action="store_true", help="turn off the climax filter")
    ap.add_argument("--no-position-filter", action="store_true", help="turn off the position-in-range filter")
    ap.add_argument("--no-channel-flag", action="store_true",
                    help="turn off the channel-as-flag rule (no breakout chasing at the end of a channel)")
    ap.add_argument("--no-breakout-trend", action="store_true", help="allow chasing breakouts inside trading ranges")
    ap.add_argument("--no-two-bar-reversal", action="store_true", help="turn off merging entry/stop for two-bar reversals")
    ap.add_argument("--no-small-bar-pad", action="store_true", help="turn off the extra stop padding for small signal bars")
    ap.add_argument("--min-rr", type=float, default=1.0, help="minimum reward:risk; no signal below this")
    ap.add_argument("--min-risk-frac-range", type=float, default=0.25,
                    help="minimum risk = average bar range x this ratio, so stops are not too tight for noise")
    ap.add_argument("--stop-max-ticks", type=int, default=8, help="maximum distance from entry to stop (ticks)")
    ap.add_argument("--stop-too-wide", default="reject", choices=["reject","truncate"])
    ap.add_argument("--order-life", type=int, default=1, help="number of bars a pending order lives before it is cancelled")
    ap.add_argument("--no-breakout", action="store_true")
    ap.add_argument("--no-pullback", action="store_true")
    ap.add_argument("--strategy", default="v1", choices=["v1", "pullback", "pullback2", "open_trend", "abc", "fade", "ai"],
                    help="v1 = first version; pullback = plain pullback; pullback2 = refined pullback; open_trend = trend from the open; abc = structured ABC pullback (T-3); fade = fade failed range breakouts (F-1); ai = always-in reversal (AI-1)")
    ap.add_argument("--target", default="2R", choices=["1R", "2R", "extreme", "eod"], help="take-profit method (eod = close at session end)")
    ap.add_argument("--dir-min", type=int, default=7, help="minimum of the last 10 bars on the same side of the moving average")
    ap.add_argument("--min-h", type=int, default=1, help="1 = H2/L2 only; 0 = allow H1/L1")
    ap.add_argument("--out", default="results")
    return ap


def main():
    args = build_parser().parse_args()
    report(run(args), args)


if __name__ == "__main__":
    main()
