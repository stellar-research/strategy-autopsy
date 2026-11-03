# Brooks-06: fade failed breakouts on trading-range days (hypothesis F-1)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules (fixed before running, from REVERSALS ch. 9 and 18)
Short side (long is symmetric):
1. Context: no clear trend today, |trend strength score| < 3; not in a tight trading range
2. Range top: the highest price of bars 2 to 21 back
3. Breakout bar (previous bar): a bull trend bar closing above the range top; "not too strong": its length ≤ 1.5x the average bar length, and the bar before it is not a bull trend bar
4. Failure signal bar (current bar): a bear trend bar, or an inside bar that closes down
5. Entry: sell stop one tick below the signal bar low, active for one bar only; stop one tick above the higher of the breakout and signal bars
6. Target: middle of the range; skip if it is less than 1x risk away

Code: `--strategy fade`

## Data
MES in-sample, ES 2010-06 to 2018-12 and ES 2019-01 to 2023-08 reported separately; last year of MES locked.

## Pass criteria (fixed before running)
Both ES periods with profit factor > 1.1 and ≥ 150 trades, and MES in-sample profit factor > 1.0.

## Results
| Data | Trades | Win rate | Random baseline | Profit factor | Total P&L (USD) |
|---|---|---|---|---|---|
| MES in-sample | 52 | 34.6% | — | 1.18 | +211.6 |
| ES 2010-2018 | 171 | 37.4% | 41.4% | 0.64 | −713.2 |
| ES 2019-2023 | 115 | 35.7% | 37.7% | 0.82 | −508.0 |

**Verdict: fail.** On both ES periods the actual win rate was below the random baseline.
