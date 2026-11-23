# Strategy Workshop

Open the dashboard's **Develop strategies** item, the mobile **Strategies** tab,
or https://nifty-research-terminal.nearbydrape.chatgpt.site/#strategies.

Create a strategy from Adaptive spreads, Directional spreads or Range premium.
Choose a defined-risk option spread or No trade for each market/volatility pair.
Adjust ADX, volatility thresholds, an optional 5-minute RSI band, spread width,
entry times, risk and maximum lots. Save a named draft and run a historical test.

The workshop supports create, edit, copy, remove, JSON import/export, up to 50
saved definitions per browser, recent experiment comparisons, and report export.
The strategy library stays in the current browser's local storage. It does not
synchronize between the phone, laptop or a friend's device. Export a strategy JSON
and import it on another device to share it. Clearing browser storage deletes that
browser's library. A completed test stores a small summary with a saved definition;
full experiment data and imported comparison reports stay in the current session.

Backtests run in an isolated browser worker. They need no cloud key or Azure
change and cannot call the trading API. Each experiment has a separate ₹5,00,000
research account. Its baseline uses the same dates, data and pricing assumptions.
Account P&L uses the chosen lot sizing; the main comparison report uses per-lot
P&L consistently. No trades are appended to the forward paper account.

Only defined-risk vertical spreads and iron condors are offered. The research
bounds retain at most 2% per-entry risk, five lots, three entries/day, one open
position, a 3% daily budget, cooldown and drawdown controls. Completed 15-minute
bias and 5-minute triggers are used; event/shock/missing-data vetoes remain active.
Exits retain the existing model's take-profit, stop, invalidation and same-day
15:15 target. A missing exit observation is an error, not an invented fill.

The dataset contains observed underlying bars and causally calculated features;
coverage dates are shown after loading. The published dataset currently covers
18 August–16 November 2026, including indicator warm-up history. VIX can be an
explicitly labelled prior-day proxy. Historical costs, fixed lot size and modelled
option prices/fills match the configured research model. Same-bar fills are
optimistic; no option-chain liquidity or broker margin is simulated. A short
historical backtest is not proof of a profitable strategy.

**Saving, importing, testing or comparing a draft never activates it in the
unattended cloud bot.** Active paper trading continues with its exact pinned
policy. Moving a research draft into forward execution requires a separate,
deliberate deployment and account/policy validation.

## Definition format and reference testing

Definitions use schema version 1 with `name`, `description`, `parameters` and
routing `rules`. Import accepts a single definition or an array; executable code,
extra fields, duplicate condition pairs, unsupported structures, invalid entry
windows and excessive risk are rejected. Browser imports are limited to 128 KB.
Templates in `examples/strategy-definitions` can be imported through the UI.

`strategy_workshop.py --definition path/to/strategy.json --output result.json`
runs an isolated Python reference backtest in a child process. It never alters
live module settings or opens a paper database. `--dataset
 dashboard/dist/strategy-data.json` regenerates the static research dataset from
local observed CSVs without downloading new data or modifying any account.

`tests/test_strategy_workshop.py` checks invalid definitions and compares browser
results with the Python reference for adaptive, range-only and changed-parameter
strategies. `dashboard/strategy-checks.mjs` checks persistent saving, atomic
imports, escaping, validation, same-day exits, bounds and account isolation.
Browser QA verified saving, reloading, worker simulation and comparison; a
390-pixel viewport has no document overflow. No real phone or broker was used.
