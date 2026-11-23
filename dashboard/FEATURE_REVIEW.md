# Trading platform feature review

Reviewed 21 November 2026. Scope: Last of Our League, a Nifty options research and automatic paper-trading application. This is a focused comparison with official platform documentation, not a claim that every trading product or search result was reviewed.

## Findings and changes

| Capability | Existing application | This update |
| --- | --- | --- |
| Market-condition strategies | Adaptive trend/range and volatility routing; visible decisions and skip reasons | Preserved the active policy; linked engine activity from the tools desk |
| Orders and positions | Stored BUY/SELL opening and closing model fills, positions, export and account P&L | Retained; did not invent exchange order statuses or broker funds |
| Portfolio risk | Entry/day/lot/drawdown limits in the engine | Added a dedicated Risk & alerts page with equity, stored unrealised P&L, peak drawdown, entry risk budget, daily budget and open-position model risk |
| Operational status | Engine heartbeat, source bar and reconnect states | Consolidated data freshness and connection checks; pause entries uses the existing permission-checked API and keeps exits managed |
| Options analysis | Hedged structures and configured pricing model | Added Options lab: five structures, leg premiums, position delta/gamma/theta/vega, expiry payoff, break-evens, fixed-fee profit/loss bounds and spot scenarios |
| Alerts | No custom user condition alerts | Added price, daily closed-loss, drawdown and engine-attention alerts with edge-trigger latching, acknowledgement, rearm, pause and delete |
| Strategy development | Device library, rule templates, JSON import/export, worker backtests, baseline comparison | Added a chronological 70/30 diagnostic and a 2× slippage stress run to each Workshop result/report |
| Trade review | Stored closed trades | Added daily closed-P&L calendar, visible-history statistics, per-trade tags/notes and JSON note transfer |
| Appearance | Single dark navy/gold theme, several small labels | Slate/teal light and dark themes, persistent preference, larger controls/text, responsive cards and a mobile Tools tab |
| Account security | HTTPS engine, session-only keys, trader/viewer permissions | Reused existing access checks; no new public account data or credentials added |

TradingView describes account managers with equity/P&L, positions, orders, history, journals and exports; these informed the account/review comparison. [Official account-manager documentation](https://www.tradingview.com/support/solutions/43000786138-what-is-the-account-manager/).

TradingView documents condition-based alerts. This release implements browser-local conditions only, without claiming TradingView-style server delivery. [Official alerts documentation](https://www.tradingview.com/support/solutions/43000595315-how-to-set-up-alerts/).

The Options Industry Council describes Greeks as theoretical sensitivities. The lab calculates finite differences of this repository's configured pricing/skew model, aggregates signed quantities and labels the results accordingly. [OIC: Understanding Options Greeks](https://prd-web.optionseducation.org/advancedconcepts/understanding-options-greeks).

QuantConnect's research guide discusses overfitting and out-of-sample validation. Workshop segment tests use separate virtual accounts, chronological complete sessions and no parameter search. Repeated inspection means these results cannot be described as an untouched holdout. [Official research guide](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide).

## Limits that require more than a dashboard update

- Live option bid/ask, depth, OI, traded volume, liquidity/fill modelling and exchange-adjusted expiry calendars require a suitable licensed feed. The lab uses observed underlying reference bars and theoretical option premiums; its research contract size is not verified against current exchange specifications.
- Broker margin, live order entry/amend/cancel, reconciliation and genuine exchange fills require a broker integration. The user's selected mode remains paper trading. [Kite's official order API documentation](https://kite.trade/docs/kite/orders/) illustrates this separate execution layer.
- Alerts evaluate only while this app is open and has fresh connected observations. They are not iPhone push/email, do not run on the server and do not place orders. Disconnect/stale price data cannot trigger or rearm price alerts. Browser suspension can delay evaluation.
- Notes, alert definitions and strategy drafts are saved per browser/device, not synced to friends or other devices. Notes JSON export/import transfers review notes; Workshop JSON transfers strategies. Storage failure is reported, and imports validate before committing.
- Expiry payoff uses fixed reference-premium closing fee estimates so payoff bounds are defined. It excludes actual exercise/settlement charges, liquidity and gaps. No estimated fee is a broker charge quote.
- Strategy backtests use model premiums and same-bar execution assumptions. The chronological and stress diagnostics are research checks, not profitability evidence. The available dataset ends on 16 November 2026 and contains 61 complete sessions.
- New research tools do not activate strategies or change the cloud account. Existing 2% entry risk, 3% daily budget, 3 entries/day, 5-lot limit and one-position policy remain. The engine deliberately does not submit large bursts of trades. Prior local historical-storage/HTTP capacity measurements are in `../ENGINEERING_AUDIT.md`; they do not establish high-frequency execution capacity or a cloud throughput guarantee.
- This release publishes the dashboard, not the deferred Azure backend reliability release. It neither requires nor attempts a new Azure sign-in.

## Validation

- 113 Python tests passed, including browser/Python model parity and account isolation.
- Eight dashboard suites passed: existing reports, control recovery, public routing, order rendering, execution visibility, mobile permissions/cache handling, Workshop and new platform checks.
- New checks cover risk calculations, payoff extrema/break-evens, lot aggregation, stale-data alert latches, quota failures, atomic note imports, text escaping, viewer control rejection, persistent themes and independent research diagnostics.
- Safari visually rendered the desktop options lab and a 390px iframe mobile layout. Browser host access was unavailable and native Safari element actions failed, so full interactive browser and physical-iPhone verification were not completed. Automated module/controller checks cover the new actions.


## Automatic selection follow-up — 21 November 2026

Automatic routing is now the default Workshop experience. Per-condition
strategy dropdowns and template selection are advanced custom research controls.
The same page shows the engine-reported candidate, active position and fills,
with explicit saved/disconnected labels. Existing custom drafts remain editable
and imports/exports retain the version 1 definition format. No policy, risk,
account or broker integration changed. All nine condition combinations and
event/shock/missing-data vetoes are covered by checks.

A read-only HTTPS engine check at 19:12 IST confirmed automatic paper trading
enabled, market closed, last source bar 20 November 15:30 IST, rising/rich
conditions, bull put spread candidate and no open position. This is a timestamped
observation, not a promise that a later entry will occur.


## Paper-production follow-up — 22 November 2026

The dashboard adds connected server readiness/backup/disk diagnostics, correct
closed-market standby, capability-negotiated action identifiers, a shared-device
connection guide and a static content-security policy. Nine dashboard suites
pass. Backend release 1.2.0 adds operational safeguards while retaining the
existing strategy fingerprint and account; definitive installation and live
verification evidence is in the engine workspace deployment/status.json.
