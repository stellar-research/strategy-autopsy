"""
H-ICT3: trade only the pattern that matches the Episode 2 chart exactly. Does it make money? (pass criteria: registry/ict-03-episode2-pattern.md)

On top of the setups ictlib produces with default parameters, add every Episode 2 condition:
  1 the level swept is a relative equal high / equal low
  2 inducement first: earlier that day (from 00:00 New York), price broke the Asia low (for a short) / Asia high (for a long) before the sweep
  3 New York morning session
  4 in line with the daily bias
  5 entry in the premium (short) / discount (long) half of today's range (00:00 to now)
  6 target = the nearest old low (high) or today's unfilled 1-minute imbalance beyond the 50% line; no target, no trade
Entry at the near edge of the FVG, stop 2 ticks beyond the sweep extreme, cancelled if not filled within 30 minutes, both sides in one bar counts as a stop, flat at 16:55.
Mirror trades (same distances, opposite side) are recorded as the random baseline, plus exploratory results without conditions 1 and 2 (not used for pass/fail).

Usage: python3 ict/research_ep2.py data.csv --symbol ES --name es_2010_2018 [--before 2025-09-01]
Results: results/ict/EP2_<name>.md and ep2_<name>.jsonl
"""
import argparse
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ictlib import NY  # noqa: E402
from research import SPEC, stream, tstat  # noqa: E402
from research_choice import ChoiceEngine, Sim, net  # noqa: E402


class Day:
    """Today's (from 00:00 New York) high and low, the Asia range, and unfilled 1-minute imbalances."""

    def __init__(self):
        self.date = None
        self.hi = self.lo = None
        self.asia_next = [None, None]  # high/low of the previous evening 20:00-24:00, used the next day
        self.asia = [None, None]
        self.broke_asia_lo = self.broke_asia_hi = False
        self.bars = []
        self.bull, self.bear = [], []  # imbalances [lo, hi]

    def on_bar(self, b):
        t = b.t.time()
        if b.t.date() != self.date:
            self.date = b.t.date()
            self.hi, self.lo = b.h, b.l
            self.asia = self.asia_next
            self.asia_next = [None, None]
            self.broke_asia_lo = self.broke_asia_hi = False
            self.bars, self.bull, self.bear = [], [], []
        self.hi, self.lo = max(self.hi, b.h), min(self.lo, b.l)
        if self.asia[1] is not None and b.l < self.asia[1]:
            self.broke_asia_lo = True
        if self.asia[0] is not None and b.h > self.asia[0]:
            self.broke_asia_hi = True
        if t >= time(20, 0):
            a = self.asia_next
            self.asia_next = [b.h if a[0] is None else max(a[0], b.h), b.l if a[1] is None else min(a[1], b.l)]
        # Imbalances: drop the fully filled ones first, then add new ones
        self.bull = [g for g in self.bull if b.l > g[0]]
        self.bear = [g for g in self.bear if b.h < g[1]]
        self.bars.append(b)
        if len(self.bars) >= 3:
            a, c = self.bars[-3], self.bars[-1]
            if c.l > a.h:
                self.bull.append([a.h, c.l])
            if c.h < a.l:
                self.bear.append([c.h, a.l])


def mirror(sim_args):
    short, entry, stop, target, t = sim_args
    risk, rew = abs(stop - entry), abs(target - entry)
    return Sim(not short, entry, entry - risk if short else entry + risk,
               entry + rew if short else entry - rew, t)


def run(files, sym, before=None, after=None):
    rows = []
    for path in files:
        eng = ChoiceEngine(sym, tick=SPEC[sym][1], kz_only=True)
        day = Day()
        live = []
        for b in stream(path, before, after):
            for x in live:
                if x["mir"] is not None and not x["mir"].done:
                    x["mir"].step(b)
                if not x["sim"].done:
                    x["sim"].step(b)
                    if x["sim"].trig == b.t and x["mir"] is None:
                        # The mirror fills on the same bar as the real trade; on the trigger bar only the stop counts (same as ictlib's mirror)
                        x["mir"] = mirror(x["args"])
                        x["mir"].trig = b.t
                        x["mir"].step(b)
            for x in [x for x in live if x["sim"].done and (x["mir"] is None or x["mir"].done)]:
                live.remove(x)
                r = x["row"]
                r["net"] = net(x["sim"], sym)
                r["mirror"] = net(x["mir"], sym) if x["mir"] is not None else 0.0
                r["filled"] = x["sim"].trig is not None
                r["outcome"] = x["sim"].done if r["filled"] else "nofill"
                rows.append(r)
            day.on_bar(b)
            for e in eng.on_bar(b):
                if e["type"] != "setup":
                    continue
                short = e["dir"] == "short"
                mid = (day.hi + day.lo) / 2
                c1 = e["level"] in ("equal highs", "equal lows")
                c2 = day.broke_asia_lo if short else day.broke_asia_hi
                c3 = e["kill_zone"] == "NY AM"
                c4 = e["align"] == "with bias"
                c5 = e["entry"] > mid if short else e["entry"] < mid
                liq = [p for p in getattr(eng, "_last_cands", []) if (p < mid if short else p > mid)]
                imb = [g[1] for g in day.bull if g[1] < mid and g[1] < e["entry"]] if short else \
                      [g[0] for g in day.bear if g[0] > mid and g[0] > e["entry"]]
                cands = liq + imb
                if not cands:
                    continue
                tgt = max(cands) if short else min(cands)
                kind = "imbalance" if tgt in imb and tgt not in liq else "old " + ("low" if short else "high")
                args = (short, e["entry"], e["stop"], tgt, e["t"])
                row = dict(t=str(e["t"]), dir=e["dir"], level=e["level"], c1=c1, c2=c2, c3=c3, c4=c4, c5=c5,
                           all=c1 and c2 and c3 and c4 and c5, entry=e["entry"], stop=e["stop"], target=tgt,
                           kind=kind, risk=abs(e["stop"] - e["entry"]), rr=round(abs(tgt - e["entry"]) / abs(e["stop"] - e["entry"]), 2))
                live.append(dict(row=row, args=args, sim=Sim(*args), mir=None))
        print(f"{Path(path).name} done, {len(rows)} setups so far", flush=True)
    return rows


def line(name, rs):
    tr = [r for r in rs if r["filled"]]
    if not tr:
        return f"| {name} | {len(rs)} | 0 | | | | | |"
    n = [r["net"] for r in tr]
    d = [r["net"] - r["mirror"] for r in rs]
    wr = 100 * sum(r["outcome"] == "win" for r in tr) / len(tr)
    f = lambda xs: sum(xs) / len(xs)
    return (f"| {name} | {len(rs)} | {len(tr)} | {wr:.0f}% | {f(n):+.3f} | {tstat(n):+.2f} | "
            f"{f(d):+.3f} | {tstat(d):+.2f} |")


def summarize(rows, title):
    hdr = ["| Condition | Setups | Filled | Win rate | Avg R per trade (after costs) | t | Per setup vs mirror | t (paired) |",
           "|---|---|---|---|---|---|---|---|"]
    S = [r for r in rows if r["all"]]
    md = [f"# {title}", "", "**Main test: all Episode 2 conditions (1 equal highs/lows, 2 inducement first, 3 NY AM, 4 with bias, 5 premium/discount)**", ""]
    md += hdr + [line("All conditions", S), ""]
    md += ["## Exploration (not used for pass/fail)", ""] + hdr + [
        line("Without 1 (any liquidity)", [r for r in rows if r["c2"] and r["c3"] and r["c4"] and r["c5"]]),
        line("Without 2 (no inducement needed)", [r for r in rows if r["c1"] and r["c3"] and r["c4"] and r["c5"]]),
        line("Without 3 (all three sessions)", [r for r in rows if r["c1"] and r["c2"] and r["c4"] and r["c5"]]),
        line("Only 5 (premium/discount)", [r for r in rows if r["c5"]]),
        line("All setups (only the target rule changed)", rows),
        line("All conditions, target is an imbalance", [r for r in S if r["kind"] == "imbalance"]),
        line("All conditions, target is an old high/low", [r for r in S if r["kind"] != "imbalance"]), ""]
    by = {}
    for r in S:
        by.setdefault(r["t"][:4], []).append(r)
    md += ["## All conditions by year", ""] + hdr + [line(y, by[y]) for y in sorted(by)]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--symbol", required=True, choices=list(SPEC))
    ap.add_argument("--name", required=True)
    ap.add_argument("--before")
    ap.add_argument("--after")
    a = ap.parse_args()
    d = lambda s: datetime.fromisoformat(s).replace(tzinfo=NY) if s else None
    rows = run(a.files, a.symbol, d(a.before), d(a.after))
    md = summarize(rows, f"H-ICT3 strict Episode 2 pattern: {a.name} ({a.symbol})")
    log = HERE.parent / "results" / "ict"
    log.mkdir(parents=True, exist_ok=True)
    (log / f"EP2_{a.name}.md").write_text(md + "\n", encoding="utf-8")
    with (log / f"ep2_{a.name}.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n" + md.split("## Exploration")[0])


if __name__ == "__main__":
    main()
