# Brooks-02: refined pullback (hypothesis T-1)

> This is a public transcription. The original registration and results are in the author's private lab notes; the spec was fixed before running, and only results were appended afterwards.

## Rules
- Code: `--strategy pullback2 --target {1R|2R}`
- Brooks-01 plus three conditions (from TRENDS ch. 10): trend strength score ≥ 3; in the pullback, at most 3 consecutive opposite trend bars and at most 1 large opposite trend bar; the H2 entry price must not be better than the H1 entry

## Data and costs
Same as Brooks-01.

## Results
| Variant | Trades | Win rate | Profit factor | Expectancy (USD) |
|---|---|---|---|---|
| H2 pullback 2R (control) | 597 | 32.5% | 0.80 | −4.41 |
| Refined pullback 1R | 44 | 45.5% | 0.59 | −7.92 |
| Refined pullback 2R | 44 | 27.3% | 0.61 | −9.51 |

**Verdict: fail.** Tighter conditions left only 44 trades, the win rate still sat at random, and results got worse.
