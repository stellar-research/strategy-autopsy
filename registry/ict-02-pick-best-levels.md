# ICT-02: upper bound if every level pick is right (H-ICT2)

> The original registration was committed to the author's private repository before the backtest; the commit time is the evidence. This is a faithful translation with personal details removed.

## Registration (2026-10-15, before any result was seen)

Origin: after H-ICT1 failed, someone proposed "the system offers up to 3 entries and 3 exits, and a person picks". Script `ict/research_choice.py`; `ictlib.py` parameters unchanged.

- Each setup: entry candidates = near edge of the FVG / CE midpoint / far edge of the FVG; exit candidates = the nearest 3 liquidity levels beyond the entry (within 6R, filled with 1R/2R/3R if fewer); stop unchanged.
- "Pick perfectly" = the best R after costs among the 9 combinations and "no trade" (a theoretical upper bound that cannot be achieved).
- Control = the same setup and the same stop, using the level geometry of another random setup.

**What is tested**: whether ICT levels themselves carry information, i.e. whether ICT "pick perfectly" has a higher average R than control "pick perfectly".
**Pass criteria**: ES 2010-2023 combined and NQ 2010-2025 combined both with paired difference > 0 and t ≥ 2; paired difference > 0 in at least 4 of the 5 periods.
The absolute size of "pick perfectly" is for reference only (any levels picked after the fact make money) and is not a pass criterion. MES after 2025-09-01 stays locked.

Run: `python3 ict/research_choice.py data.csv --symbol ES --name es_2010_2018 --before 2025-09-01`

## Verdict

Date: 2026-10-15. Each setup has 3 entries × 3 exits; "pick perfectly" = the best of the 9 combinations or no trade. Control = the same setup and stop with the level geometry of another random setup.

| Period | Setups | ICT perfect | Random perfect | Difference | t |
|---|---|---|---|---|---|
| ES 2010-2018 | 4826 | +0.423 | +0.415 | +0.009 | +0.67 |
| ES 2019-2023 | 3771 | +0.433 | +0.435 | −0.001 | −0.09 |
| NQ 2010-2023 | 13060 | +0.393 | +0.393 | +0.001 | +0.11 |
| NQ 2023-2025 | 1550 | +0.460 | +0.470 | −0.009 | −0.31 |
| MES 2023-2025 | 1647 | +0.461 | +0.446 | +0.015 | +0.59 |
| **ES combined** | 8597 | +0.428 | | +0.004 | +0.41 |
| **NQ combined** | 14610 | +0.400 | | −0.000 | −0.03 |

Criteria: ES and NQ combined paired difference > 0 with t ≥ 2 → neither holds; paired difference > 0 in 3 of 5 periods (≥ 4 required) → fails.
**Verdict: H-ICT2 fails.** The after-the-fact upper bound of ICT entry and exit levels equals that of random levels; the levels themselves carry no measurable information.
"Pick perfectly" is about +300R a year (ES) / +390R (NQ), but random levels do just as well, so this upper bound only reflects how much prices move, not ICT.
