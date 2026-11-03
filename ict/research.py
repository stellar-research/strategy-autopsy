"""
ICT rule research backtest: streams 1-minute CSV data (e.g. Databento) bar by bar into the ictlib engine,
measures R after costs, and compares each trade with a 'mirror' trade (same time, same distances, opposite side). Pass criteria: registry/ict-01-mentorship-model.md.

Usage (from the repository root):
  python3 ict/research.py data.csv [more files...] --symbol ES --name es2010 [--before 2025-09-01]
The CSV needs a time column (ts_event / timestamp / datetime / time / date; UTC nanosecond integers or timezone-aware strings)
and open/high/low/close columns. Results go to results/ict/RESEARCH_<name>.md and research_<name>.jsonl.
"""
import argparse
import csv
import json
import math
import sys
import time as _time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ictlib import NY, Bar, Engine  # noqa: E402

# Contracts: point value (USD), tick size, and which micro contract the costs are based on
SPEC = {"ES": (50, 0.25, "MES"), "MES": (5, 0.25, "MES"), "NQ": (20, 0.25, "MNQ"), "MNQ": (2, 0.25, "MNQ")}
MICRO_PV = {"MES": 5, "MNQ": 2}
COMM_RT = 1.70  # round-trip commission per contract (USD)


def stream(path, before=None, after=None):
    """Read the CSV line by line and yield 1-minute Bars in New York time (without loading the whole file)."""
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in rd.fieldnames}
        tc = next(cols[k] for k in ("ts_event", "timestamp", "datetime", "time", "date") if k in cols)
        o, h, l, c = (cols[k] for k in ("open", "high", "low", "close"))
        for r in rd:
            v = r[tc]
            if v.isdigit():
                n = int(v)
                sec = n / 1e9 if n > 1e17 else n / 1e3 if n > 1e11 else n
                t = datetime.fromtimestamp(sec, tz=timezone.utc).astimezone(NY)
            else:
                t = datetime.fromisoformat(v.replace("Z", "+00:00"))
                t = t.astimezone(NY) if t.tzinfo else t.replace(tzinfo=NY)
            if before and t >= before:
                break
            if after and t < after:
                continue
            yield Bar(t, float(r[o]), float(r[h]), float(r[l]), float(r[c]))


def net_r(e, sym):
    """R after costs: micro-contract commission, plus 1 tick of slippage on stop and forced exits."""
    _, tick, micro = SPEC[sym]
    risk = e.get("risk_pts") or 0
    if not risk or e.get("r") is None:
        return None
    cost = COMM_RT / MICRO_PV[micro] + (tick if e["outcome"] in ("loss", "timeout") else 0)
    return e["r"] - cost / risk


def tstat(xs):
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd > 0 else float("nan")


def run(files, sym, before=None, after=None):
    events, nbars = [], 0
    t0 = _time.time()
    for path in files:
        eng = Engine(sym, tick=SPEC[sym][1], kz_only=True, shadow=True)
        first = last = None
        for b in stream(path, before, after):
            first = first or b.t
            last = b.t
            nbars += 1
            events += [e for e in eng.on_bar(b) if e["type"] in ("setup", "result", "shadow_result")]
            if nbars % 500000 == 0:
                print(f"  ...{nbars:,} bars, {b.t:%Y-%m-%d}, {_time.time() - t0:.0f}s", flush=True)
        print(f"{Path(path).name}: {first:%Y-%m-%d} to {last:%Y-%m-%d}" if first else f"{path}: no data", flush=True)
    return events, nbars


def summarize(events, sym, title):
    real = [e for e in events if e["type"] == "result"]
    shadow = {(str(e["setup_t"]), str(e["trig_t"])): e for e in events if e["type"] == "shadow_result"}
    rows = []
    for e in real:
        e["net"] = net_r(e, sym)
        if e["net"] is None:
            continue
        m = shadow.get((str(e["setup_t"]), str(e["trig_t"])))
        e["mirror"] = net_r(m, sym) if m else None
        rows.append(e)
    setups = sum(1 for e in events if e["type"] == "setup")
    cnt = defaultdict(int)
    for e in real:
        cnt[e["outcome"]] += 1

    def line(name, rs):
        if not rs:
            return f"| {name} | 0 | | | | | | | |"
        g = [e["r"] for e in rs]
        n = [e["net"] for e in rs]
        pairs = [e["net"] - e["mirror"] for e in rs if e.get("mirror") is not None]
        mir = [e["mirror"] for e in rs if e.get("mirror") is not None]
        wr = 100 * sum(1 for e in rs if e["outcome"] == "win") / len(rs)
        f = lambda xs: f"{sum(xs) / len(xs):+.3f}" if xs else "-"
        return (f"| {name} | {len(rs)} | {wr:.0f}% | {f(g)} | {f(n)} | {tstat(n):+.2f} | {f(mir)} | "
                f"{f(pairs)} | {tstat(pairs):+.2f} |")

    hdr = ["| Group | Trades | Win rate | Avg R (before costs) | **Avg R (after costs)** | t (vs 0) | Mirror avg R | **vs mirror** | t (paired) |",
           "|---|---|---|---|---|---|---|---|---|"]
    md = [f"# {title}", "",
           f"{setups} setups; filled trades: {cnt['win']} wins, {cnt['loss']} losses, {cnt['timeout']} closed at session end; "
           f"not filled: {cnt['missed']} missed, {cnt['expired']} expired, {cnt['invalid']} invalidated.", "",
           "Mirror trade = same time, same stop and target distance, opposite direction: a random-direction baseline. "
           "Only |t| >= 2 counts as statistically meaningful.", "", "## Overall", ""] + hdr + [line("All", rows), ""]

    def group(name, key):
        g = defaultdict(list)
        for e in rows:
            g[key(e)].append(e)
        return [f"## By {name} (exploratory)", ""] + hdr + [line(k, g[k]) for k in sorted(g)] + [""]

    md += group("year", lambda e: str(e["setup_t"])[:4])
    md += group("session", lambda e: e.get("kill_zone") or "-")
    md += group("daily bias", lambda e: e.get("align", ""))
    md += group("level swept", lambda e: e.get("level", ""))
    md += group("direction", lambda e: "short" if e["dir"] == "short" else "long")
    md += group("reward:risk bucket", lambda e: f"{min(int(abs(e['target'] - e['entry']) / e['risk_pts']), 4)}R")
    return "\n".join(md), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--symbol", required=True, choices=list(SPEC))
    ap.add_argument("--name", required=True)
    ap.add_argument("--before", help="use only data before this date (keeps the out-of-sample period locked)")
    ap.add_argument("--after")
    a = ap.parse_args()
    d = lambda s: datetime.fromisoformat(s).replace(tzinfo=NY) if s else None
    events, nbars = run(a.files, a.symbol, d(a.before), d(a.after))
    title = f"ICT rule backtest: {a.name} ({a.symbol}, {nbars:,} one-minute bars" + (f", up to {a.before}" if a.before else "") + ")"
    md, rows = summarize(events, a.symbol, title)
    log = HERE.parent / "results" / "ict"
    log.mkdir(parents=True, exist_ok=True)
    (log / f"RESEARCH_{a.name}.md").write_text(md + "\n", encoding="utf-8")
    with (log / f"research_{a.name}.jsonl").open("w", encoding="utf-8") as f:
        for e in rows:
            f.write(json.dumps({k: (str(v) if isinstance(v, datetime) else v) for k, v in e.items()
                                if k not in ("text",)}, ensure_ascii=False) + "\n")
    print("\n" + md.split("## By year")[0])


if __name__ == "__main__":
    main()
