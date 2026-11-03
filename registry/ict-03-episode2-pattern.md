# ICT-03: only the strict Episode 2 pattern (H-ICT3)

> The original registration was committed to the author's private repository before the backtest; the commit time is the evidence. This is a faithful translation with personal details removed.

## Registration (2026-10-16, before any result was seen)

Origin: after H-ICT1 and H-ICT2 failed, someone asked "can you make money trading only the pattern from Episode 2?". Script `ict/research_ep2.py`; `ictlib.py` parameters unchanged.

Conditions (all required): 1 the level swept is a relative equal high / equal low; 2 earlier that day (from 00:00 New York), before the sweep, price first broke the Asia low (short) / Asia high (long); 3 New York morning session; 4 in line with the daily bias (the weekly bias cannot be judged automatically, so the daily bias is used); 5 the entry is in the premium (short) / discount (long) half of today's range (00:00 to now).
Target: the nearest old high/low or today's unfilled 1-minute imbalance on the other side of the 50% line; no trade if none. Entry at the near edge of the FVG, stop 2 ticks beyond the sweep extreme, costs as in H-ICT1. Baseline: mirror trades with the same time and distances on the opposite side.

**Pass criteria (all required)**:
1. ES 2010-2023, NQ 2010-2025 and MES 2023-09 to 2025-09 combined: ≥ 100 filled trades meeting every condition;
2. Combined average R per trade after costs > +0.05 with t ≥ 2;
3. Combined, each setup better than its mirror by > 0 with paired t ≥ 2;
4. ES combined and NQ combined each with average R per trade > 0.
With fewer than 100 fills the verdict is "sample too small to judge", with no conclusion either way. Exploratory groups are not pass criteria. MES after 2025-09-01 stays locked.

Run: `python3 ict/research_ep2.py data.csv --symbol ES --name es_2010_2018 --before 2025-09-01`

## Verdict

Date: 2026-10-16. Conditions: equal highs/lows + inducement first + NY morning + with daily bias + premium/discount; target is the nearest old high/low or imbalance beyond the 50% line.

| Period | Qualifying setups | Filled | Win rate | Avg R per trade (after costs) | t | vs mirror | Paired t |
|---|---|---|---|---|---|---|---|
| ES 2010-2018 | 240 | 118 | 45% | −0.207 | −1.85 | −0.030 | −0.29 |
| ES 2019-2023 | 188 | 91 | 41% | −0.134 | −0.94 | +0.035 | +0.32 |
| NQ 2010-2023 | 656 | 328 | 41% | −0.210 | −2.79 | +0.002 | +0.03 |
| NQ 2023-2025 | 79 | 41 | 44% | +0.099 | +0.42 | +0.209 | +1.12 |
| MES 2023-2025 | 81 | 48 | 54% | +0.299 | +1.38 | +0.207 | +0.92 |
| **ES combined** | 428 | 209 | 43% | −0.176 | −1.98 | −0.001 | −0.02 |
| **NQ combined** | 735 | 369 | 41% | −0.176 | −2.44 | +0.024 | +0.40 |
| **All combined** | 1244 | 626 | 43% | **−0.139** | **−2.55** | +0.027 | +0.59 |

Criterion 1, ≥ 100 fills: met (626). Criterion 2, average R > +0.05 with t ≥ 2: not met (−0.139, t = −2.55, significantly negative). Criterion 3, better than mirror with t ≥ 2: not met (t = 0.59). Criterion 4, ES and NQ each > 0: not met.
**Verdict: H-ICT3 fails.** With every Episode 2 condition added, the loss per trade is a little smaller than without them (about −0.18R) but still significantly negative, and no better than a random direction.
The two 2023-2025 periods are positive, but each has only about 40 trades with t below 1.5 and they were picked after the fact, so no conclusion can be drawn. Testing them would require a new registration using the locked MES data after 2025-09.
