# Registry entry: <experiment name>

**English** | [日本語](TEMPLATE.ja.md)

> Fill this in and commit it **before you look at any backtest result.** Do not edit it afterwards. To change the rules, open a new entry and explain the link under "Relation to earlier experiments".

## 1. Basics

- Experiment ID:
- Registration date:
- Hypothesis in one sentence: <e.g. after two consecutive strong trend bars, a with-trend entry wins more often than the random baseline>
- Source: <book / course / video + chapter or timestamp>

## 2. Rules (must be codeable; no "it depends")

- Entry condition:
- Entry order: <market at next open / stop order beyond the bar / limit>
- Stop:
- Target:
- Filters:
- Time limits: <session, flat before the close, etc.>
- Maximum open positions:

## 3. Data

- Instrument and timeframe:
- Period:
- **Never used before**: <yes / no. If no, explain how it was used>
- Locked out-of-sample period:

## 4. Costs

- Commission (per contract per side):
- Slippage (ticks):
- Fill assumptions:

## 5. Pass criteria (fixed in advance)

- Minimum number of trades: <e.g. ≥ 300>
- Win rate: <e.g. significantly above the random baseline, one-sided p < 0.05>
- Profit factor: <e.g. > 1.1, and still > 1.0 with 1 extra tick of slippage per side>
- Other: <e.g. positive in both halves of the data>

## 6. Relation to earlier experiments

- Was this rule inspired by earlier results?
- If so, why is this not tuning on the same data?

## 7. Results (fill in after the backtest; append only, do not edit the sections above)

- Run date:
- Command:
- Summary:
- Pass / fail:
