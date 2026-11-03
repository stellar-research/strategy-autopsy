# Brooks-04: independent validation of trend from the open, 2R

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules
Exactly the same as "trend from the open, 2R" in Brooks-03, no parameter changed.

## Data (all never used before)
- ES 1-minute 2019-01 to 2023-08, with MES costs
- NQ 1-minute 2023-09 to 2025-08, with MNQ costs
- MES after 2025-09-01 still locked

## Pass criteria (fixed before running)
ES: profit factor > 1.1 and ≥ 100 trades; NQ: profit factor > 1. Only if both pass would the locked data be used.

## Results
| Data | Trades | Win rate | Profit factor | Total P&L (USD) |
|---|---|---|---|---|
| MES in-sample (original finding) | 65 | 46.2% | 1.14 | +202.0 |
| ES 2019-2023 | 190 | 36.8% | 0.91 | −345.5 |
| NQ 2023-2025 | 80 | 31.2% | 0.82 | −621.0 |

**Verdict: fail.** On new data the win rate fell back to around random (about 33% for 2R). The 46% in-sample was small-sample luck.
