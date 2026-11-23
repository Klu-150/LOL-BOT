# Last of Our League — options paper terminal

The local terminal includes candlesticks, market watch, automatic regime routing,
paper positions, account risk controls, historical trade inspection and backtests.

From the bot repository root:

```bash
.venv/bin/python dashboard.py --auto-paper
```

Open `http://127.0.0.1:8765`. Keep the app and computer running to manage intraday
exits. **Start auto paper** enables entries; **Pause new entries** leaves exits
active. **Run intraday backtest** operates in an isolated subprocess, so its
sensitivity overrides never change the running paper worker's cost settings.

All automation is virtual. There are no broker credentials or order APIs.
Loopback-only controls require the local page's origin and ephemeral session
nonce. No control nonce is exported to the hosted snapshot.

## Views

- **Trading terminal:** Nifty/VIX watch, actual 5m/15m candles and EMAs, condition
  matrix, automatic engine status, virtual positions and activity.
- **Performance / comparisons:** returns, drawdowns, report metrics and costs.
- **Market data:** underlying daily observations and regime indicators.
- **Trade journal:** historical model trades with fees, legs and CSV exports.
- **Paper account:** persisted forward positions and realised/marked equity.
- **Orders:** stored paper BUY/SELL leg fills, strikes, expiries, quantities in
  lots, model fill prices, timestamps, phase filters and CSV export. Entry-side
  order IDs remain stable after closing; missing exit prices are not fabricated.
- **Data & reports:** additional compatible algorithm imports and provenance.

The default report is the intraday run in `results/intraday/`. Weekly research
and the previous 200-point credit-only experiment remain distinct report sets.
Use each report's labelled timeframe and hedge width when comparing outcomes.
Intraday history is short and option fills remain theoretical; losses are kept.

## Private snapshot

```bash
.venv/bin/python dashboard.py --export
```

The buildless `dist/` directory is published as a private Site. It contains the
exported dataset and UI, not SQLite files, the Python worker or credentials.
The hosted UI cannot start local automation and labels its controls accordingly.
Imported reports remain in browser memory and are never uploaded.

The retained `.openai/hosting.json` identifies the existing Site. Keep its ID
and owner-private sharing when updating the interface. There are no external
charting, font, image or JavaScript dependencies.

Checks: `node checks.mjs` verifies financial filtering/format intake; `node
render-checks.mjs` verifies all eight generated views. Browser QA is separate.


## Platform tools

`#options` models defined-risk payoff, Greeks and scenarios. `#desk` shows account
risk, freshness and device alerts. `#review` provides a forward-paper P&L calendar
and local review notes. Theme preference persists per browser. Workshop results
include chronological split and slippage stress diagnostics. See
[FEATURE_REVIEW.md](FEATURE_REVIEW.md) for sources, scope and verification.

Run `node platform-checks.mjs` alongside the existing suites.


## Automatic selection

The Strategies page opens with automatic adaptive routing and a read-only
condition table. It displays the existing engine execution panel, including
snapshot/disconnection state, candidate, active position and stored fills.
Custom research definitions remain available under Advanced: custom rules;
existing saved definitions are preserved. Research saves never change the
running account. The paper engine already selects the matching structure on
each eligible completed bar and can choose no trade. It manages open positions
under exit rules instead of replacing them whenever the candidate changes.


## Chart and selection interactions

Theme colors cover hovered/selected table rows and active watchlist, comparison
and routing items. Chart tooltips/crosshairs dismiss on pointer leave/cancel/up,
scroll (including nested containers), outside pointer down, focus changes, Escape,
page backgrounding and window blur. Touch scrolling does not activate hover.
These lifecycle regressions are covered by `node interaction-checks.mjs`.


## Paper-production operations

The connected Risk & alerts page displays server readiness, release, backup
status and free disk space when supported by the engine. Closed-market standby
is distinguished from a stale active-session feed. Connect devices documents
one shared cloud engine for both laptops, with separate trader/viewer sign-ins.
The client negotiates idempotency support and remains compatible with older
engines. Static page CSP blocks third-party scripts and native form submission;
the application submits validated API actions through its event handlers.


## League workspace design

The desktop shell groups Trading desk, Research and Workspace navigation. The chart,
positions and strategy engine lead the terminal; the full execution diagnostics follow
below. `dist/workspace.css` owns the shared visual tokens and component refinements
for the light/dark themes. `prepare-assets.mjs` combines it with the retained component
stylesheet and fingerprints the result with the browser modules.

Phone layouts use a fixed five-item navigation dock, an off-canvas menu with backdrop,
Escape dismissal and keyboard focus containment, and horizontally scrollable data
books. The connection form leads Connect devices so both laptops can sign in without
scrolling past installation instructions. Snapshot and disconnected states remain
explicit; the UI never fabricates running status or fills. No execution rules or account
data are changed by this design release.

The recovery card also shows the connected engine’s off-server backup state, last successful copy and isolated-restore verification. It keeps VM snapshot status separate and never treats an unconfirmed off-server copy as healthy.
