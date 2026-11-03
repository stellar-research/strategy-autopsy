# ICT-01: 2022 Mentorship intraday model (H-ICT1)

> The original registration was committed to the author's private repository before the backtest; the commit time is the evidence. This is a faithful translation with personal details removed.

## Registration

### Hypothesis H-ICT1
The ICT 2022 Mentorship intraday model implemented by `ict/ictlib.py` with default parameters (no tuning):
inside a kill zone, **liquidity sweep → opposite market structure shift (MSS) → FVG → enter on return to the FVG**,
stop beyond the sweep extreme, target at the next liquidity level (2R if there is no suitable target),
has positive expectancy after costs on 1-minute index futures data, and beats a "same time, same distances, opposite side" mirror trade.

### Data (Databento CME 1-minute data, not included)
| Use | Data |
|---|---|
| Test | ES 1-minute 2010-06-06 to 2019-01-01, ES 1-minute 2019-01-01 to 2023-09-01 |
| Test | NQ 1-minute 2010-06-06 to 2023-09-01, NQ 1-minute 2023-09-01 to 2025-09-01 |
| Test | MES 1-minute 2023-09-01 to **before 2025-09-01** |
| **Locked, not used** | MES 2025-09-01 to 2026-09-01 |

### Cost assumptions (micro contracts, same as the Brooks experiments)
- Commission: 1.70 USD round trip per contract (MES 5 USD per point → 0.34 points; MNQ 2 USD per point → 0.85 points)
- Slippage: 1 tick (0.25 points) on stop exits and forced exits at the close; no slippage on FVG limit entries and target limit exits
- A bar touching both stop and target counts as a stop; on the trigger bar only the stop counts

### Pass criteria (all three must hold)
1. **ES 2010-2023 combined**: ≥ 300 filled trades, average R after costs > +0.05 with t ≥ 2 against 0, **and** paired difference vs mirror trades with t ≥ 2
2. **NQ 2010-2025 combined**: average R after costs > 0, and positive paired difference vs mirror trades
3. **Stability**: of the 5 periods ES 2010-2018, ES 2019-2023, NQ 2010-2023, NQ 2023-2025 and MES 2023-2025, at least 4 have average R after costs > 0

Only if all pass is the locked last year of MES used once for a final test.
Results by session, bias, level and direction are **exploratory only** (more groups make chance results more likely) and cannot be used to pass.

### If it fails
Parameters are not tuned and rerun to "rescue" the result. New hypotheses (H-ICT2...) may be proposed from the grouped results, but must be registered before testing in the same way.

Run: `python3 ict/research.py data.csv --symbol ES --name es_2010_2018 --before 2025-09-01`

## Verdict

Date: 2026-10-15. Data: Databento 1-minute, ES 2010-2023, NQ 2010-2025, MES 2023-09 to 2025-09 (after 2025-09 locked and unused).

| Period | Trades | Win rate | Avg R (before costs) | Avg R (after costs) | t | vs mirror | t (paired) |
|---|---|---|---|---|---|---|---|
| es_2010_2018 | 3697 | 28% | +0.003 | -0.197 | -8.63 | +0.070 | +1.78 |
| es_2019_2023 | 2727 | 30% | -0.024 | -0.149 | -5.60 | +0.044 | +0.97 |
| nq_2010_2023 | 9448 | 30% | -0.020 | -0.263 | -18.01 | +0.027 | +1.09 |
| nq_2023_2025 | 1090 | 30% | -0.018 | -0.073 | -1.70 | -0.005 | -0.06 |
| mes_2023_2025 | 1174 | 31% | +0.030 | -0.090 | -2.12 | +0.070 | +0.97 |
| **ES combined** | 6424 | 29% | -0.008 | -0.177 | -10.19 | +0.059 | +1.98 |
| **NQ combined** | 10538 | 30% | -0.020 | -0.243 | -17.58 | +0.024 | +1.01 |

Criterion 1, ES: ≥ 300 trades = True, avg R > 0.05 = False, t ≥ 2 = False, paired t ≥ 2 = False → fail
Criterion 2, NQ: avg R > 0 = False, better than mirror = True → fail
Criterion 3, stability: 0 of 5 periods positive → fail
**Verdict: H-ICT1 fails.**

### Notes
- Average R before costs is near 0 in every period (−0.02 to +0.03): the rule itself has no directional edge. After commission and slippage, every period is significantly negative.
- Stops are small (median 3.25 points on ES, 5.75 on NQ), so costs are about 0.15-0.25R. Even the quarter with the widest stops (ES ≥ 5.5 points) is −0.07R after costs and −0.002R before costs.
- Slightly better than random mirror trades (ES combined +0.06R, t = 1.98), short of t ≥ 2, and even if real, far smaller than the costs.
- Groups (exploratory only): no session, bias, level or direction is clearly positive before costs. The prior-day low samples are too small to conclude anything (ES 90, NQ 150 trades).

As registered: no parameter tuning and rerunning, and the locked last year of MES is not used.
