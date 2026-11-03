# ICT-04: an ICT trading checklist from an online article

> This round had no formal registration file. The rules came from an ICT checklist published in an online article, and the definitions were fixed from the article's wording before backtesting. Treat the results as indicative only.

## Rules
- **Checklist as written**: enter only when every condition in the article holds, including "the entry is in the discount zone (long) / premium zone (short)"
- **Practical version**: fixed 2R target, discount-zone filter removed
- **Without the direction filter**: the practical version with the higher-timeframe direction filter also removed

## Data
Index CFD 5-minute data (S&P 500 and Nasdaq 100, matching MES and MNQ), 2020-09 to 2023-09. **Not CME futures data**; this was the only free data available.

## Results
| Version | Trades | Win rate | Avg R per trade |
|---|---|---|---|
| Checklist as written | 0 | — | — |
| Practical version (2R) | 82 | 24% | −0.18 |
| Without the direction filter | 360 | — | −0.10 (positive only in 2022) |

A 2R target needs a win rate of about 33% to break even. Adjusting FVG size, displacement multiple and target multiple left results near zero or negative; no parameter set was consistently positive.

**Verdict: no reliable edge found.**

## Limitations
- Used CFD 5-minute data, not CME futures; no news or FOMC filter; no precise 1-minute entries
- This is one objective definition of the checklist; another definition could give different results
