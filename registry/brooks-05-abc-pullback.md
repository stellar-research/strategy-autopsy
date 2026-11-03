# Brooks-05: structured ABC pullback (hypothesis T-3)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules
- Code: `--strategy abc --target 2R`
- A two-leg pullback in a trend (A leg, B leg bounce, C leg), with the B leg at least 30% of the A leg (as a proxy for a "minor trendline break"), plus several filters

## Data and costs
- MES in-sample 2023-09 to 2025-08
- ES 2010-06 to 2018-12 (never used), with MES costs

## Results
| Data | Trades | Win rate | Profit factor | Total P&L (USD) |
|---|---|---|---|---|
| MES in-sample | 12 | 50.0% | 1.55 | +89.6 |
| ES 2010-2018 | 49 | 24.5% | 0.38 | −370.8 |

**Verdict: fail.** Only 49 trades in 8.5 years, with a win rate below the 2R random level of about 33%. The positive 12 in-sample trades were luck.

The dilemma we saw: loose conditions give many signals with a random win rate; conditions tight enough to match the book give too few signals to validate, and still no edge.
