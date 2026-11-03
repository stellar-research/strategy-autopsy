# Brooks-03: first pullback in a trend from the open (hypothesis T-2, in-sample)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules
- Code: `--strategy open_trend --target {2R|eod} --max-trades 1`
- If the open starts with ≥ 3 consecutive same-direction bars covering ≥ 15% of the average daily range, enter with the trend at the first pullback; give up if the pullback returns to the open; at most 1 trade per day
- Target: 2R, or close at session end

## Data and costs
Same as Brooks-01.

## Results
| Variant | Trades | Win rate | Profit factor | Expectancy (USD) |
|---|---|---|---|---|
| Trend from the open, 2R | 65 | 46.2% | 1.14 | +3.11 |
| Trend from the open, close at end | 65 | 27.7% | 0.93 | −1.99 |

The random baseline for 2R is about 33% and the measured win rate was 46.2%, p ≈ 0.02 on its own. But about 9 variants had been tested by then, so after multiple testing it only counts as "worth validating". **No parameter was changed**; it moved to Brooks-04 for validation on unused data.
