# Data

This repository **does not include any market data.** Futures data licences usually do not allow redistribution.

The backtests need a 1-minute OHLCV CSV with these columns:

```
timestamp,open,high,low,close,volume
```

`timestamp` can be ISO 8601 with a time zone (for example `2024-01-02T09:30:00-05:00`) or UTC nanosecond integers (`ts_event`, as exported by Databento).

You can get data from a vendor (such as Databento, or your broker's historical data API) or export it from TradingView. Please follow each source's data licence and do not commit downloaded data to a public repository.

Everything in this folder except this file is excluded by `.gitignore`.
