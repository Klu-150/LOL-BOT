# Last of Our League

**New: LOL Pro terminal** — regime-based positional options paper trading with live news,
an AI assistant and alerts. Double-click **Launch LOL Pro.command** or see [LOL_PRO.md](LOL_PRO.md).

**iPhone:** Open the [app setup page](https://nifty-research-terminal.nearbydrape.chatgpt.site/#mobile)
in Safari and add it to your Home Screen. The app displays saved records until
an always-on engine is connected. See [CLOUD_SETUP.md](CLOUD_SETUP.md) for the
cloud connection and phone installation instructions.

An automatic **intraday options paper-trading terminal** for Nifty. It analyses
completed market bars, chooses a hedged strategy for the current condition,
records hypothetical fills, and manages same-day exits. No broker is connected
and no real orders are submitted.

## Shared cloud use and production checks

Both laptops should open the same public dashboard and connect using their own
credentials under **Connect devices**. One cloud engine manages the separate
original and experimental virtual accounts; the viewer cannot start or pause it. Closing either laptop does not stop
the server. Do not start a duplicate local engine for the migrated account.

Release 1.3.2 adds read-only runtime hardening, OS patch checks, verified off-server
application-recovery rehearsals and persistent reliability observations. See
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for measured evidence and remaining
qualification requirements, and [EXPERIMENT25.md](EXPERIMENT25.md) for the separate
high-risk virtual account. Real options quotes and independent review remain
unverified; the seven-day observation period is collecting. No real money is traded.

## Server access for deploys

SSH to the Azure VM goes only over the owner's private Tailscale network
(device `league-engine`, 100.68.162.75). The public port 22 rule was removed on
22 November 2026, so deploys need neither `az login` nor a fixed home IP address.
Run `deployment/upgrade-paper-engine.sh` from this Mac with Tailscale connected
(`LEAGUE_VM_HOST` overrides the address). Emergency fallback if Tailscale is down:
re-add the rule saved in `deployment/nsg-AdminSSH-removed.json` in the Azure portal.
The website and API (HTTPS) stay public. Use one tool at a time for deploys.

## Start the application

On this Mac, double-click **Launch Last of Our League.command**, keep its
Terminal window open, then open http://127.0.0.1:8765/#terminal and click
**Start auto paper**. The launcher starts the dashboard with entries disabled.
Alternatively, the following command also enables automatic paper trading:

```bash
.venv/bin/python dashboard.py --auto-paper
```

Open **http://127.0.0.1:8765**. The local application polls the public research
feed every 60 seconds during the configured session window. Keep the application,
computer and network running so positions can be managed. No operating-system
service is installed. Use **Pause new entries** to stop entries while keeping
open-position exit management running.

The user-selected account starts with **₹5,00,000 virtual capital** and risks at
most **2% of current equity per entry**, subject to whole-lot sizing, a daily
risk budget, a maximum of three entries and drawdown limits. Its durable database
is `paper/intraday_500k.sqlite3`. The prior ₹20,000 account remains untouched.

The [public hosted interface](https://nifty-research-terminal.nearbydrape.chatgpt.site)
shows a labelled snapshot until connected to the hosted engine using your private
access key on the App page. Connected trader accounts can use the existing paper
controls; viewers can inspect results. The Azure engine runs independently of the
phone browser. The migration marker prevents starting a duplicate local account.

The dashboard now includes **Options lab**, **Risk & alerts** and **Trade review**.
Use the header to switch between slate/teal light and dark themes. Alerts run only
while the app is open; notes and strategy drafts stay on this device. The Workshop
adds chronological 70/30 and doubled-slippage diagnostics. Read the
[feature review](dashboard/FEATURE_REVIEW.md) for sources and data limitations.

If the local server stops, the dashboard shows **Paper engine disconnected**
and retries the connection every five seconds. Restart the launcher, then use
**Reconnect** if needed. A server restart creates a fresh session; controls
renew that session before acting. Reconnection does not enable trading by itself.

The terminal's **Strategy & execution** panel shows the selected strategy for
the latest market condition separately from the strategy in an open position.
It displays the last recorded entry/exit decision, the 5-minute trigger values,
the engine heartbeat, and today's stored BUY/SELL leg-fill counts. **View orders**
opens the paper order book; **Decision log** shows why each evaluated bar was
skipped, opened, held or closed. A selected strategy alone does not create a fill.

The public dashboard shows the exported snapshot time on every page. Its
**Engine activity** tab is available directly at `/#terminal/activity` and keeps
that selection after a reload. Public records update only when a new snapshot
is exported and published; refreshing the page cannot query the running local bot.
Before publishing frontend edits, run `node dashboard/prepare-assets.mjs` to
generate versioned scripts and styles so browsers do not mix cached versions.

## How strategies switch

The completed **15-minute** close, EMA20/EMA50 and ADX set direction. Closed
**5-minute** bars provide execution triggers. Volatility uses observed India VIX,
its prior-session historical rank, and trailing intraday realised volatility.

| Market condition | Candidate strategy |
|---|---|
| Rising trend + relatively cheap volatility | Bull call debit spread |
| Rising trend + relatively rich volatility | Bull put credit spread |
| Falling trend + relatively cheap volatility | Bear put debit spread |
| Falling trend + relatively rich volatility | Bear call credit spread |
| Range + relatively rich volatility | Iron condor |
| Unclear direction, mixed volatility, listed event, VIX shock or missing data | No new trade |

Candidates still must pass the five-minute trigger, premium/reward filter,
entry window, data freshness and account risk checks. The bot never forces a
trade just because a market is open. It does not close and reopen on the same
bar. TP/SL, a regime invalidation or the 15:15 square-off target closes a position
at the next available model observation. See [TRADING_PLAN.md](TRADING_PLAN.md)
for exact rules.

## Data and backtesting

```bash
# Download recent observed 5-minute Nifty and VIX bars.
.venv/bin/python intraday_feed.py --period 60d

# Run the intraday model backtest, including costs and slippage sensitivity.
.venv/bin/python intraday_backtest.py

# Validate engine, persistence, feeds, dashboard and paper controls.
.venv/bin/python -m pytest -q
```

Read `results/intraday/summary.md`. Recent history is limited; results are not
proof of a trading edge. The downloaded underlying/VIX observations are real
research data, but **option premiums, deltas, fills and exits are modelled** with
Black–Scholes, skew, slippage and configured costs. No actual option bid/ask,
liquidity, broker margin or intraday option-chain history is supplied.

If intraday VIX is missing, a sufficiently recent completed prior-day VIX may
be used as an explicitly labelled pricing proxy. No current/future daily close
is borrowed for a historical bar. Missing or stale price data blocks entries.
A missing square-off bar leaves the position unresolved and blocks the next
session; the engine never invents a later-price settlement.

## Terminal views and commands

The interface includes a market watch, 5m/15m candlesticks, strategy engine,
positions, activity, backtest comparisons, searchable trade journal, paper
account and report imports. The **Run intraday backtest** action operates in a
separate process so cost-sensitivity changes cannot affect the paper runner.

Open **Orders** in the sidebar, or **Trading terminal → Orders**, to inspect
recorded per-leg BUY/SELL fills: strike, expiry, quantity in lots, model price,
filled-bar time and opening/closing phase. CSV export and side/phase filters
are available. IDs start with `PAPER-`; these are model fills, not broker order
acknowledgements. Missing fills are never invented. **Positions** shows exposure;
**Trade history** shows closed trades; **Engine activity** shows decisions.

```bash
# A single automatic paper cycle, without downloading on that cycle.
.venv/bin/python auto_trader.py --once --no-refresh

# Standalone continuous automatic paper runner (instead of the dashboard).
.venv/bin/python auto_trader.py

# Inspect the forward account and its stored history.
.venv/bin/python intraday_paper.py review

# Refresh the portable dashboard snapshot for private publication.
.venv/bin/python dashboard.py --export
```

Run one local terminal/runner for this account. SQLite transactions and unique
bar IDs prevent duplicate processing, but running multiple feed writers is
unnecessary. Changes to pinned strategy/code settings require a separate account
experiment rather than silently changing an existing ledger.

## Weekly research retained

The weekly research engine remains available through `run_backtest.py` and
`paper_trade.py`. It is separate from the new automatic intraday mode.

```bash
.venv/bin/python run_backtest.py --profile adaptive_regime
.venv/bin/python live_signal.py --explain
```

`results/summary.md` contains the current 100-point weekly comparison. Previous
200-point credit-only reports are preserved in
`results/algorithms/credit_regime_200pt_v1/`. These differently sized structures
are separate experiments. Historical lot sizes/rates and nominal expiries remain
model assumptions, and the inspected 2023 split is a diagnostic, not untouched
validation.

## Develop and add strategies

Use **Develop strategies** in the dashboard or the mobile **Strategies** tab.
The [Strategy Workshop](https://nifty-research-terminal.nearbydrape.chatgpt.site/#strategies)
supports editable rule templates, saved drafts, JSON import/export, browser
backtests and comparison with the adaptive baseline. Drafts are stored per
browser and do not activate the cloud bot. See [the workshop guide](STRATEGY_WORKSHOP.md).


## Market terminal and shared development

The dashboard now uses a dark, amber market-terminal design, with model payoff
scenarios, a strike-centred theoretical option chain, synthetic volatility surface,
actual paper-position Greeks and a recorded execution stream. Panel order is saved
on the device and can be changed by dragging its handle or using keyboard buttons.
Existing paper start/pause controls remain connected to the original engine.
Live trading, observed OI/GEX and immediate flatten are unavailable. Read
[the terminal guide](dashboard/TERMINAL_DESIGN.md) for data and execution limits.

Both developers should use a Git clone and follow [COLLABORATION.md](COLLABORATION.md):
pull before working, make changes on a feature branch, test, commit, push and review
a pull request. Local saves and browser strategy drafts do not automatically sync.
GitHub source changes and publication of the running app are separate steps.
