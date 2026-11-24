# Adaptive 25% virtual experiment (1.3.0)

This opt-in experiment uses a separate ₹5,00,000 ledger and child process. The
original 2% account, pinned strategy files and history remain unchanged. It is
paper trading with modelled prices, fills and costs; no broker orders are sent.

The policy reserves at most 25% of current equity as estimated full spread loss
plus cost reserves, subject to the remaining daily budget and a 100-lot ceiling.
There are at most six entries per session, one open structure, a five-minute
cooldown, a 25% daily loss budget and a 30% peak-equity drawdown halt. These are
admission thresholds, not guaranteed loss limits; gaps and model errors can breach
them. Risk reserve is not broker margin or cash allocation.

A net profit target equals 25% of collected credit for credit structures, or 25%
of maximum gross payoff for debit verticals, after model entry/exit charges.
Existing loss exits and the 15:15 IST square-off target remain. No profit target
is guaranteed, and no historical trades are entered on startup.

Each completed five-minute observation uses completed fifteen-minute bias.
Bullish/rich selects bull put, bullish/cheap bull call, bearish/rich bear call,
bearish/cheap bear put, range/rich iron condor. Unclear, event, shock and missing
bias conditions block new entries. Replacement requires two observations of a
different candidate, a matching trigger, a qualifying quote and an affordable
replacement within entry/session limits. The existing position closes first;
re-entry waits until another bar and is rechecked. A candidate is not a fill.

## Historical comparison

One unoptimized local model replay (61 sessions, August 18–November 16, 2026)
ended at ₹4,89,471 for the baseline (−₹10,529) and ₹3,46,372 for this experiment
(−₹1,53,628, drawdown halt). Higher exposure did not establish a trading edge.
Reproduce independently; source observations, model assumptions and dates matter:

```sh
python paper_experiment.py backtest --profile baseline --output /tmp/baseline.json
python paper_experiment.py backtest --profile adaptive25 --output /tmp/experiment.json
```

## Operations and isolation

The authenticated cloud API offers GET `/api/experiment/status` and
`/api/experiment/dashboard`; POST `/api/experiment/start` and
`/api/experiment/pause` require trader permission and accept idempotency keys.
Pausing waits for an in-flight cycle and keeps exits managed. Both accounts use
the same observed feed with separate SQLite transactions, controls and policy
fingerprints. Workers resume after server restarts; readiness checks flag a dead
or stale experimental worker. The original account must keep refreshing the feed.
The dashboard account selector routes controls to the selected ledger. Account
P&L, strategy observations, fills and sizing are read from that account only.
The local single-account server does not expose this experimental control API.

Private SQLite snapshots include the experiment once it exists. Guarded upgrades
require all existing paper accounts flat, unchanged policy hashes, integrity
checks and exact state preservation. Off-host backups use the existing private
Blob store and verify restoration. No credentials or private histories belong in
GitHub or the static website. Confirm a fresh recovery copy after activation.

This release does not constitute independent security certification, validated
real option execution, a guaranteed profitable strategy or a long-running soak.
