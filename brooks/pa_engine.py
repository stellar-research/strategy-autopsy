"""
pa_engine.py - Al Brooks price action feature engine (incremental, bar by bar) v2

Uses closed bars only; never looks at future data.

Changes in v2 versus v1 (based on the English edition of the Brooks trilogy):
  P0-1  ADR warm-up: return None while the sample is too small, instead of falling back to price x 1%
  P0-2  Tight trading range: OR across several windows (4/6/10), plus an ADR-independent range-height / average-bar test
  P0-3  Climax filter: shared method that every pullback entry must pass
  P0-4  Position filter: outside strong trends, no buys in the top third and no sells in the bottom third of the range
  P0-5  Breakout entries need trend >= min_trend (no more chasing breakouts inside trading ranges)
  P1-6  If the signal bar overlaps the previous bar by >= 75%, treat it as a two-bar reversal (entry and stop beyond both bars)
  P1-7  Extra stop padding for small signal bars, with an 8-tick cap on total risk
  P1-8  Minimum risk: stops that are too tight are rejected
  P1-9  Removed the win_prob expectancy filter; replaced with a hard min_rr
  P2-11 always_in becomes global state, with follow-through bar confirmation and a tick threshold
  P2-10 New micro measuring gap target (projected from the midpoint)

Every filter has its own switch so its contribution can be measured in a backtest.

Usage:
    pa = BrooksPA(tick=0.25)
    for bar in bars:
        f = pa.update(o, h, l, c, first_of_session)
        if f and f["signal"] != 0: ...
"""
import math
from dataclasses import dataclass

INF = float("inf")


@dataclass
class PAParams:
    ema_period: int = 20
    lookback: int = 20
    ttr_bars: int = 10
    ttr_frac: float = 0.25          # tight range height <= average daily range x this ratio
    swing_strength: int = 3
    sessions_for_avg: int = 20
    min_trend: float = 3.0
    min_signal: int = 6
    min_breakout: int = 7
    fallback_rr: float = 1.5
    max_risk_frac_adr: float = 0.2
    # ---- strategy selection
    strategy: str = "v1"
    dir_bars: int = 10
    dir_min: int = 7
    min_h_count: int = 1
    target_mode: str = "2R"
    # ---- refined pullback
    max_cntr_run: int = 3
    max_big_cntr: int = 1
    # ---- trend from the open
    ot_spike_bars: int = 3
    ot_spike_adr: float = 0.15
    ot_last_bar: int = 24

    # ================= new in v2 =================
    # P0-1 warm-up
    warmup_sessions: int = 10       # sessions of daily range needed before signals start
    # P0-2 tight trading range
    use_ttr_filter: bool = True
    ttr_windows: tuple = (4, 6, 10)
    ttr_bar_mult: float = 2.0       # range height <= average bar range x this multiple also counts as tight
    # P0-3 climax
    use_climax_filter: bool = True
    climax_lookback: int = 10       # no same-direction pullback entry within this many bars after a climax
    climax_body_mult: float = 3.0   # single body >= average body x this multiple
    climax_ma_mult: float = 2.0     # |close - moving average| >= average bar range x this multiple
    climax_skip_current: int = 1    # bars to skip when a breakout entry checks for a climax (a big breakout bar itself is normal)
    # P0-4 position
    # Brooks' "position" means which end of an **established trading range** price is at,
    # not which end of the last N bars. With-trend entries are always at the edge of the last N bars
    # (breakout entries are by definition beyond the new high/low), so that yardstick would block every with-trend trade.
    # So: enable it only in ranges / no trend, and measure the range over a longer window.
    use_position_filter: bool = True
    pos_window: int = 40            # window (bars) for measuring the range; price sits still in a range, so a long window is more accurate
    pos_bars: int = 20              # short window used only for displaying f["range_pos"]
    pos_hi: float = 0.67            # in a range: no buys above the top third
    pos_lo: float = 0.33            # in a range: no sells below the bottom third
    pos_apply_trend: float = 3.0    # |trend score| below this (or a tight range) enables the "thirds" rule
    strong_trend: float = 6.0       # at this strength the trend counts as strong and the position filter lets everything through
    # In channels (3 <= |trend score| < strong_trend) only breakout entries are checked, and only at the extremes:
    # "trade a bull channel as a bear flag" (TRENDS ch. 15): buying the top of a bull channel is the wrong side.
    # Channels are supposed to keep making new highs, so 0.9/0.1 is used here instead of thirds.
    use_channel_flag: bool = True
    pos_channel_extreme: float = 0.90
    # P0-5 breakouts
    breakout_needs_trend: bool = True
    # P1-6 two-bar reversal
    use_two_bar_reversal: bool = True
    two_bar_overlap: float = 0.75
    # P1-7 stops
    use_small_bar_pad: bool = True
    small_bar_frac: float = 0.7     # signal bar range < average x this ratio -> small signal bar
    small_bar_ticks: int = 3        # stop padding for small signal bars (ticks)
    stop_max_ticks: int = 8         # maximum distance from entry to stop (ticks)
    stop_too_wide: str = "reject"
    # P1-8 minimum risk
    min_risk_frac_range: float = 0.25   # risk >= average bar range x this ratio
    # P1-9 minimum reward:risk
    min_rr: float = 1.0
    # P2-11 always in
    ai_follow_ticks: int = 2        # minimum ticks the follow-through bar must exceed the breakout bar by


class BrooksPA:
    def __init__(self, tick, params=None):
        self.tk = tick
        self.p = params or PAParams()
        self.o, self.h, self.l, self.c, self.e = [], [], [], [], []
        self.sess_ranges = []
        self.sess_hi = self.sess_lo = None
        self.adr = 0.0
        self.avg_range = self.avg_body = 0.0
        # bar counting state
        self.bull_leg_h, self.bull_leg_bar, self.bull_pb, self.bull_need_dn, self.hc = -INF, 0, False, False, 0
        self.bear_leg_l, self.bear_leg_bar, self.bear_pb, self.bear_need_up, self.lc = INF, 0, False, False, 0
        self.swings = []
        self.bull_h1_entry = self.bear_l1_entry = None
        self.abc = {1: self._abc_new(), -1: self._abc_new()}
        self.sess_bar = -1
        self.sess_open = None
        self._ot_reset()
        self.prev_bo_up = self.prev_bo_dn = 0
        # v2: global always-in state
        self.always_in = 0
        self.ai_flip_bar = -10 ** 9

    # ---------------------------------------------------------------- barsAgo access
    def O(self, k): return self.o[-1 - k]
    def H(self, k): return self.h[-1 - k]
    def L(self, k): return self.l[-1 - k]
    def C(self, k): return self.c[-1 - k]
    def E(self, k): return self.e[-1 - k]

    def rng(self, k): return max(self.H(k) - self.L(k), self.tk)
    def body(self, k): return abs(self.C(k) - self.O(k))
    def utail(self, k): return self.H(k) - max(self.O(k), self.C(k))
    def ltail(self, k): return min(self.O(k), self.C(k)) - self.L(k)
    def cpos(self, k): return (self.C(k) - self.L(k)) / self.rng(k)
    def bull_tb(self, k): return self.C(k) > self.O(k) and self.body(k) >= 0.5 * self.rng(k)
    def bear_tb(self, k): return self.C(k) < self.O(k) and self.body(k) >= 0.5 * self.rng(k)
    def doji(self, k): return self.body(k) <= 0.25 * self.rng(k)
    def inside(self, k): return self.H(k) <= self.H(k + 1) and self.L(k) >= self.L(k + 1)

    def overlap(self, k):
        ov = min(self.H(k), self.H(k + 1)) - max(self.L(k), self.L(k + 1))
        return max(0.0, ov) / self.rng(k)

    def _hi(self, d, k): return self.H(k) if d > 0 else -self.L(k)
    def _lo(self, d, k): return self.L(k) if d > 0 else -self.H(k)
    def _tb(self, d, k): return self.bull_tb(k) if d > 0 else self.bear_tb(k)

    # ---------------------------------------------------------------- main entry point
    def update(self, o, h, l, c, first_of_session):
        p = self.p
        self.o.append(o); self.h.append(h); self.l.append(l); self.c.append(c)
        a = 2.0 / (p.ema_period + 1)
        self.e.append(c if not self.e else self.e[-1] + a * (c - self.e[-1]))

        if first_of_session:
            self.sess_bar, self.sess_open = 0, o
            self._ot_reset()
        else:
            self.sess_bar += 1

        # average daily range (per trading session)
        if first_of_session:
            if self.sess_hi is not None:
                self.sess_ranges.append(self.sess_hi - self.sess_lo)
                self.sess_ranges = self.sess_ranges[-p.sessions_for_avg:]
            self.sess_hi, self.sess_lo = h, l
        else:
            self.sess_hi = h if self.sess_hi is None else max(self.sess_hi, h)
            self.sess_lo = l if self.sess_lo is None else min(self.sess_lo, l)

        # P0-1: no signals while the daily range sample is too small (no more price x 1% estimate)
        if len(self.sess_ranges) < p.warmup_sessions:
            self.adr = (sum(self.sess_ranges) / len(self.sess_ranges)) if self.sess_ranges else 0.0
            return None
        # with warmup_sessions=0 (for ablation) sess_ranges may be empty
        self.adr = (sum(self.sess_ranges) / len(self.sess_ranges)) if self.sess_ranges else 0.0

        n = len(self.c)
        if n < max(p.lookback, p.ema_period) + 4:
            return None

        L = p.lookback
        self.avg_range = sum(self.rng(i) for i in range(1, L + 1)) / L
        self.avg_body = max(sum(self.body(i) for i in range(1, L + 1)) / L, self.tk)

        magap = self._ma_gap(n)
        micro = self._micro(n)
        bull_sig, bear_sig = self._signal(True), self._signal(False)

        failed_up = self.prev_bo_up >= 6 and (self.bear_tb(0) or (self.inside(0) and self.C(0) < self.O(0)))
        failed_dn = self.prev_bo_dn >= 6 and (self.bull_tb(0) or (self.inside(0) and self.C(0) > self.O(0)))
        bo_up, bo_dn = self._breakout(True), self._breakout(False)
        self.prev_bo_up, self.prev_bo_dn = bo_up, bo_dn

        trend = self._trend(magap, micro)
        ttr = self._ttr()
        he, le = self._bar_count(n)
        if p.strategy == "abc":
            self._abc_update(1, n); self._abc_update(-1, n)
        self._swings(n)
        mm_up, mm_dn = self._measured_moves()
        self._update_always_in()                       # P2-11

        if ttr: state = "TightTradingRange"
        elif trend >= 6: state = "StrongBullTrend"
        elif trend <= -6: state = "StrongBearTrend"
        elif trend >= 3: state = "BullChannel"
        elif trend <= -3: state = "BearChannel"
        else: state = "TradingRange"

        f = dict(state=state, trend=trend, ttr=ttr, ma_gap=magap, micro=micro,
                 bull_sig=bull_sig, bear_sig=bear_sig, bo_up=bo_up, bo_dn=bo_dn,
                 failed_up=failed_up, failed_dn=failed_dn, h_count=self.hc, l_count=self.lc,
                 h_event=he, l_event=le, mm_up=mm_up, mm_dn=mm_dn,
                 adr=self.adr, avg_range=self.avg_range,
                 always_in=self.always_in,
                 climax_up=self._climax_bars_ago(1), climax_dn=self._climax_bars_ago(-1),
                 range_pos=self._range_pos(self.C(0)),
                 signal=0, type="none", entry=math.nan, stop=math.nan, target=math.nan, quality=0.0)

        if p.strategy == "pullback":
            self._entry_pullback(f)
        elif p.strategy == "pullback2":
            self._entry_pullback(f, refined=True)
        elif p.strategy == "open_trend":
            self._entry_open_trend(f)
        elif p.strategy == "abc":
            self._entry_abc(f)
        elif p.strategy == "fade":
            self._entry_fade(f)
        elif p.strategy == "ai":
            self._entry_always_in(f)
        else:
            self._entry(f)
        return f

    # ---------------------------------------------------------------- features
    def _ma_gap(self, n):
        mx = min(n - 1 - self.p.ema_period, 200)
        k = 0
        if self.L(0) > self.E(0):
            while k < mx and self.L(k) > self.E(k): k += 1
            return k
        if self.H(0) < self.E(0):
            while k < mx and self.H(k) < self.E(k): k += 1
            return -k
        return 0

    def _micro(self, n):
        mx = min(n - 2, 50)
        up = dn = 0
        while up < mx and self.L(up) >= self.L(up + 1): up += 1
        while dn < mx and self.H(dn) <= self.H(dn + 1): dn += 1
        return up if up >= dn else -dn

    def _signal(self, bull):
        d = 1 if bull else -1
        ok = (self.C(0) > self.O(0) or self.cpos(0) > 0.5) if bull else \
             (self.C(0) < self.O(0) or self.cpos(0) < 0.5)
        if not ok: return 0
        s = 0
        if d * (self.C(0) - self.O(0)) > 0: s += 2
        if d * (self.O(0) - self.C(1)) <= self.tk: s += 1
        if d * (self.C(0) - self.C(1)) > 0: s += 1
        rej = (self.ltail(0) if bull else self.utail(0)) / self.rng(0)
        opp = (self.utail(0) if bull else self.ltail(0)) / self.rng(0)
        if 0.25 <= rej <= 0.6: s += 2
        if opp <= 0.15: s += 1
        if self.overlap(0) <= 0.5: s += 1
        k = 1
        while k <= self.p.lookback and d * (self.C(0) - self.C(k)) > 0: k += 1
        if k - 1 >= 5: s += 2
        elif k - 1 >= 2: s += 1
        return min(s, 10)

    def _breakout(self, up):
        if not (self.bull_tb(0) if up else self.bear_tb(0)): return 0
        d = 1 if up else -1
        s = 0
        if self.body(0) >= 1.5 * self.avg_body: s += 2
        elif self.body(0) >= self.avg_body: s += 1
        if (self.cpos(0) >= 0.8) if up else (self.cpos(0) <= 0.2): s += 1
        if (self.utail(0) if up else self.ltail(0)) <= 0.1 * self.rng(0): s += 1
        k = 1
        while k <= self.p.lookback and (self.C(0) > self.H(k) if up else self.C(0) < self.L(k)): k += 1
        b = k - 1
        s += 3 if b >= 10 else 2 if b >= 5 else 1 if b >= 2 else 0
        if d * (self.O(0) - self.C(1)) >= 0: s += 1
        if self.bull_tb(1) if up else self.bear_tb(1): s += 1
        if up and self.bull_tb(1) and self.L(0) >= self.H(2): s += 1
        if not up and self.bear_tb(1) and self.H(0) <= self.L(2): s += 1
        return min(s, 10)

    def _trend(self, magap, micro):
        L = self.p.lookback
        bulls = sum(1 for i in range(L) if self.bull_tb(i))
        bears = sum(1 for i in range(L) if self.bear_tb(i))
        above = sum(1 for i in range(L) if self.C(i) > self.E(i))
        path = sum(abs(self.C(i) - self.C(i + 1)) for i in range(L))
        er = (self.C(0) - self.C(L)) / path if path > 0 else 0.0
        s = 3.0 * (bulls - bears) / L + 2.0 * max(-20, min(20, magap)) / 20.0 \
            + 2.0 * (2.0 * above / L - 1) + 2.0 * er
        if abs(micro) >= 5: s += 1 if micro > 0 else -1
        return round(max(-10.0, min(10.0, s)), 2)

    # ---- P0-2: multi-window tight trading range ------------------------------------
    def _ttr(self):
        p = self.p
        if not p.use_ttr_filter: return False
        navail = len(self.c) - 1
        for N in p.ttr_windows:
            if N > navail: continue
            height = max(self.H(i) for i in range(N)) - min(self.L(i) for i in range(N))
            ov = sum(self.overlap(i) for i in range(N)) / N
            dojis = sum(1 for i in range(N) if self.doji(i)) / N
            avg_bar = sum(self.rng(i) for i in range(N)) / N
            # Thresholds scale with sqrt(N): a random walk's range already grows with sqrt(N),
            # so without scaling short windows would flag normal consolidation as tight (63% false positives at 4 bars in tests).
            # ttr_bars is the reference window; with N == ttr_bars this matches v1.
            scale = (N / float(p.ttr_bars)) ** 0.5
            if self.adr > 0:
                narrow = height <= p.ttr_frac * self.adr * scale
            else:
                narrow = height <= p.ttr_bar_mult * avg_bar * scale
            if narrow and (ov >= 0.5 or dojis >= 0.3):
                return True
        return False

    # ---- P0-3: climax detection ------------------------------------------------------
    def _climax_bars_ago(self, d, maxlook=None, skip=0):
        """Bars since the last same-direction climax; 999 if none.
        Brooks defines a climax broadly: any unsustainable behaviour. Three computable approximations are used here.
        skip: how many bars back to start looking. Breakout entries pass 1 because a big breakout bar is normal;
        what should be blocked is "the next breakout after a climax"."""
        p = self.p
        if not p.use_climax_filter: return 999
        maxlook = maxlook or (p.climax_lookback * 2)
        n = len(self.c) - 1
        for k in range(skip, min(maxlook + skip, n - 2)):
            if not self._tb(d, k): continue
            if self.body(k) >= p.climax_body_mult * self.avg_body:
                return k
            if (self._tb(d, k + 1) and self._tb(d, k + 2)
                    and self.body(k) > self.body(k + 1) > self.body(k + 2)):
                return k
            if abs(self.C(k) - self.E(k)) >= p.climax_ma_mult * self.avg_range:
                return k
        return 999

    # ---- P0-4: position in the range ------------------------------------------------------
    def _range_pos(self, price, N=None):
        N = N or self.p.pos_bars
        N = min(N, len(self.c) - 1)
        if N < 2: return 0.5
        hi = max(self.H(i) for i in range(N))
        lo = min(self.L(i) for i in range(N))
        return (price - lo) / max(hi - lo, self.tk)

    def _position_ok(self, d, entry, trend, ttr=False, typ=None):
        """Three regimes:
        - Range / no trend (tight, or |trend score| < pos_apply_trend): every entry follows the "thirds" rule,
          no buys in the top third and no sells in the bottom third.
        - Channel (pos_apply_trend <= |trend score| < strong_trend): only breakout entries are checked, and only at the extremes.
          Based on "trade a bull channel as a bear flag": breakout longs at the top of a channel are on the wrong side.
          With-trend pullbacks inside a channel are allowed; Brooks himself buys H1/H2 in bull channels.
        - Strong trend (|trend score| >= strong_trend): everything is allowed; new highs in a strong bull trend are meant to be bought.
        """
        p = self.p
        if not p.use_position_filter: return True
        at = abs(trend)
        if at >= p.strong_trend: return True
        pos = self._range_pos(entry, p.pos_window)
        if ttr or at < p.pos_apply_trend:                      # treat as a trading range
            if d > 0 and pos > p.pos_hi: return False
            if d < 0 and pos < p.pos_lo: return False
            return True
        if p.use_channel_flag and typ == "breakout":           # chasing a breakout at the end of a channel
            if d > 0 and pos > p.pos_channel_extreme: return False
            if d < 0 and pos < 1.0 - p.pos_channel_extreme: return False
        return True

    # ---- P2-11: global always-in state -------------------------------------------
    def _update_always_in(self):
        """The flip is confirmed at the close of the follow-through bar (the second trend bar).
        The follow-through bar must not close the other way, and must close at least ai_follow_ticks beyond the breakout bar's extreme."""
        p = self.p
        if len(self.c) < p.lookback + 3: return
        bo, ft = 1, 0                      # k=1 is the breakout bar, k=0 the follow-through bar
        if self.body(bo) < 1.5 * self.avg_body: return
        prior_hi = max(self.H(k) for k in range(bo + 1, bo + 11))
        prior_lo = min(self.L(k) for k in range(bo + 1, bo + 11))
        if self.bull_tb(bo) and self.C(bo) > prior_hi:
            if self.C(ft) >= self.O(ft) and self.C(ft) - self.H(bo) >= p.ai_follow_ticks * self.tk:
                self.always_in = 1
                self.ai_flip_bar = len(self.c) - 1
        elif self.bear_tb(bo) and self.C(bo) < prior_lo:
            if self.C(ft) <= self.O(ft) and self.L(bo) - self.C(ft) >= p.ai_follow_ticks * self.tk:
                self.always_in = -1
                self.ai_flip_bar = len(self.c) - 1

    def _bar_count(self, n):
        """Simplified H1-H4 / L1-L4: only requires a lower high between two counts;
        a real micro trendline break check is not implemented yet (see review item P2-13)."""
        cb, maxage = n - 1, self.p.lookback * 3
        he = le = 0
        if self.H(0) > self.bull_leg_h or cb - self.bull_leg_bar > maxage:
            self.bull_leg_h, self.bull_leg_bar, self.bull_pb, self.bull_need_dn, self.hc = self.H(0), cb, False, False, 0
        elif self.H(0) < self.H(1):
            self.bull_pb, self.bull_need_dn = True, False
        elif self.bull_pb and not self.bull_need_dn and self.H(0) > self.H(1):
            self.hc = min(self.hc + 1, 4); he = self.hc; self.bull_need_dn = True
            if self.hc == 1: self.bull_h1_entry = self.H(1) + self.tk

        if self.L(0) < self.bear_leg_l or cb - self.bear_leg_bar > maxage:
            self.bear_leg_l, self.bear_leg_bar, self.bear_pb, self.bear_need_up, self.lc = self.L(0), cb, False, False, 0
        elif self.L(0) > self.L(1):
            self.bear_pb, self.bear_need_up = True, False
        elif self.bear_pb and not self.bear_need_up and self.L(0) < self.L(1):
            self.lc = min(self.lc + 1, 4); le = self.lc; self.bear_need_up = True
            if self.lc == 1: self.bear_l1_entry = self.L(1) - self.tk
        return he, le

    def _swings(self, n):
        s = self.p.swing_strength
        if n < 2 * s + 2: return
        hi = all(self.H(s) > self.H(s + k) and self.H(s) >= self.H(s - k) for k in range(1, s + 1))
        lo = all(self.L(s) < self.L(s + k) and self.L(s) <= self.L(s - k) for k in range(1, s + 1))
        for is_high, flag, price in ((True, hi, self.H(s)), (False, lo, self.L(s))):
            if not flag: continue
            if self.swings and self.swings[-1][1] == is_high:
                last = self.swings[-1][0]
                if (price > last) if is_high else (price < last):
                    self.swings[-1] = (price, is_high)
            else:
                self.swings.append((price, is_high))
                self.swings = self.swings[-8:]

    # ---- P2-10: micro measuring gap (projected from the midpoint) -------------------------------------
    def _micro_measuring_gap(self, d):
        """The bars before and after a strong trend bar do not overlap -> take their midpoint and project from the start of the leg.
        Target = 2 x midpoint - leg start. The gap height itself is not in the formula; it only locates the midpoint."""
        n = len(self.c) - 1
        leg_start = None
        for pr, is_high in reversed(self.swings):
            if (d > 0 and not is_high) or (d < 0 and is_high):
                leg_start = pr; break
        if leg_start is None: return math.nan
        for k in range(1, min(15, n - 1)):
            if not self._tb(d, k): continue
            if d > 0 and self.L(k - 1) >= self.H(k + 1):
                mid = (self.H(k + 1) + self.L(k - 1)) / 2
                return 2 * mid - leg_start
            if d < 0 and self.H(k - 1) <= self.L(k + 1):
                mid = (self.L(k + 1) + self.H(k - 1)) / 2
                return 2 * mid - leg_start
        return math.nan

    def _measured_moves(self):
        up = dn = math.nan
        if len(self.swings) >= 3:
            (a, ah), (b, bh), (c, ch) = self.swings[-3:]
            up = c + (b - a) if (not ah and bh and not ch and c > a) else math.nan
            dn = c - (a - b) if (ah and not bh and ch and c < a) else math.nan
        # Micro measuring gaps take priority: they occur more often than the three-point swing method and follow the book more closely
        g_up, g_dn = self._micro_measuring_gap(1), self._micro_measuring_gap(-1)
        if not math.isnan(g_up) and g_up > self.C(0): up = g_up
        if not math.isnan(g_dn) and g_dn < self.C(0): dn = g_dn
        return up, dn

    # ---------------------------------------------------------------- stop construction
    def _stop_for(self, d, entry):
        """P1-6 two-bar reversal + P1-7 small signal bar padding + 8-tick cap.
        Returns (entry, stop); a two-bar reversal can also move the entry."""
        p = self.p
        two_bar = p.use_two_bar_reversal and self.overlap(0) >= p.two_bar_overlap
        if two_bar:
            if d > 0:
                entry = max(self.H(0), self.H(1)) + self.tk
                base = min(self.L(0), self.L(1))
            else:
                entry = min(self.L(0), self.L(1)) - self.tk
                base = max(self.H(0), self.H(1))
        else:
            base = self.L(0) if d > 0 else self.H(0)
        pad = self.tk
        if p.use_small_bar_pad and self.rng(0) < p.small_bar_frac * self.avg_range:
            pad = p.small_bar_ticks * self.tk
        stop = base - d * pad
        # Total risk cap: Brooks' price action stops are no more than 8 ticks beyond the entry
        if abs(entry - stop) > p.stop_max_ticks * self.tk:
            if p.stop_too_wide == "reject":
                return entry, None
            stop = entry - d * p.stop_max_ticks * self.tk
        return entry, stop

    def _risk_ok(self, risk):
        p = self.p
        if risk <= 0: return False
        # Skip this cap when adr is unknown; otherwise adr=0 would block every signal (rather than meaning "risk too big")
        if self.adr > 0 and risk > p.max_risk_frac_adr * self.adr: return False
        if risk < p.min_risk_frac_range * self.avg_range: return False   # P1-8 minimum
        return True

    # ---------------------------------------------------------------- entry candidates
    def _entry(self, f):
        p = self.p
        if f["ttr"]: return
        trend = f["trend"]
        strong = abs(trend) >= p.strong_trend
        near = self.L(0) <= self.E(0) + self.avg_range and self.H(0) >= self.E(0) - self.avg_range
        if trend >= p.min_trend and self.bull_pb and not self.bull_need_dn and f["h_event"] == 0 \
                and (strong or self.hc >= 1) and (strong or near) and f["bull_sig"] >= p.min_signal:
            self._try(f, 1, "pullback", f["mm_up"], f["bull_sig"])
        elif trend <= -p.min_trend and self.bear_pb and not self.bear_need_up and f["l_event"] == 0 \
                and (strong or self.lc >= 1) and (strong or near) and f["bear_sig"] >= p.min_signal:
            self._try(f, -1, "pullback", f["mm_dn"], f["bear_sig"])
        # P0-5: breakout entries need a real trend; no breakout chasing inside trading ranges
        elif f["bo_up"] >= p.min_breakout and (trend >= p.min_trend if p.breakout_needs_trend else trend >= 0):
            self._try(f, 1, "breakout", f["mm_up"], f["bo_up"], market=True)
        elif f["bo_dn"] >= p.min_breakout and (trend <= -p.min_trend if p.breakout_needs_trend else trend <= 0):
            self._try(f, -1, "breakout", f["mm_dn"], f["bo_dn"], market=True)

    def _pullback_ok(self, d, leg_bar):
        n = len(self.c) - 1 - leg_bar
        run = best = big = 0
        for k in range(min(n, 60)):
            cntr = self.bear_tb(k) if d > 0 else self.bull_tb(k)
            run = run + 1 if cntr else 0
            best = max(best, run)
            if cntr and self.body(k) >= 1.5 * self.avg_body: big += 1
        return best <= self.p.max_cntr_run and big <= self.p.max_big_cntr

    def _entry_pullback(self, f, refined=False):
        p = self.p
        if f["ttr"]: return
        n_above = sum(1 for i in range(p.dir_bars) if self.C(i) > self.E(i))
        n_below = p.dir_bars - n_above
        near = self.L(0) <= self.E(0) + self.avg_range and self.H(0) >= self.E(0) - self.avg_range
        if not near: return
        f["dir_above"] = n_above
        if n_above >= p.dir_min and self.bull_pb and not self.bull_need_dn and f["h_event"] == 0 \
                and self.hc >= p.min_h_count and self.C(0) > self.O(0) and self.cpos(0) > 0.5:
            if f["climax_up"] <= p.climax_lookback: return          # P0-3
            entry, stop = self._stop_for(1, self.H(0) + self.tk)
            if stop is None: return
            if not self._position_ok(1, entry, f["trend"], f["ttr"]): return  # P0-4
            if refined and not (f["trend"] >= p.min_trend and self._pullback_ok(1, self.bull_leg_bar)
                                and (self.hc == 0 or self.bull_h1_entry is None or entry >= self.bull_h1_entry - self.tk)):
                return
            self._set_pb(f, 1, entry, stop, self.bull_leg_h, self.hc + 1)
        elif n_below >= p.dir_min and self.bear_pb and not self.bear_need_up and f["l_event"] == 0 \
                and self.lc >= p.min_h_count and self.C(0) < self.O(0) and self.cpos(0) < 0.5:
            if f["climax_dn"] <= p.climax_lookback: return
            entry, stop = self._stop_for(-1, self.L(0) - self.tk)
            if stop is None: return
            if not self._position_ok(-1, entry, f["trend"], f["ttr"]): return
            if refined and not (f["trend"] <= -p.min_trend and self._pullback_ok(-1, self.bear_leg_bar)
                                and (self.lc == 0 or self.bear_l1_entry is None or entry <= self.bear_l1_entry + self.tk)):
                return
            self._set_pb(f, -1, entry, stop, self.bear_leg_l, self.lc + 1)

    # ---------------------------------------------------------------- ABC pullback
    @staticmethod
    def _abc_new():
        return dict(ext=-INF, bar=0, pb=False, need=False, cnt=0, ev=0,
                    a_low=None, a_bar=None, b_high=None, b_bar=None)

    def _abc_update(self, d, n):
        st, cb = self.abc[d], n - 1
        st["ev"] = 0
        h0, h1 = self._hi(d, 0), self._hi(d, 1)
        if h0 > st["ext"] or cb - st["bar"] > self.p.lookback * 3:
            self.abc[d] = st = self._abc_new()
            st["ext"], st["bar"] = h0, cb
            return
        if h0 < h1:
            st["pb"], st["need"] = True, False
        elif st["pb"] and not st["need"] and h0 > h1:
            st["cnt"] = min(st["cnt"] + 1, 4); st["ev"] = st["cnt"]; st["need"] = True
            if st["cnt"] == 1:
                span = cb - st["bar"]
                k_low = min(range(span + 1), key=lambda k: self._lo(d, k))
                st["a_low"], st["a_bar"] = self._lo(d, k_low), cb - k_low
                st["b_high"], st["b_bar"] = h0, cb
        if st["cnt"] >= 1 and st["b_high"] is not None and h0 > st["b_high"]:
            st["b_high"], st["b_bar"] = h0, cb

    def _entry_abc(self, f):
        p, n = self.p, len(self.c)
        if f["ttr"]: return
        n_above = sum(1 for i in range(p.dir_bars) if self.C(i) > self.E(i))
        near = self.L(0) <= self.E(0) + self.avg_range and self.H(0) >= self.E(0) - self.avg_range
        if not near: return
        mid_in = min(self.H(1), max(self.H(0), self.H(2))) - max(self.L(1), min(self.L(0), self.L(2)))
        if mid_in >= 0.5 * self.rng(1) and (self.doji(0) or self.doji(1) or self.doji(2)): return
        for d in (1, -1):
            if d > 0 and not (n_above >= p.dir_min and f["trend"] >= p.min_trend): continue
            if d < 0 and not (p.dir_bars - n_above >= p.dir_min and f["trend"] <= -p.min_trend): continue
            if (f["climax_up"] if d > 0 else f["climax_dn"]) <= p.climax_lookback: continue
            if self._abc_ok(d, n):
                entry, stop = self._stop_for(d, self.H(0) + self.tk if d > 0 else self.L(0) - self.tk)
                if stop is None: continue
                if not self._position_ok(d, entry, f["trend"], f["ttr"]): continue
                self._set_pb(f, d, entry, stop, 0, self.abc[d]["cnt"] + 1)
                f["type"] = "abc"                     # fix: no longer labelled as pullback
                return

    def _abc_ok(self, d, n):
        st, cb = self.abc[d], n - 1
        if not (st["pb"] and not st["need"] and st["ev"] == 0 and st["cnt"] in (1, 2)): return False
        if st["a_low"] is None or st["b_bar"] is None: return False
        if d > 0 and not (self.C(0) > self.O(0) and self.cpos(0) > 0.5): return False
        if d < 0 and not (self.C(0) < self.O(0) and self.cpos(0) < 0.5): return False
        if self.doji(0): return False
        a_size = st["ext"] - st["a_low"]
        if a_size <= 0 or (cb - st["bar"]) < 2: return False
        if st["b_high"] - st["a_low"] < 0.3 * a_size: return False
        if not any(self._tb(d, cb - j) for j in range(st["a_bar"], st["b_bar"] + 1)): return False
        run = best = big = 0
        for j in range(st["b_bar"] + 1, cb + 1):
            k = cb - j
            cntr = self._tb(-d, k)
            run = run + 1 if cntr else 0
            best = max(best, run)
            if cntr and self.body(k) >= 1.5 * self.avg_body: big += 1
        if best > self.p.max_cntr_run or big > self.p.max_big_cntr: return False
        c_low = min(self._lo(d, cb - j) for j in range(st["b_bar"], cb + 1))
        if c_low < st["a_low"] - self.avg_range: return False
        return True

    # ---------------------------------------------------------------- fade failed range breakouts
    def _entry_fade(self, f):
        p = self.p
        if f["ttr"] or abs(f["trend"]) >= p.min_trend: return
        if len(self.c) < 23: return
        rh = max(self.H(k) for k in range(2, 22))
        rl = min(self.L(k) for k in range(2, 22))
        mid = (rh + rl) / 2
        not_strong = self.rng(1) <= 1.5 * self.avg_range
        if self.bull_tb(1) and self.C(1) > rh and not_strong and not self.bull_tb(2) \
                and (self.bear_tb(0) or (self.inside(0) and self.C(0) < self.O(0))):
            entry = self.L(0) - self.tk
            stop = max(self.H(0), self.H(1)) + self.tk
            risk, reward = stop - entry, entry - mid
            if self._risk_ok(risk) and reward >= p.min_rr * risk \
                    and self._position_ok(-1, entry, f["trend"], f["ttr"], "fade"):
                # Quality scores use the same 0-10 scale. Previously this was hard-coded to 0.0, so any --min-quality > 0
                # silently removed the whole fade strategy.
                f.update(signal=-1, type="fade", entry=entry, stop=stop, target=mid,
                         quality=round(0.5 * f["bear_sig"] + 0.5 * min(10, abs(f["trend"])), 1))
            return
        if self.bear_tb(1) and self.C(1) < rl and not_strong and not self.bear_tb(2) \
                and (self.bull_tb(0) or (self.inside(0) and self.C(0) > self.O(0))):
            entry = self.H(0) + self.tk
            stop = min(self.L(0), self.L(1)) - self.tk
            risk, reward = entry - stop, mid - entry
            if self._risk_ok(risk) and reward >= p.min_rr * risk \
                    and self._position_ok(1, entry, f["trend"], f["ttr"], "fade"):
                f.update(signal=1, type="fade", entry=entry, stop=stop, target=mid,
                         quality=round(0.5 * f["bull_sig"] + 0.5 * min(10, abs(f["trend"])), 1))

    # ---------------------------------------------------------------- always-in reversal strategy
    def _entry_always_in(self, f):
        p = self.p
        if len(self.c) < 16: return
        hi = max(self.H(k) for k in range(3, 13)); lo = min(self.L(k) for k in range(3, 13))
        ov = sum(self.overlap(k) for k in range(3, 12)) / 9
        if self.adr > 0 and hi - lo <= p.ttr_frac * self.adr and ov >= 0.5: return

        def strong_bull(k):
            return self.C(k) > self.O(k) and self.body(k) >= self.avg_body and self.cpos(k) >= 2 / 3
        def strong_bear(k):
            return self.C(k) < self.O(k) and self.body(k) >= self.avg_body and self.cpos(k) <= 1 / 3

        if strong_bull(2) and strong_bull(1) and self.C(1) > hi and self.C(0) >= self.O(0):
            entry = self.C(0)
            stop = min(self.L(1), self.L(2)) - self.tk
            risk = entry - stop
            if self._risk_ok(risk) and risk <= 0.5 * self.adr:
                f.update(signal=1, type="ai_flip", entry=entry, stop=stop,
                         target=entry + max(p.min_rr, 1.0) * risk, quality=0.0)
            return
        if strong_bear(2) and strong_bear(1) and self.C(1) < lo and self.C(0) <= self.O(0):
            entry = self.C(0)
            stop = max(self.H(1), self.H(2)) + self.tk
            risk = stop - entry
            if self._risk_ok(risk) and risk <= 0.5 * self.adr:
                f.update(signal=-1, type="ai_flip", entry=entry, stop=stop,
                         target=entry - max(p.min_rr, 1.0) * risk, quality=0.0)

    # ---------------------------------------------------------------- trend from the open
    def _ot_reset(self):
        self.ot_dir, self.ot_count, self.ot_spike = 0, 0, False
        self.ot_ext = None
        self.ot_done = False
        self.ot_pending = None

    def _entry_open_trend(self, f):
        p = self.p
        k = self.sess_bar
        if self.ot_pending is not None:
            lvl, d = self.ot_pending
            if (d > 0 and self.H(0) >= lvl) or (d < 0 and self.L(0) <= lvl):
                self.ot_done = True
            self.ot_pending = None
        if self.ot_done or k < 0: return
        if f["ttr"]: return                                 # added: no trades in a tight trading range

        if not self.ot_spike:
            up = self.C(0) > self.O(0) and (k == 0 or self.C(0) > self.C(1))
            dn = self.C(0) < self.O(0) and (k == 0 or self.C(0) < self.C(1))
            if k == 0:
                self.ot_dir, self.ot_count = (1, 1) if up else (-1, 1) if dn else (0, 0)
            elif (self.ot_dir > 0 and up) or (self.ot_dir < 0 and dn):
                self.ot_count += 1
            else:
                self.ot_done = True
                return
            if self.ot_dir == 0:
                self.ot_done = True; return
            if self.ot_count >= p.ot_spike_bars:
                move = abs(self.C(0) - self.sess_open)
                if move >= p.ot_spike_adr * self.adr:
                    self.ot_spike = True
                    self.ot_ext = self.H(0) if self.ot_dir > 0 else self.L(0)
            return

        d = self.ot_dir
        if k > p.ot_last_bar: self.ot_done = True; return
        if d > 0:
            if self.L(0) <= self.sess_open: self.ot_done = True; return
            if self.H(0) > self.ot_ext and self.H(0) >= self.H(1):
                self.ot_ext = self.H(0); return
            if self.H(0) < self.H(1) and self.cpos(0) >= 0.5:
                entry, stop = self._stop_for(1, self.H(0) + self.tk)
                if stop is None: return
                self._set_pb(f, 1, entry, stop, self.ot_ext, 1)
        else:
            if self.H(0) >= self.sess_open: self.ot_done = True; return
            if self.L(0) < self.ot_ext and self.L(0) <= self.L(1):
                self.ot_ext = self.L(0); return
            if self.L(0) > self.L(1) and self.cpos(0) <= 0.5:
                entry, stop = self._stop_for(-1, self.L(0) - self.tk)
                if stop is None: return
                self._set_pb(f, -1, entry, stop, self.ot_ext, 1)
        if f["signal"] != 0:
            f["type"] = "open_trend"
            self.ot_pending = (f["entry"], f["signal"])

    # ---------------------------------------------------------------- order construction
    def _set_pb(self, f, d, entry, stop, extreme, count):
        p = self.p
        risk = abs(entry - stop)
        if not self._risk_ok(risk): return
        if p.target_mode == "1R":
            target = entry + d * risk
        elif p.target_mode == "eod":
            target = entry + d * 1000 * risk
        elif p.target_mode == "extreme":
            if d * (extreme - entry) < risk: return
            target = extreme
        else:
            target = entry + d * 2 * risk
        if p.target_mode != "eod" and abs(target - entry) < p.min_rr * risk: return   # P1-9
        # The quality score must use the same 0-10 scale as _try. Previously this put the H/L count (1-4) here,
        # so the same --min-quality threshold meant different things on the two entry paths:
        # --min-quality 5 silently removed every _set_pb pullback order and kept only _try signals.
        sig = f["bull_sig"] if d > 0 else f["bear_sig"]
        f.update(signal=d, type="pullback", entry=entry, stop=stop, target=target,
                 quality=round(0.5 * sig + 0.5 * min(10, abs(f["trend"])), 1),
                 h_count=int(count))

    def _try(self, f, d, typ, mm, setup, market=False):
        """P1-9: removed the win_prob expectancy filter; replaced with a hard min_rr."""
        p = self.p
        # P0-3b: breakout entries also check for climaxes. Previously only pullback/ABC entries did,
        # so the most typical bad trade, "chasing a breakout on a climax bar", was never blocked
        # (59 signals in 60 days of synthetic data landed on climax bars).
        # Skip the current bar: a big breakout bar is normal; what should be blocked is "the next breakout after a climax".
        if p.use_climax_filter and typ == "breakout":
            if self._climax_bars_ago(d, skip=p.climax_skip_current) <= p.climax_lookback:
                return
        if market:
            entry = self.C(0)
            stop = (self.L(0) if d > 0 else self.H(0)) - d * self.tk
        else:
            entry, stop = self._stop_for(d, (self.H(0) if d > 0 else self.L(0)) + d * self.tk)
            if stop is None: return
        if not self._position_ok(d, entry, f["trend"], f["ttr"], typ): return
        risk = abs(entry - stop)
        if not self._risk_ok(risk): return
        target = mm if (not math.isnan(mm) and d * (mm - entry) > p.min_rr * risk) \
            else entry + d * risk * p.fallback_rr
        if abs(target - entry) < p.min_rr * risk: return
        f.update(signal=d, type=typ, entry=entry, stop=stop, target=target,
                 quality=round(0.5 * setup + 0.5 * min(10, abs(f["trend"])), 1))
