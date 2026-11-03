"""
"The system offers up to 3 entries and up to 3 exits, and a person picks": if every pick were right, how much would it make? And are ICT levels better than random levels?

For each setup (produced by ictlib with default parameters; stop unchanged = 2 ticks beyond the sweep extreme):
  entry candidates (3): near edge of the FVG (the original entry), FVG midpoint (CE), far edge of the FVG
  exit candidates (3): the nearest 3 liquidity levels beyond the entry (within 6R); fill with 1R/2R/3R if fewer than 3
  each entry x exit combination (9) is simulated bar by bar (same rules as ictlib: cancelled if not back within 30 minutes,
  only the stop counts on the trigger bar, both sides in one bar counts as a stop, flat at 16:55), R after costs.
  "Pick perfectly" = the best of the 9 combinations and "no trade" (0R).
Control (random levels): apply the level geometry of another random setup from the same file (entry relative to stop, exits as multiples of risk)
  to this setup, again taking the best of 9. If ICT levels carry information, ICT "pick perfectly" should clearly beat the control.

Usage is the same as research.py:
  python3 ict/research_choice.py data.csv --symbol ES --name es_2010_2018 [--before 2025-09-01]
Results: results/ict/CHOICE_<name>.md and choice_<name>.jsonl
"""
import argparse
import json
import random
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ictlib import NY, Engine, Level  # noqa: E402
from research import COMM_RT, MICRO_PV, SPEC, stream, tstat  # noqa: E402


class ChoiceEngine(Engine):
    """Changes no ictlib parameter or logic; only records every liquidity target candidate when a setup is created."""

    def _make_setup(self, h, fvg, b):
        s = super()._make_setup(h, fvg, b)
        if s is None:
            return None
        recent = b.t - timedelta(hours=8)
        swings = ([Level("short-term low", q, "sell") for t, q in getattr(self, "_eql", []) if t >= recent]
                  + [Level("short-term high", q, "buy") for t, q in getattr(self, "_eqh", []) if t >= recent])
        pool = [lv for lv in self.levels if not lv.taken] + swings
        if s.dir == "short":
            c = sorted({lv.price for lv in pool if lv.side == "sell" and lv.price < s.entry}, reverse=True)
        else:
            c = sorted({lv.price for lv in pool if lv.side == "buy" and lv.price > s.entry})
        self._last_cands = c
        return s


class Sim:
    """Bar-by-bar simulation of one entry x exit combination."""
    __slots__ = ("short", "entry", "stop", "target", "t0", "trig", "r", "done")

    def __init__(self, short, entry, stop, target, t0):
        self.short, self.entry, self.stop, self.target, self.t0 = short, entry, stop, target, t0
        self.trig, self.r, self.done = None, 0.0, False  # not filled = 0R

    def step(self, b):
        s = self.short
        risk = abs(self.stop - self.entry)
        if self.trig is None:
            if b.t - self.t0 > timedelta(minutes=30):
                self.done = True
                return
            if (s and b.h >= self.stop) or (not s and b.l <= self.stop):
                self.done = True
                return
            if (s and b.l <= self.target) or (not s and b.h >= self.target):
                self.done = True
                return
            if (s and b.h >= self.entry) or (not s and b.l <= self.entry):
                self.trig = b.t
        if self.trig is not None:
            if (s and b.h >= self.stop) or (not s and b.l <= self.stop):
                self.r, self.done = -1.0, "loss"
                return
            if self.trig != b.t and ((s and b.l <= self.target) or (not s and b.h >= self.target)):
                self.r, self.done = abs(self.target - self.entry) / risk, "win"
                return
            if time(16, 55) <= b.t.time() < time(17, 0):
                self.r = ((self.entry - b.c) if s else (b.c - self.entry)) / risk
                self.done = "timeout"


def net(sim, sym):
    if sim.trig is None:
        return 0.0
    _, tick, micro = SPEC[sym]
    risk = abs(sim.stop - sim.entry)
    cost = COMM_RT / MICRO_PV[micro] + (tick if sim.done in ("loss", "timeout") else 0)
    return sim.r - cost / risk


def geometry(e):
    """Level geometry (in units of the original risk R0): how far the 3 entries are from the stop, and the 3 exits from the near entry."""
    R0 = abs(e["stop"] - e["entry"])
    lo, hi = e["fvg"]
    short = e["dir"] == "short"
    ents = [e["entry"], (lo + hi) / 2, hi if short else lo]
    fr = [abs(e["stop"] - x) / R0 for x in ents]
    return fr, None, R0


def build(short, stop, R0, efr, tmul):
    sign = -1 if short else 1          # short: entry below the stop, target below the entry
    near = stop + sign * R0
    ents = [stop + sign * f * R0 for f in efr]
    tgts = [near + sign * m * R0 for m in tmul]
    return ents, tgts


def run(files, sym, before=None, after=None, seed=7):
    rnd = random.Random(seed)
    out, geo = [], []
    for path in files:
        eng = ChoiceEngine(sym, tick=SPEC[sym][1], kz_only=True)
        live = []
        n = 0
        for b in stream(path, before, after):
            n += 1
            for g in live:
                for sim in g["ict"] + g["rnd"]:
                    if not sim.done:
                        sim.step(b)
            for g in [g for g in live if all(x.done for x in g["ict"] + g["rnd"])]:
                live.remove(g)
                ict = [net(x, sym) for x in g["ict"]]
                rr = [net(x, sym) for x in g["rnd"]]
                base = ict[0]  # near entry x first exit ~ a conservative version of the original rule
                out.append(dict(t=str(g["t"]), dir=g["dir"], R0=g["R0"],
                                best=max(ict + [0.0]), best_rnd=max(rr + [0.0]) if rr else None,
                                avg=sum(ict) / len(ict), avg_rnd=sum(rr) / len(rr) if rr else None,
                                entries=g["ents"], targets=g["tgts"], combos=[round(x, 3) for x in ict],
                                base=base))
            for e in eng.on_bar(b):
                if e["type"] != "setup":
                    continue
                short = e["dir"] == "short"
                R0 = abs(e["stop"] - e["entry"])
                cands = [c for c in getattr(eng, "_last_cands", []) if abs(c - e["entry"]) <= 6 * R0][:3]
                mul = [abs(c - e["entry"]) / R0 for c in cands]
                for m in (1.0, 2.0, 3.0):
                    if len(mul) >= 3:
                        break
                    if all(abs(m - x) > 0.25 for x in mul):
                        mul.append(m)
                mul = sorted(mul)[:3]
                efr, _, _ = geometry(e)
                ents, tgts = build(short, e["stop"], R0, efr, mul)
                g = dict(t=e["t"], dir=e["dir"], R0=R0, ents=ents, tgts=tgts,
                         ict=[Sim(short, x, e["stop"], y, e["t"]) for x in ents for y in tgts], rnd=[])
                if geo:  # control: borrow another setup's level geometry
                    efr2, mul2 = rnd.choice(geo)
                    ents2, tgts2 = build(short, e["stop"], R0, efr2, mul2)
                    g["rnd"] = [Sim(short, x, e["stop"], y, e["t"]) for x in ents2 for y in tgts2]
                geo.append((efr, mul))
                live.append(g)
            if n % 500000 == 0:
                print(f"  ...{n:,} bars, {b.t:%Y-%m-%d}", flush=True)
        print(f"{Path(path).name} done", flush=True)
    return out


def summarize(rows, sym, title):
    pv = MICRO_PV[SPEC[sym][2]]
    days = len({r["t"][:10] for r in rows}) or 1
    yrs = days / 252
    paired = [r for r in rows if r["best_rnd"] is not None]
    diff = [r["best"] - r["best_rnd"] for r in paired]
    f = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    doll = sum(r["best"] * r["R0"] * pv for r in rows) / yrs
    md = [f"# {title}", "",
          f"{len(rows)} setups (about {days} trading days). Each setup has 3 entries x 3 exits = 9 combinations; every stop is beyond the sweep extreme.", "",
          "| How levels are picked | Avg R per setup (after costs) |", "|---|---|",
          f"| **ICT levels, always picked perfectly** (best of 9 or no trade) | **{f([r['best'] for r in rows]):+.3f}** |",
          f"| Random levels, always picked perfectly (control) | {f([r['best_rnd'] for r in paired]):+.3f} |",
          f"| ICT levels, one of 9 at random | {f([r['avg'] for r in rows]):+.3f} |",
          f"| Random levels, at random | {f([r['avg_rnd'] for r in paired]):+.3f} |",
          f"| Near entry x first exit (no picking) | {f([r['base'] for r in rows]):+.3f} |", "",
          f"ICT perfect picks beat random perfect picks by {f(diff):+.3f}R, paired t = {tstat(diff):+.2f} (only |t| >= 2 counts).", "",
          f"ICT perfect picks, 1 contract of {SPEC[sym][2]}: about {doll:,.0f} USD per year ({len(rows) / yrs:.0f} setups a year, "
          f"{sum(r['best'] > 0 for r in rows) / yrs:.0f} of them worth taking).", ""]
    by = {}
    for r in rows:
        by.setdefault(r["t"][:4], []).append(r)
    md += ["## By year", "", "| Year | Setups | ICT perfect | Random perfect | ICT at random |", "|---|---|---|---|---|"]
    for y in sorted(by):
        g = by[y]
        p = [r for r in g if r["best_rnd"] is not None]
        md.append(f"| {y} | {len(g)} | {f([r['best'] for r in g]):+.3f} | {f([r['best_rnd'] for r in p]):+.3f} | {f([r['avg'] for r in g]):+.3f} |")
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
    md = summarize(rows, a.symbol, f"ICT candidate levels, pick-perfectly upper bound: {a.name} ({a.symbol})")
    log = HERE.parent / "results" / "ict"
    log.mkdir(parents=True, exist_ok=True)
    (log / f"CHOICE_{a.name}.md").write_text(md + "\n", encoding="utf-8")
    with (log / f"choice_{a.name}.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n" + md.split("## By year")[0])


if __name__ == "__main__":
    main()
