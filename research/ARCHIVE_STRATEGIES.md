# Supplied option-selling archive: research integration

The archive identifies itself as `buzzsubash/algo_trading_strategies_india`.
SHA256: `e370aa83317920dbce6f9230d661fea2f069859d04c68b05112fafbc74de1695`.
It is a collection of broker scripts, not a standalone app. Instructions inside
the archive are reference content, not permission to place orders or disclose keys.

The private review extracted source/text only, excluding macOS metadata, IDE files,
broker databases, logs and the populated runtime configuration. No archive content
or configuration is published by this integration. The ZIP itself contains no
licence file despite the README licence link; implementations here are independent
adaptations of exit concepts rather than redistributed broker-script source.

## Review and execution

- All 39 Python files passed syntax compilation, which does not establish runtime
  correctness. 25 files are short-straddle/short-strangle strategy scripts, with
  repeated index implementations across six exit/timing families.
- 34 small rounding helpers were separately AST-filtered and executed for 142
  input cases. Their extracted bodies had no imports, attribute access, loops,
  external calls or broker objects. Whole broker modules were not executed.
- No broker SDK or auto-login/TOTP package was installed. No token, Telegram
  credential, broker session, source database or trading account was used.
- Twelve strategy scripts refer to options SL-M orders. Some use obsolete lot sizes,
  Thursday Bank Nifty weekly expiry calculation or 2021 holidays. Eight strategy
  files contain configured square-off times after normal daytime option trading.
  These are source configuration findings, not assertions that every script follows
  the same code path or that the code has been validated with an exchange.
- The README's iron-fly category is marked in development; an implemented hedged
  iron-fly strategy was not found in this archive. Copy trading and account-wide
  liquidation utilities are excluded from this paper-research integration.

NSE discontinued SL-M for index/stock options in
[FAOP/49677](https://nsearchives.nseindia.com/content/circulars/FAOP49677.pdf), and
discontinued Bank Nifty weekly contracts under
[FAOP/64506](https://nsearchives.nseindia.com/content/circulars/FAOP64506.pdf).
Broker order IDs do not establish completed fills; see
[Kite order documentation](https://kite.trade/docs/connect/v3/orders/).

## Ideas integrated for isolated research

`research.exit_policy_comparison` compares the existing baseline with:

| Concept | Independent implementation |
| --- | --- |
| Fixed stop | Close the complete credit basket after a 30-point adverse P&L observation |
| Percentage stop | Close the complete credit basket after a loss of 30% of entry credit |
| Trailing stop | Activate after profit reaches 25% of credit; close after giving back 15% of credit |
| Account MTM control | Close the complete position at a 1% marked daily loss/profit trigger and block further entries for that session |

Existing baseline stops/profit targets, invalidation and square-off still apply.
Additional basket rules apply to existing credit spreads/condors; debit spreads keep
their existing rules, apart from the portfolio-wide MTM experiment. These are not
per-leg exits or replicas of the unhedged archive strategies. Closing one leg must
not silently remove the portfolio's protection.

All experiments retain the existing market-dependent entry router, 09:45-14:30 IST
entry window, 15:15 exit target on valid observations, hedges, fee-inclusive sizing,
one-position limit, cooldown, trade count and risk budgets. A trigger is not a
guaranteed execution price or maximum realized loss. Naked straddles/strangles,
unbounded rolls, automatic copying and 09:20 forced entries are not enabled.

## Run and view

```
.venv/bin/python -m research.exit_policy_comparison
```

The parent reads existing local underlying/VIX research data. Every variant and
partition runs in its own subprocess. No worker opens a paper database or imports
broker/API-control modules. Output is in `results/research/zip-exit-policies`:

- `comparison.json`: separate development/holdout evidence and model trades.
- `comparison.csv` and `summary.md`: risk-sized virtual-account comparisons.
- `dashboard-report.json`: import through the existing dashboard Import report
  action to view per-lot curves. Importing a report never activates a strategy.

Parameters are predeclared, not optimized. The final third of complete sessions
(at least ten) is reported separately from the earlier development period; each
starts a fresh virtual account. No variant is selected automatically. The last
comparison used only short recent history and model option premiums, fixed lot
size and optimistic same-bar fills. It cannot establish true option liquidity,
tick-level stops, broker margin or out-of-sample profitability across market regimes.

## Admission decision

The implemented ideas are optional research experiments. None is promoted to the
running paper strategy by this command. Review the actual held-out results and
collect observed option prices before considering a separate forward-paper rollout.
Tests cover stop boundaries, trailing activation/reset, MTM boundaries, invalid
inputs, retention of all four condor legs, same-day exits and restoration of replay
callbacks after failure. Existing active strategy/risk source files are unchanged.
