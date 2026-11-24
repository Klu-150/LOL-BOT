# League market-terminal interface

This is an original Bloomberg-inspired visual direction: near-black surfaces,
amber navigation, blue analytical series, monospaced prices, compact square panels
and a function bar. It retains the current buildless browser modules and Python
paper API, rather than introducing an unrelated React/FastAPI/Redis application.
OpenBull was inspected as a design reference; its AGPL source is not incorporated.

`terminal-analytics.js` adds four reorderable panels, with keyboard move controls
and browser-local layout persistence. The payoff study includes the current model
curve and intrinsic expiry payoff. Spot, IV and elapsed-time scenarios preserve the
entry basis; all results are one-lot studies with reference fee estimates. Study
settings never alter engine risk limits, positions or active strategy definitions.

Header Greeks are computed from the actual loaded paper-position legs and lots,
not the selected study structure. A flat account has zero exposure; missing or
expired valuation data shows unavailable values. Units: delta is rupees per spot
point, gamma rupees per point squared, theta the model one-calendar-day change,
and vega rupees per one IV percentage point. Values are as of the source bar.

The chain has theoretical premiums and delta around ATM. India VIX is a pricing
proxy, not observed contract IV. The projected surface illustrates the configured
synthetic skew over assumed maturities; it is not an observed or calibrated market
surface. Bid/ask, open interest and market gamma exposure remain unavailable until
a licensed data feed exists. No invented volume, OI or live tick stream is shown.

The existing start/pause controls keep their permission, connectivity and uncertain
request protections. Pause blocks new entries and preserves exit management. The
requested immediate flatten and live execution controls are explicitly unavailable:
the current API has neither feature. The five existing defined-risk structures
remain under one automatic router; 0DTE and gamma scalping are not added as fake
independent bots. API polling is retained; there is no WebSocket market-data source.

Candlesticks, orders, strategy development, performance, alerts and device connection
remain available. Dark is the default for new browsers; existing theme preferences
are respected. The light theme, keyboard focus, reduced motion and mobile navigation
are retained. No backend restart or strategy-policy change is needed for this release.

Checks: `node dashboard/terminal-analytics-checks.mjs`, existing dashboard suites,
release allowlist/credential/hash checks and Safari visual/interaction verification.
