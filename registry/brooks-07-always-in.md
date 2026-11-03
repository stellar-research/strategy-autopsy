# Brooks-07: always-in reversal (hypothesis AI-1)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules (fixed before running)
- Two consecutive strong same-direction trend bars (body ≥ average body, close within the outer third), the second closing beyond the extreme of the 10 bars before the spike
- The follow-through bar does not close the other way; no tight trading range before the spike
- Enter at market on the next open; stop one tick beyond the bottom of the spike; target 1R; risk ≤ half the average daily range

Code: `--strategy ai --target 1R`

## Data and costs
- NQ 1-minute 2010-06 to 2023-08 (never used), with MNQ costs; last year of MES locked
- Commission 0.85 USD per contract per side; 1 tick of slippage on stop and market orders

## Pass criteria (fixed before running)
≥ 300 trades, win rate ≥ 55%, profit factor > 1.1.

## Engine honesty check
On 500 days of pure random walk: win rate 47.1% (below the 51.5% random baseline; the gap is costs), losing overall.

## Results
| Metric | Result |
|---|---|
| Trades | 1,556 |
| Win rate | 51.8% (random baseline 50.9%, z ≈ 0.7, not significant) |
| Profit factor | 1.07 |
| Total P&L (MNQ, after costs) | +3,033 USD; max drawdown −1,491 |
| 1 extra tick of slippage per side | profit factor 1.03 |
| 2 extra ticks of slippage per side | profit factor 1.00 |
| By year | lost money 5 years in a row 2010-2014; profitable in most years after 2015 |

**Verdict: fail.** The only one of the 7 rounds that was positive overall, but its win rate is not significantly different from the random baseline and the profit is very sensitive to slippage. The yearly pattern is an after-the-fact observation and was not used to change the rules.
