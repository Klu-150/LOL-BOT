# How to build trading strategies (and how the adaptive engine does it)

Paper/research only. Nothing here places orders. A backtest is evidence, not a promise.

## 1. Why the old intraday bot bought high and sold low

Intraday backtest, 18 Aug–16 Nov 2026: 21 trades, 30% winners, profit factor 0.15,
−₹7,974 per lot. Nifty rose ~13% in the same window.

- **The structure could not win intraday.** It sold weekly credit spreads/condors and
  closed them at 15:15 the same day. A credit spread earns from time decay over days;
  in five hours it earns almost nothing, while 4 legs × 2 sides of slippage and
  charges are paid in full. 19 of 21 trades ended at the 15:15 square-off.
- **It entered at 09:45 after the opening move** (11 of 21 entries at 09:45, one at 09:50). Entering on a
  breakout of the first bars means buying after the move — i.e. buying high.
- **"Rich volatility" was mis-measured.** The VIX/realised-vol ratio compares a 30-day
  implied vol with a few hours of intraday realised vol, so nearly every day looked "rich".
- **A 15-minute regime flips many times a day.** It re-labels noise as a trend change.

## 2. The five questions every strategy must answer

1. **Edge — why should this make money?** Name the behaviour you exploit: trends persist
   (momentum), short-term overreactions revert (mean reversion), fear is overpriced
   (volatility premium). "The indicator crossed" is not an edge.
2. **Regime — when does the edge exist?** Momentum works in trends and fails in ranges;
   mean reversion is the opposite. Write down when the strategy must be switched off.
3. **Entry — exactly when, at what price?** Decide on a completed bar, fill at the next
   open. Prefer entering on a pullback inside a trend or a confirmed breakout, never
   after an extended run (RSI2 > 90 in an uptrend is late).
4. **Exit — where am I wrong, and where do I take profit?** Set the stop before entry
   (e.g. 2.5 × ATR). Let winners run with a trailing stop or a rule (close below EMA50).
5. **Size — how much can I lose?** Risk a fixed 1–2% of equity per trade to the stop.
   Size = risk ₹ ÷ stop distance. This one rule is what keeps traders in business.

## 3. How to test an idea without fooling yourself

- **No look-ahead.** Only use data up to the decision bar. `tests/test_pro_engine.py`
  checks that appending future data never changes past features or decisions.
- **Include costs, then double them.** If the edge dies at 2× costs, it isn't an edge.
- **Fix parameters from textbooks before looking at results.** Every tweak you make after
  seeing a backtest makes it look better and trade worse ("overfitting").
- **Split time.** Develop on older data, then check a period you did not look at.
  An edge should hold in both halves, not only overall.
- **Need enough trades.** Fewer than ~30 trades is anecdote.
- **Compare to buy-and-hold.** On Nifty that is a very high bar (≈11%/yr since 2016).

## 4. What the engine found on 2016–2026 Nifty daily data

Each library strategy was run alone (index points, 1.5 pts cost per side):

| Strategy | Idea | Result |
|---|---|---|
| trend_pullback | uptrend + RSI2<10, buy the dip | long side works, best in 2023–26 |
| channel_breakout | 55-day breakout, trail 3 ATR | long side works in both eras |
| trend_rider | ADX≥25 ride to EMA50 | mixed; kill switch watches it |
| range_reversion | fade Bollinger bands when ADX<20 | flips sign between eras → rejected |
| panic_reversal | buy VIX spikes | lost in both eras → rejected |
| any short side | — | mostly lost; Nifty drifts upward → rejected |

The adaptive engine (regime playbook + walk-forward kill switch):

| 2016–2026 | Return/yr | Worst drawdown |
|---|---|---|
| Buy & hold Nifty | 11.4% | −38.4% |
| Adaptive, fully invested on signals, cash at 6% otherwise | 5.8% | −9.9% |
| 50% buy & hold + 50% adaptive | 8.8% | −21.3% |

Honest conclusion: these technical rules **do not beat buy-and-hold on return**. They
cut the worst loss by roughly three-quarters and sit in cash ~70% of the time. Holding
the multi-day signals as option debit spreads lost money in the model (time decay +
four-leg slippage); the signals fit an index ETF or futures, not short-dated options.

## 5. How the engine adapts each day

`python -m pro.live` (after 15:10 IST, add `--include-today`):

1. Loads 2012→today daily Nifty + India VIX history and appends the latest public bars.
2. Classifies the regime: `uptrend`, `transition`, `range`, `downtrend`, `stress` (VIX≥25
   or VIX rank≥85), plus a scheduled-event veto (edit `events.csv` — budget, RBI, results).
3. Looks up the playbook for that regime (`pro/engine.py: PLAYBOOK`).
4. **Learns from history:** scores each allowed strategy on its trades in the same regime
   that *closed* in the last ~3 years; disables one whose recent record is clearly broken;
   ranks the rest.
5. Prints BUY / HOLD (with trailing stop) / SELL / STAND_ASIDE to
   `paper/pro_engine_plan.json`, and appends every decision to `paper/pro_engine_decisions.jsonl`.

`python -m pro.backtest` regenerates `results/pro/` (summary, trades, decisions).

About "news": the engine uses India VIX (the market's fear gauge) and the event calendar.
It does not read headlines; free headline feeds are unreliable, and headline sentiment
has weak, hard-to-test evidence. Add it only as a veto (stand aside), never as a trigger.

## 6. Template prompt for a new strategy

Fill this in and send it; I will add it to `pro/strategies.py`, run it alone and inside
the adaptive engine, and report whether it survives the tests above.

```
Name:
Edge (why it should work):
Market/regime where it works:            (uptrend / range / downtrend / high VIX)
Where it must be switched off:
Entry rule (on completed daily or 15m bar):
Long, short, or both:
Stop rule:                               (e.g. 2.5 x ATR below entry)
Exit / take-profit rule:
Maximum holding time:
Instrument:                              (index ETF / futures / option spread)
Risk per trade:                          (1-2% of equity)
```

Good ideas to try next: a 15-minute opening-range breakout used only on
`uptrend` days, a volatility-premium iron condor *held several days* when VIX rank>60
and regime is `range`, and a sector-rotation version across Bank Nifty/IT indices.
