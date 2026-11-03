# Method

**English** | [日本語](method.ja.md)

This project is not trying to find a profitable strategy. It answers a narrower question: **does a strategy written as fixed rules have an edge beyond random after costs?**

To make the answer credible, every experiment follows the five rules below.

## 1. Register first, then backtest

Rules, parameters, data ranges and pass criteria are written into `registry/` and committed before any result is seen. The commit time is the evidence.

Rules are never changed after testing. A change means a new registry entry and a new experiment.

## 2. Test each rule set once

Tuning parameters repeatedly on the same data will eventually produce a set that looks good, but that is mostly luck. So each registry entry is run only once.

## 3. Lock out-of-sample data

The last stretch of data is untouched from the start (for example the last year of MES) and reserved for a final test. New experiments prefer instruments or periods that have never been used.

## 4. Compare with a random baseline

For an entry with no directional information, the probability of hitting the target first is about:

```
random win rate ≈ stop distance ÷ (stop distance + target distance)
```

So:

| Reward : risk | Random win rate | Expectancy (before costs) |
|---|---|---|
| 1 : 1 | about 50% | about 0 |
| 1 : 1.5 | about 40% | about 0 |
| 1 : 2 | about 33% | about 0 |

Moving stops and targets only trades win rate against reward:risk. What has to be tested is **whether the actual win rate is significantly above the random win rate computed from each trade's actual stop and target.** We measure significance with a binomial z score.

The engine itself must also pass an **honesty check**: on pure random-walk data, the win rate should be slightly below the random baseline (the gap is costs) and the strategy should lose money overall. If it makes money on random data, the backtest has a bug.

## 5. Count costs honestly

- Commission at real broker rates.
- 1 tick of slippage per side by default, plus sensitivity tests with 1 and 2 extra ticks.
- Market orders fill at the next bar's open, not at the signal bar's close.

## What this method cannot show

- Only whether *this particular objective definition* of a rule has an edge; another definition could differ.
- It cannot test discretionary judgement. Testing whether discretionary trading has an edge needs other methods, such as blind tests.
- No edge in the past does not mean no edge in the future, and an edge in the past does not mean it will continue.
