# Brooks-01: plain pullback system (H2 / L2 second entry)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules
- Code: `brooks/backtest.py --strategy pullback --target {1R|2R|extreme}`; control group: first version `--strategy v1`
- Second entry in a with-trend pullback (H2 long / L2 short), stop order one tick beyond the signal bar, stop at the other end of the signal bar
- Three targets: 1x risk, 2x risk, the prior swing extreme

## Data and costs
- MES 1-minute, 2023-09-01 to 2025-08-29 (in-sample); data after 2025-09-01 locked
- Commission 0.85 USD per contract per side; 1 tick of slippage on stop and market orders

## Pass criteria
In-sample exploration, no pass criteria. The goal was to see whether the entry signal carries directional information.

## Results
| Variant | Trades | Win rate | Random baseline | Profit factor | Expectancy (USD) |
|---|---|---|---|---|---|
| First version (control) | 1,125 | 37.6% | — | 0.78 | −5.07 |
| H2 pullback, 1R target | 624 | 47.3% | ~50% | 0.74 | −4.47 |
| H2 pullback, 2R target | 597 | 32.5% | ~33% | 0.80 | −4.41 |
| H2 pullback, prior extreme | 488 | 27.5% | lower | 0.73 | −6.23 |

**Verdict: no edge.** With all three targets the win rate sits at the random baseline. Changing the target cannot fix it; the problem is the entry signal itself.
