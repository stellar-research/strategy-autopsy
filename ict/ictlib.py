"""
ICT pattern detection (pure logic, no network access, easy to backtest and test)

Feed it closed 1-minute bars one at a time; the engine emits events following the ICT 2022 Mentorship model:
  watch   price swept a key liquidity level (prior-day high/low, Asia/London range high/low, equal highs/lows)
  setup   after the sweep, an opposite market structure shift (MSS) left a fair value gap (FVG)
  trigger price returned to the FVG and the model enters
  result  whether the stop or the target was hit first (to measure how reliable these alerts are)

All times are New York time. Produces alerts only; never places orders.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

KILL_ZONES = [  # New York time
    ("London", time(2, 0), time(5, 0)),
    ("NY AM", time(8, 30), time(11, 0)),
    ("NY PM", time(13, 30), time(16, 0)),
]


@dataclass
class Bar:
    t: datetime  # bar open time (New York)
    o: float
    h: float
    l: float
    c: float


@dataclass
class Level:
    name: str
    price: float
    side: str          # "buy": buy-side liquidity above (buy stops); "sell": sell-side liquidity below
    taken: bool = False


@dataclass
class Hunt:
    """After a liquidity sweep, wait for the opposite structure shift."""
    dir: str           # swept buy-side -> look for a short; swept sell-side -> look for a long
    level: Level
    t0: datetime
    extreme: float     # highest (short) / lowest (long) price during the sweep
    extreme_t: datetime
    mss_ref: float | None = None   # short-term swing point that must be broken
    mss_t: datetime | None = None  # bar where the structure shift happened
    wait_fvg: int = 0


@dataclass
class Setup:
    dir: str
    level: Level
    fvg_lo: float
    fvg_hi: float
    entry: float
    stop: float
    target: float
    target_name: str
    t: datetime
    sweep_t: datetime
    kill_zone: str
    bias: str
    triggered: datetime | None = None
    done: bool = False
    shadow: bool = False  # backtest-only mirror trade: same time and distances, opposite side (random baseline)


def kill_zone(t: datetime):
    tt = t.time()
    for name, a, b in KILL_ZONES:
        if a <= tt < b:
            return name
    return ""


def session_day(t: datetime):
    """CME trading day: a new day starts at 18:00 New York time."""
    return (t + timedelta(hours=6)).date()


class Engine:
    def __init__(self, symbol, tick=0.25, kz_only=True, hunt_minutes=60, fvg_wait=3,
                 setup_minutes=30, min_fvg_ticks=2, min_rr=1.5, eq_tol=0.0002,
                 fvg_atr=0.5, risk_atr=1.5, disp_atr=3.0, max_rr=6.0, shadow=False):
        self.symbol, self.tick, self.kz_only = symbol, tick, kz_only
        self.shadow = shadow
        self.hunt_minutes, self.fvg_wait, self.setup_minutes = hunt_minutes, fvg_wait, setup_minutes
        self.min_fvg, self.min_rr, self.eq_tol = min_fvg_ticks * tick, min_rr, eq_tol
        # Displacement threshold (relative to 1-minute ATR): filters out small, noisy signals
        self.fvg_atr, self.risk_atr, self.disp_atr, self.max_rr = fvg_atr, risk_atr, disp_atr, max_rr
        self.atr = None
        self.bars: list[Bar] = []
        self.days: dict = {}           # trading day -> [open, high, low, close]
        self.day = None
        self.levels: list[Level] = []
        self.hunts: list[Hunt] = []
        self.setups: list[Setup] = []
        self.swing_hi: list[tuple] = []  # 1-minute swing highs (time, price)
        self.swing_lo: list[tuple] = []
        self.m5: list[Bar] = []
        self.bias = "none"
        self.asia = self.london = None
        self.midnight_open = None

    # --------- every bar ---------
    def on_bar(self, b: Bar):
        ev = []
        d = session_day(b.t)
        if d != self.day:
            self._new_day(d)
        self._update_day(d, b)
        self._sessions(b)
        if self.bars:
            pc = self.bars[-1].c
            tr = max(b.h - b.l, abs(b.h - pc), abs(b.l - pc))
            self.atr = tr if self.atr is None else self.atr + (tr - self.atr) / 14
        self.bars.append(b)
        if len(self.bars) > 3000:
            self.bars = self.bars[-2000:]
        self._update_5m(b)
        self._update_swings()
        ev += self._track_setups(b)
        ev += self._check_hunts(b)
        ev += self._check_sweeps(b)
        return ev

    # --------- daily data, ranges, key levels ---------
    def _new_day(self, d):
        self.day = d
        prev = sorted(k for k in self.days if k < d)
        self.levels = [lv for lv in self.levels if lv.name.startswith("equal") and not lv.taken]
        if prev:
            o, h, l, c = self.days[prev[-1]]
            self.levels += [Level("prior-day high", h, "buy"), Level("prior-day low", l, "sell")]
            self.bias = self._bias(prev)
        self.asia = self.london = None
        self.midnight_open = None

    def _bias(self, prev):
        """Simple daily bias: if yesterday swept the day before's high/low and closed back inside, lean the other way; otherwise use where yesterday closed in its range."""
        o, h, l, c = self.days[prev[-1]]
        if len(prev) >= 2:
            _, h2, l2, _ = self.days[prev[-2]]
            if h > h2 and c < h2:
                return "bearish (prior day swept the earlier high and closed back below)"
            if l < l2 and c > l2:
                return "bullish (prior day swept the earlier low and closed back above)"
        return "lean long (prior day closed in upper half)" if c >= (h + l) / 2 else "lean short (prior day closed in lower half)"

    def _update_day(self, d, b):
        if d not in self.days:
            self.days[d] = [b.o, b.h, b.l, b.c]
        else:
            x = self.days[d]
            x[1], x[2], x[3] = max(x[1], b.h), min(x[2], b.l), b.c
        if len(self.days) > 30:
            for k in sorted(self.days)[:-30]:
                del self.days[k]

    def _sessions(self, b):
        tt = b.t.time()
        if time(20, 0) <= tt or tt < time(0, 0):
            self.asia = [max(self.asia[0], b.h), min(self.asia[1], b.l)] if self.asia else [b.h, b.l]
        if tt == time(0, 0):
            self.midnight_open = b.o
            if self.asia:
                self.levels += [Level("Asia high", self.asia[0], "buy"), Level("Asia low", self.asia[1], "sell")]
        if time(2, 0) <= tt < time(5, 0):
            self.london = [max(self.london[0], b.h), min(self.london[1], b.l)] if self.london else [b.h, b.l]
        if tt == time(5, 0) and self.london:
            self.levels += [Level("London high", self.london[0], "buy"), Level("London low", self.london[1], "sell")]

    def _update_5m(self, b):
        """5-minute bars -> find equal highs/lows (relative equal highs and lows, with stops resting above/below)."""
        start = b.t.replace(minute=b.t.minute - b.t.minute % 5, second=0)
        if self.m5 and self.m5[-1].t == start:
            x = self.m5[-1]
            x.h, x.l, x.c = max(x.h, b.h), min(x.l, b.l), b.c
            return
        self.m5.append(Bar(start, b.o, b.h, b.l, b.c))
        if len(self.m5) > 400:
            self.m5 = self.m5[-300:]
        m, n = self.m5, 2
        if len(m) < 2 * n + 2:
            return
        i = len(m) - 2 - n  # the bar just confirmed (n closed bars to its right)
        hi = [x.h for x in m[i - n:i + n + 1]]
        lo = [x.l for x in m[i - n:i + n + 1]]
        cutoff = m[i].t - timedelta(hours=24)
        if m[i].h == max(hi):
            self._eq(m[i], "buy", cutoff)
        if m[i].l == min(lo):
            self._eq(m[i], "sell", cutoff)

    def _eq(self, bar, side, cutoff):
        p = bar.h if side == "buy" else bar.l
        attr = "_eqh" if side == "buy" else "_eql"
        pts = [x for x in getattr(self, attr, []) if x[0] >= cutoff]
        tol = p * self.eq_tol
        for t, q in pts:
            if abs(q - p) <= tol and (bar.t - t) >= timedelta(minutes=15):
                price = max(p, q) if side == "buy" else min(p, q)
                if not any(abs(lv.price - price) <= tol for lv in self.levels if lv.side == side and not lv.taken):
                    self.levels.append(Level("equal highs" if side == "buy" else "equal lows", price, side))
                break
        pts.append((bar.t, p))
        setattr(self, attr, pts[-20:])

    def _update_swings(self):
        """1-minute swing points (2 bars on each side)."""
        n, B = 2, self.bars
        if len(B) < 2 * n + 1:
            return
        i = len(B) - 1 - n
        win = B[i - n:i + n + 1]
        if B[i].h == max(x.h for x in win):
            self.swing_hi = (self.swing_hi + [(B[i].t, B[i].h)])[-50:]
        if B[i].l == min(x.l for x in win):
            self.swing_lo = (self.swing_lo + [(B[i].t, B[i].l)])[-50:]

    # --------- 1. liquidity sweep ---------
    def _check_sweeps(self, b):
        ev = []
        for lv in self.levels:
            if lv.taken:
                continue
            if (lv.side == "buy" and b.h > lv.price) or (lv.side == "sell" and b.l < lv.price):
                lv.taken = True
                d = "short" if lv.side == "buy" else "long"
                ext = b.h if d == "short" else b.l
                self.hunts = [h for h in self.hunts if h.dir != d] + [Hunt(d, lv, b.t, ext, b.t)]
                kz = kill_zone(b.t)
                if kz or not self.kz_only:
                    side = "buy-side liquidity (buy stops above)" if lv.side == "buy" else "sell-side liquidity (sell stops below)"
                    ev.append(dict(type="watch", symbol=self.symbol, t=b.t, dir=d, level=lv.name,
                                   price=lv.price, kill_zone=kz, bias=self.bias,
                                   text=f"{self.symbol} swept {lv.name} {lv.price:g} ({side}). "
                                        f"Watch for an opposite structure shift ({'short' if d == 'short' else 'long'} side)."))
        return ev

    # --------- 2. structure shift + FVG ---------
    def _check_hunts(self, b):
        ev, keep = [], []
        B = self.bars
        for h in self.hunts:
            if b.t - h.t0 > timedelta(minutes=self.hunt_minutes) and h.mss_t is None:
                continue  # no structure shift in time, give up
            short = h.dir == "short"
            if h.mss_t is None:
                # price is still moving in the sweep direction: update the extreme and look for a new structure point
                if (short and b.h > h.extreme) or (not short and b.l < h.extreme):
                    h.extreme, h.extreme_t, h.mss_ref = (b.h if short else b.l), b.t, None
                if h.mss_ref is None:
                    h.mss_ref = self._mss_ref(h)
                if h.mss_ref is not None and ((short and b.c < h.mss_ref) or (not short and b.c > h.mss_ref)):
                    h.mss_t = b.t
            if h.mss_t is not None:
                fvg = self._find_fvg(h)
                if fvg:
                    s = self._make_setup(h, fvg, b)
                    if s:
                        self.setups.append(s)
                        ev.append(self._setup_event(s))
                    continue  # this hunt is over
                h.wait_fvg += 1
                if h.wait_fvg > self.fvg_wait:
                    continue
            keep.append(h)
        self.hunts = keep
        return ev

    def _mss_ref(self, h):
        """Structure reference: the nearest short-term swing low (short) / high (long) before the sweep extreme.
        If the move had no pullback and the nearest swing is too far, use the low/high of the 5 bars before the extreme."""
        short = h.dir == "short"
        sw = [s[1] for s in (self.swing_lo if short else self.swing_hi) if s[0] < h.extreme_t]
        prior = [x for x in self.bars if x.t < h.extreme_t][-5:]
        near = (min(x.l for x in prior) if short else max(x.h for x in prior)) if prior else None
        if not sw:
            return near
        if near is None:
            return sw[-1]
        return max(sw[-1], near) if short else min(sw[-1], near)

    def _find_fvg(self, h):
        """Find the nearest FVG in the direction of the displacement, from the sweep extreme to now."""
        B = self.bars
        idx = [i for i, x in enumerate(B) if x.t >= h.extreme_t]
        if len(idx) < 3:
            return None
        need = max(self.min_fvg, self.fvg_atr * (self.atr or 0))
        for i in range(len(B) - 1, idx[0] + 1, -1):
            a, c = B[i - 2], B[i]
            if h.dir == "short" and c.h < a.l and a.l - c.h >= need:
                return (c.h, a.l)
            if h.dir == "long" and c.l > a.h and c.l - a.h >= need:
                return (a.h, c.l)
        return None

    def _make_setup(self, h, fvg, b):
        kz = kill_zone(h.mss_t)
        if self.kz_only and not kz:
            return None
        lo, hi = fvg
        buf = 2 * self.tick
        # Target candidates: untaken key levels + 5-minute short-term highs/lows from the last 8 hours (stops rest there too)
        recent = b.t - timedelta(hours=8)
        swings = ([Level("short-term low", q, "sell") for t, q in getattr(self, "_eql", []) if t >= recent]
                  + [Level("short-term high", q, "buy") for t, q in getattr(self, "_eqh", []) if t >= recent])
        pool = [lv for lv in self.levels if not lv.taken] + swings
        if h.dir == "short":
            entry, stop = lo, h.extreme + buf  # enter when price rallies back to the bottom of the FVG
            cands = [lv for lv in pool if lv.side == "sell" and lv.price < entry]
            cands.sort(key=lambda lv: -lv.price)
        else:
            entry, stop = hi, h.extreme - buf
            cands = [lv for lv in pool if lv.side == "buy" and lv.price > entry]
            cands.sort(key=lambda lv: lv.price)
        risk = abs(stop - entry)
        atr = self.atr or 0
        # Displacement must be large enough: at least disp_atr ATRs from the sweep extreme; a stop under risk_atr ATRs means the pattern is too small
        if risk <= 0 or abs(h.extreme - b.c) < self.disp_atr * atr or risk < self.risk_atr * atr:
            return None
        tgt = next((lv for lv in cands if abs(lv.price - entry) >= self.min_rr * risk), None)
        if tgt and abs(tgt.price - entry) > self.max_rr * risk:
            tgt = None  # target too far to be realistic; fall back to a fixed reward:risk
        target, tname = (tgt.price, tgt.name) if tgt else (
            entry - 2 * risk if h.dir == "short" else entry + 2 * risk, "2R (no suitable liquidity target nearby)")
        return Setup(h.dir, h.level, lo, hi, entry, stop, target, tname, b.t, h.t0, kz, self.bias)

    def _setup_event(self, s):
        risk = abs(s.stop - s.entry)
        rr = abs(s.target - s.entry) / risk
        d = "short" if s.dir == "short" else "long"
        align = self._align(s)
        return dict(type="setup", symbol=self.symbol, t=s.t, dir=s.dir, entry=s.entry, stop=s.stop,
                    target=s.target, rr=round(rr, 2), fvg=[s.fvg_lo, s.fvg_hi], level=s.level.name,
                    kill_zone=s.kill_zone, bias=s.bias, align=align, sweep_t=s.sweep_t,
                    text=f"{self.symbol} {d} setup ({s.kill_zone}): swept {s.level.name}, then a structure shift and FVG "
                         f"{s.fvg_lo:g}-{s.fvg_hi:g}. Enter on return to FVG at {s.entry:g}, stop {s.stop:g}, "
                         f"target {s.target:g} ({s.target_name}), reward:risk {rr:.1f}. Daily bias: {s.bias}, {align}.")

    @staticmethod
    def _align(s):
        bear = s.bias.startswith(("bearish", "lean short"))
        bull = s.bias.startswith(("bullish", "lean long"))
        if (s.dir == "short" and bear) or (s.dir == "long" and bull):
            return "with bias"
        if bear or bull:
            return "against bias (caution)"
        return "bias unclear"

    # --------- 3. trigger, 4. result ---------
    def _track_setups(self, b):
        ev, keep = [], []
        for s in self.setups:
            short = s.dir == "short"
            if s.triggered is None:
                if b.t - s.t > timedelta(minutes=self.setup_minutes):
                    ev.append(self._result(s, b, "expired", "did not return to the FVG within 30 minutes; setup cancelled"))
                    continue
                if (short and b.h >= s.stop) or (not short and b.l <= s.stop):
                    ev.append(self._result(s, b, "invalid", "price crossed the stop before entry; pattern invalidated"))
                    continue
                if (short and b.l <= s.target) or (not short and b.h >= s.target):
                    ev.append(self._result(s, b, "missed", "hit the target without returning to the FVG; missed"))
                    continue
                if (short and b.h >= s.entry) or (not short and b.l <= s.entry):
                    s.triggered = b.t
                    if self.shadow:  # mirror trade: same time, same stop and target distance, opposite side
                        risk, rew = abs(s.stop - s.entry), abs(s.target - s.entry)
                        m = Setup("long" if short else "short", s.level, s.fvg_lo, s.fvg_hi, s.entry,
                                  s.entry - risk if short else s.entry + risk,
                                  s.entry + rew if short else s.entry - rew, "mirror", s.t, s.sweep_t,
                                  s.kill_zone, s.bias, triggered=b.t, shadow=True)
                        # On the trigger bar the real trade only checks its stop; treat the mirror the same way for fairness
                        if (m.dir == "short" and b.h >= m.stop) or (m.dir == "long" and b.l <= m.stop):
                            ev.append(self._result(m, b, "loss", "mirror trade hit its stop"))
                        else:
                            keep.append(m)
                    ev.append(dict(type="trigger", symbol=self.symbol, t=b.t, dir=s.dir, entry=s.entry,
                                   stop=s.stop, target=s.target,
                                   text=f"{self.symbol} price returned to the FVG; {'short' if short else 'long'} entry at {s.entry:g} triggered "
                                        f"(stop {s.stop:g}, target {s.target:g})."))
            if s.triggered is not None:
                hit_stop = (short and b.h >= s.stop) or (not short and b.l <= s.stop)
                # The order of events inside the trigger bar is unknown: count only the stop, not the target (conservative)
                hit_tgt = s.triggered != b.t and ((short and b.l <= s.target) or (not short and b.h >= s.target))
                if hit_stop:  # both sides touched in the same bar: conservatively count the stop
                    ev.append(self._result(s, b, "loss", "hit the stop"))
                    continue
                if hit_tgt:
                    ev.append(self._result(s, b, "win", "reached the target"))
                    continue
                if b.t.time() >= time(16, 55) and b.t.time() < time(17, 0):
                    ev.append(self._result(s, b, "timeout", "neither target nor stop before the close; marked at the close"))
                    continue
            keep.append(s)
        self.setups = keep
        return ev

    def _result(self, s, b, outcome, why):
        risk = abs(s.stop - s.entry)
        r = {"win": abs(s.target - s.entry) / risk, "loss": -1.0}.get(outcome)
        if outcome == "timeout":
            r = ((s.entry - b.c) if s.dir == "short" else (b.c - s.entry)) / risk
        return dict(type="shadow_result" if s.shadow else "result", symbol=self.symbol, t=b.t, dir=s.dir,
                    outcome=outcome, risk_pts=round(risk, 4), trig_t=s.triggered,
                    r=None if r is None else round(r, 2), setup_t=s.t, entry=s.entry, stop=s.stop,
                    target=s.target, kill_zone=s.kill_zone, align=self._align(s), level=s.level.name,
                    text=f"{self.symbol} {s.t:%H:%M} {'short' if s.dir == 'short' else 'long'} setup: {why}"
                         + (f" ({r:+.2f}R)" if r is not None else "") + ".")
