# Last of Our League — paper-production release 1.2.2

Release 1.2.2 was installed and verified on 24 November 2026 on the existing Azure VM. Dashboard version 17 remains published. Release 1.2.1 verification below is historical evidence. The scope remains automatic options **paper trading**, one shared ₹5,00,000 account, separate authenticated clients and one trading worker. No broker execution is enabled. The approved recovery/monitoring resources use the existing student subscription; its spending limit remains On.

## Changes and verified safeguards

- Start/pause entry admission is serialized with the active paper transaction. Pausing during a network fetch blocks that cycle's subsequent entry; existing exits remain managed.
- Invalid OHLC ranges from the provider or CSV are rejected before they can become trade observations.
- Low disk headroom blocks new entries while the worker continues to process exits.
- A status persistence error disables entries instead of silently killing the worker. A failed start cannot leave entries enabled.
- A supervised-worker watchdog requests a restart for a dead worker or a heartbeat older than five minutes, after startup grace. Closed markets, paused entries, risk halts and fresh feed-error heartbeats do not cause restart loops.
- Runtime state-directory overrides now also isolate the trading database.
- Backup manifests use durable atomic writes. Hourly VM backups retain verified SQLite snapshots. A separate hourly identity-authenticated Azure Blob job now uploads private copies, downloads them for SHA256 verification and restores them into an isolated temporary directory for SQLite integrity checks.
- The new deployment path builds and runs isolated Linux tests before stopping the existing engine, refuses cutover during market sessions or with an open position, verifies the policy fingerprint, makes a private full-state backup, checks readiness and exact account preservation, and restores the previous source/image/configuration on cutover failure. A regression test proves a failed candidate build never stops the running service.
- The dashboard distinguishes market-closed standby from a stale active-session feed, suppresses stale trigger badges, shows live operations/version/backup/disk information when supported, and negotiates idempotency support before adding new request headers. Older cloud versions remain compatible.
- The Connect devices page explains the two-laptop shared-account model. Existing trader/viewer roles are retained; browser notes, alerts and research drafts remain device-local.

The deployment scripts are `deployment/upgrade-paper-engine.sh` and `deployment/install-production-release.sh`. Dependencies are installed from an offline Linux/Python 3.12 wheel bundle, verified against the application and bootstrap hash locks. CI downloads that bundle before image builds. No TLS verification is disabled. The former requires a verified SSH known-hosts file; it never disables host verification or prints access keys. The older deploy-release.sh entry point now forwards to the same guarded upgrade path.

## Evidence

148 local Python tests, 145 isolated Linux tests (three browser-parity tests run locally), and nine dashboard suites passed. Live HTTPS authentication, CORS, viewer restrictions, readiness, backup status, account preservation and unprivileged execution were verified. An actual VM backup was restored in an isolated temporary container: its manifest checksum, SQLite integrity, initial capital, flat position and policy fingerprint were verified. The account backup was copied only from the VM to the approved private Azure storage; no account database or backup was exported to a laptop. The published Connect devices page was checked in Safari.

Local and cloud verification results are recorded in `deployment/status.json`. After publishing version 14, Safari was refreshed and reconnected using the existing trader sign-in. Risk & alerts showed release 1.2.1, readiness, off-server recovery Ok and restore verification Passed. The dependency scan is `results/dependencies-2026-11-23.json`; it found no known advisories at scan time. This is not a guarantee against vulnerabilities. Container/OS vulnerability scanning is separate.

Tests cover control races, stale/replayed bars, isolated research, authenticated roles/CORS, durable idempotency, API bounds, ledger migrations and accounting, concurrent writes, backup/restore, watchdog decisions, input validation, mobile API/cache behaviour, chart interactions and automatic strategy routing. The browser research model remains checked against Python on the local machine.

[Docker's official startup guidance](https://docs.docker.com/compose/how-tos/startup-order/) explains why service readiness must be checked separately from container startup. The API hardening follows scoped [OWASP REST guidance](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), including authentication, method/content validation and restricted origins. These references do not certify this application.

## Operational limits

- This is a single-VM, single-account paper deployment, with one open position, at most three entries/day and five lots when existing risk sizing permits. It is not a high-frequency or multi-tenant execution service.
- The underlying/VIX feed is public research data; option premiums and fills are modelled. No licensed live option chain, broker margin or exchange fill reconciliation is connected.
- A feed outage blocks entries. Exits can be delayed until valid observations return; a stop rule is not guaranteed execution.
- Private off-server backups are enabled with seven-day lifecycle retention and seven-day soft delete. The container is encrypted at rest, requires HTTPS/TLS 1.2, blocks anonymous blobs/shared keys and grants the VM identity container-scoped access. This is recovery from VM/disk loss, not independence from the Azure subscription or region. No account backup is exported to either laptop. Snapshots above the 64 MiB job bound fail visibly instead of uploading without a size limit.
- Browser alerts require the app open. Separately, Azure Monitor checks `/readyz` every five minutes from five locations and notifies the designated email if three locations fail. This runs when the browsers/laptops are closed. An actual harmless activity-event alert fired and the recipient confirmed receiving it. Azure’s manual test-send API is unavailable on this free subscription. These are email alerts, not native phone push notifications.
- GitHub CI is active for the shared source repository; read the current run results before claiming checks passed for a new commit.
- Azure student credit and allowances are finite. No permanent free-hosting or availability guarantee is made.
- A long-duration production soak and physical-device end-to-end checks remain separate from the automated release checks.


## 23 November recovery and research evidence

- The cloud release gate passed 145 Linux tests with three browser parity cases run
  locally. Exact account preservation, policy fingerprints, readiness and ledger
  integrity were checked before the release completed.
- `results/capacity-2026-11-23.json` records an isolated 100,500-trade / 100,000-event
  fixture, 1,600 HTTP requests from 16 simulated clients and no request errors.
  Its separate overload burst returned 429 as intended. This is local capacity
  evidence, not a VM throughput SLA or permission to exceed trading risk limits.
- `results/readiness-soak-2026-11-23.jsonl` has ten successful low-rate observations
  over nine minutes. External probes have begun collecting longer-term evidence;
  a multi-day soak cannot be declared complete today.
- Automated Bandit scanning reported 0 high, 9 medium and 29 low findings. The medium
  findings were reviewed: the history SQL identifiers are allowlisted with bound
  values; URL findings refer to fixed endpoints or operator-only tools and
  hash-verified dependency downloads. The raw scan is retained. This is an
  implementer review plus automated scanning, not independent human certification.
- The dissertation-informed volatility experiment is an isolated research process,
  with no network, paper-account mount or order-control credentials. It runs at
  16:00 IST on weekdays. Fresh cloud history gives 40 held-out sessions, with
  QLIKE 0.392 versus 0.711 for the validation-selected simple reference. It predicts
  variance, not options profit, and never changes the running strategy.
- The observed bid/ask research adapter is implemented and tested, but no market-data
  account or real quote export was supplied. The paper engine still uses modelled
  option fills. See `research/README.md` for the dissertation code review and
  evaluation limitations.

The monitoring plan intentionally uses free URL ping tests, not paid Standard tests.
Microsoft currently retires ping tests on 30 September 2028; migrate before then.
Storage, logs and alerts can consume student credit. The log quota is 0.023 GB/day;
quota and budgets are not a universal billing cap. No paid upgrade was performed.

References: [Azure monitoring prices](https://azure.microsoft.com/en-us/pricing/details/monitor/),
[availability-test lifecycle](https://learn.microsoft.com/en-us/azure/azure-monitor/app/availability),
[managed-identity Blob access](https://learn.microsoft.com/en-us/azure/storage/common/storage-auth-aad-msi),
and [free-subscription test-send limitation](https://learn.microsoft.com/en-us/answers/questions/5566446/bug-cant-test-action-group-the-error-message-is-em).

## Privacy and usage update — dashboard version 15

Published and checked in Safari on 23 November 2026. The footer links to the public
privacy/usage notice and device-data controls. Scoped exports exclude credential
keys; confirmed deletion targets only the listed app keys. The page cannot call
cloud account or trading-control APIs. Default theme initialization no longer writes
a preference merely because the page opened. Ten dashboard suites passed, including
privacy isolation, escaping, UTF-8 sizing and unknown-key preservation checks.
Nineteen hash-locked application/bootstrap wheels have bundled licence notices.

`legal/READINESS.md` maps all 15 screenshot items to evidence and remaining work;
`legal/INCIDENT_RESPONSE.md` provides an operator procedure. Operator identity,
country and public contact are awaiting confirmation. Applicable legal bases,
GDPR/DPDP duties, provider agreements/transfers, ownership and OS/container licence
review remain unresolved. No contract, legal certification, marketing consent or
payment terms were fabricated. No shared account record was deleted, no access was
expanded and the engine was not restarted for this frontend-only update.

## Static release checks — dashboard version 16

The Site now publishes a separately assembled `dashboard/build`, containing 27
allowlisted static files. Duplicate working source and source maps are excluded.
Release gates verify paths, asset fingerprints, imported modules, credential patterns
and the two existing local access-key literals without printing their values. The
publication archive was checked against the file/hash inventory, excluding metadata
sidecars, links and extra paths. Eleven dashboard/release suites passed, including
exact parity of the emitted browser backtest with its source (21 modelled trades).
The published terminal was checked in Safari. BLA 3.5.7 received a targeted source
review but was not installed or executed. No decoys or runtime transformations were
introduced. See `SECURE_RELEASE.md` for assessment, procedure and limitations:
browser-delivered code remains copyable. This is not an anti-cloning certification
or a change to the authoritative cloud trading policy.


## 24 November operational hotfix — release 1.2.2

The live readiness endpoint returned 503 during a real exchange holiday because the
runner treated every weekday as an open session. The new reviewed NSE F&O calendar
uses [FAOP/71777](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf)
and its [15 January amendment](https://nsearchives.nseindia.com/content/circulars/FAOP72262.pdf).
Holidays, weekends and unsupported special sessions do not authorise entries or
unnecessary feed polling. Unreviewed years fail closed and degrade readiness.
Calendar coverage currently ends on 31 December 2026 and must be maintained against
new exchange circulars; it is not an automatically updated calendar service.

Exits remain managed; an unresolved position during a closed session still raises
a fault. Actual stale feeds on regular trading days remain unhealthy. The guarded
installer uses this calendar and still refuses cutover with an open position.
The live holiday-window upgrade passed 158 isolated Linux tests; three browser
parity cases were covered locally. All 161 local Python tests passed. The installer
verified exact account preservation, the pinned pricing/risk fingerprint and SQLite
integrity. External HTTPS, authentication, CORS and viewer-control checks passed.
Readiness recovered to HTTP 200 with closed-market standby. No broker order or
account-data export was performed. See `deployment/release-1.2.2.json`.

The capacity tool now generates its own hedged sample and synthetic report instead
of reading a real account or copying personal reports. A fresh local fixture held
100,500 trades and 100,000 events, served 1,600 requests from 16 clients with zero
errors (p95 18.49 ms), and passed isolated backup/restore. Its separate burst returned
429 as intended. These are local storage/HTTP measurements, not VM, market-data,
exchange-order or simultaneous-position throughput claims. The one-position and
three-entry daily policy remains in force. Large histories exceeding the configured
off-host backup bound need a separate capacity/streaming-backup plan.

GitHub CI is active and performs tests, locked-dependency auditing and a Docker
build. A separate CodeQL workflow scans Python and JavaScript on pushes and pull
requests. A completed job does not prove the absence of findings: inspect the Security
tab. Automated scanning is not an independent human security review.

This is a controlled paper deployment. Licensed option prices/fills, extended healthy
soak evidence, physical two-device acceptance, a full replacement-VM recovery drill
and applicable operator/legal review remain outstanding. The existing nominal expiry
pricing model was not silently changed in the pinned running account. This operational
calendar fix does not validate its option prices, profitability or real-money execution.
