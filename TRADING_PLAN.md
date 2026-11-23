# Last of Our League: automatic intraday paper plan

Version 2 — 15 November 2026. Market: Nifty options. Execution mode: virtual money.

## 1. Market and timeframe

Use real, observed Nifty/VIX **5-minute underlying bars** from the public research
feed, or a CSV with `timestamp,Open,High,Low,Close,VIX`. Timestamps are timezone-aware
**bar-end** times in Asia/Kolkata. Only completed bars are processed.

Direction uses only completed 15-minute candles: each must contain all three
5-minute bars. EMA20, EMA50 and ADX(14) come from those completed candles, including
their completed close. A partial 5-minute move never substitutes for the higher
close. Five-minute EMA20/EMA50 alignment provides the entry trigger.

The option contract expiry is a **nominal** weekly date. The bot closes intraday
and does not hold to expiry. An authoritative holiday/contract calendar and real
option quotes are still needed for execution validation.

## 2. Condition-to-strategy rules

A rising condition is completed 15m close > EMA20 > EMA50 with ADX >= 20. A falling
condition is close < EMA20 < EMA50 with ADX >= 20. ADX < 20 defines the range case;
other combinations are unclear.

- **Rich-volatility proxy:** IV rank >= 30 and VIX / trailing realised vol >= 1.10.
- **Cheap-volatility proxy:** IV rank < 30 and that ratio <= 1.00.
- Other combinations are mixed and do not trigger a directional entry.

| Condition | Candidate |
|---|---|
| Rising + cheap | Bull call debit spread |
| Rising + rich | Bull put credit spread |
| Falling + cheap | Bear put debit spread |
| Falling + rich | Bear call credit spread |
| Range + rich | Iron condor |
| Range + cheap/mixed, unclear direction or mixed directional volatility | No trade |
| Listed same-day event, VIX >= 30, insufficient indicators or stale data | No trade |

The basic outlooks are documented by the Options Industry Council's
[bull call spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread)
and [iron condor](https://www.optionseducation.org/strategies/all-strategies/short-condor)
references. Their existence does not validate this timing rule or establish a
Nifty trading edge.

For a bullish entry require current 5m close > its EMA20 >= its EMA50; for bearish
entries require close < EMA20 <= EMA50. Range entries use the range/volatility
filters. A completed higher-timeframe observation older than 20 minutes cannot
support a new entry.

## 3. Structures and fills

All shorts have same-expiry hedges **100 points** away. Verticals sell about
0.25 absolute model delta; condors use about 0.16 on each side. Debit spreads buy
the rounded ATM option and sell 100 points further in the intended direction.
The configured research lot size is 65 units.

Credit after entry slippage must be positive, less than wing width, and at least
15% of the width. Debit must be positive and below width, and estimated maximum
reward after cost reserve / full reserved risk must be at least 0.5.

The pricing model uses fractional time to expiry, synthetic skew, and India VIX.
Buy fills add configured slippage; sell fills subtract it. Brokerage, taxes and
charges are modelled on entry and exit. When observed intraday VIX is absent, a
completed prior-day close no older than four calendar days can be used as a
**labelled proxy**. Current/future daily closes are never used for historical bars.
IV rank uses only prior-session daily history; realised volatility excludes the
single-bar overnight gap and is annualised from trailing 5m returns.

These are theoretical option fills against real underlying observations. They
are not real option quotes or broker executions. Same-bar execution is optimistic.

## 4. Account and exits

The selected virtual account begins at **₹5,00,000**. Entry fees reduce realised
equity immediately. Closing adds gross P&L less exit fees; no fee is deducted twice.
Receiving short premium is not counted as earned profit.

- Risk at most **2% of current realised equity** per entry, using full spread
  payoff loss plus estimated costs and a ₹500 per-lot buffer. Round lots down.
- One open position at a time; maximum five lots and **three entries per session**.
- Reserve from the remaining **3% daily loss budget** as well as the per-trade
  budget. Execution losses/costs can exceed estimates.
- New entries only from **09:45 to 14:30 IST**. A 15-minute cooldown follows an exit.
- Credit TP: 50% of entry credit. Credit SL: loss of twice entry credit.
- Debit TP: 50% of maximum payoff profit. Debit SL: loss of 50% of debit.
- A confirmed opposite 15m trend invalidates a directional position. A condor
  exits on a directional 15m breakout with ADX >= 25. A VIX shock also invalidates.
- Square-off target is **15:15 IST**, at the next available completed-bar model
  observation. This is an earlier bot risk cutoff, not a claim about exchange
  closing time. It takes precedence over other exits at/after that timestamp.
- Never close and reopen on the same bar. A 15% realised account drawdown halts
  new entries persistently.

Stops are programmatic model decisions checked on 5-minute bars, not broker stop
orders or guaranteed fills. If the feed misses the square-off observation, mark
the position unresolved, block the next session, and restore the missing bars;
do not manufacture a fill or substitute a later session's spot.

## 5. Automatic operation and review

```bash
.venv/bin/python dashboard.py --auto-paper
```

The local application checks its source every 60 seconds in the configured
weekday session window and processes each completed bar once. **Pause new entries**
leaves open-position management active. Shutting down the application or computer
stops all processing, including exits; keep it running during sessions. No OS
service is installed. A public data source can delay, rate-limit or fail; stale
bars cannot open a new position.

The durable forward account is `paper/intraday_500k.sqlite3`, with observed-bar
events, actual model positions, fees, marks and realised outcomes. It begins
forward from initialisation and does **not** replay old entries. Earlier weekly
paper accounts remain separate and unchanged.

Run `intraday_backtest.py` to test recent observed bars with costs, no costs and
2× slippage. Read `results/intraday/summary.md`. Exclude incomplete sessions and
assert all completed-session trades exit on their entry date. Backtests are
historical model results; they never become forward paper fills.

The initial available intraday history is short. Keep losses visible, do not tune
thresholds until this sample becomes profitable, and do not call a small sample
validated. Real option quotes, contract calendars, latency, liquidity and margin
checks remain outside this research system. The hosted website is a static
private snapshot; it cannot run the local automatic worker.
