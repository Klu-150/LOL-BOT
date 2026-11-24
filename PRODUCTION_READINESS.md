# Readiness record — release 1.3.2

Updated 24 November 2026. Engine 1.3.2 is deployed on the existing Azure VM;
public dashboard version 20 is published. This is an invited, shared **model-based
options paper workspace**, with separate original and high-risk experimental
ledgers. No broker execution is enabled. Both pinned policies and private account
histories were preserved. Prior dated release records remain in Git history.

The deployment is hardened for controlled paper operation. Full production
qualification remains incomplete until the observation period, independent
security review and authorised real-options-data validation have finished. A
healthy `/readyz` result reports current operation; it is not that qualification.

## Gap status and evidence

| Area | Verified result | Practical limit / remaining work |
| --- | --- | --- |
| Off-server recovery | Private Azure Blob archives, identity-based access, download/hash verification and SQLite restore checks. The hourly uploader takes a fresh snapshot immediately before upload. | Same Azure subscription/region. Target recovery point is roughly one hour when jobs succeed; no guaranteed RPO. |
| Application recovery | Actual off-server archive booted in a fresh container: both ledgers, policy hashes, authenticated dashboards, viewer restrictions, entries disabled and exact account preservation passed. Measured 18.6 seconds in the first successful drill. | Same existing VM, no network or live-volume mount. Replacement-VM provisioning and subscription/region loss were not tested. |
| Outage alerts | Existing external Azure checks every five minutes; designated recipient previously confirmed an actual `league-email-delivery-check` alert. Feed, worker, backup and disk faults degrade readiness. | Email delivery and provider availability are external dependencies; browser alerts are separate. |
| Load | Actual-VM isolated synthetic fixture: 100,500 trades, 100,000 events, 1,600 HTTP requests, 16 clients, zero errors; p95 119.02 ms on release 1.3.2. The 157,429,760-byte database also passed the streaming off-server archive/restore format. Separate overload burst returned 429. | Separate container, 0.5 CPU/384 MiB, no TLS/WAN or live ledger. This does not validate exchange execution, simultaneous portfolios or HFT. |
| Long-running evidence | Five-minute bounded observations persist on the VM, with a weekly isolated recovery rehearsal. Health gates detect stale observation/recovery evidence and failed new rehearsals. | Seven continuous calendar days of sufficiently complete healthy observations are required by the evidence tool. Collection started today; it is not complete. The observer is on the VM; independent external Azure probes remain separate. |
| Security | 189 local Python tests, 186 Linux tests plus three locally checked browser-parity cases, dashboard suites, CodeQL findings gate, locked Python-dependency audit, and new Debian/OSV gate. OS updates applied; post-update scan: 61 source packages, zero advisories with available fixes, 89 unfixed advisory matches retained for review. | Automated scans do not establish reachability or constitute independent human review. Codex Security was offered but is not confirmed connected. Gateway/host and remaining vendor advisories need review. |
| Real options data | Strict observed bid/ask research adapter exists and rejects stale, future, crossed, insufficient-size and unsynchronised quotes. | Operator confirmed no broker/market-data account. No real option-chain feed, margin, contract-master or broker-fill validation is connected. Prices/fills remain modelled. |
| Operator notice | Venkata Madhan Kanakala, India, and supplied public support/privacy email published and checked in Safari. | Provider agreements, applicable legal duties and commercial ownership/licensing still require assessment before wider launch. No legal certification or contract acceptance was fabricated. |

The load fixture's history exceeded the former 64 MiB raw-backup bound. Hashing and
restore extraction now stream database files. Limits remain explicit: 512 MiB total
uncompressed recovery members and 64 MiB compressed/network archive. Size checks,
member allowlists, duplicate/path rejection, checksums and SQLite integrity remain
mandatory. Larger histories need a measured archival plan; limits are not unlimited.

## Reliability fixes in this release

- Experimental readiness now catches stale data, missing data, storage faults,
  malformed/future heartbeats and dead workers. An alive but stalled child is
  recycled after startup grace; fresh feed-error heartbeats do not restart-loop.
- Missing optional research reports no longer hide recovered accounts. The cloud
  dashboard returns explicit unavailable research metrics and keeps ledger views
  usable. It does not invent a successful backtest.
- Runtime root filesystem is read-only. Startup uses only the capabilities needed
  to initialise existing private storage, then drops to UID 10001. The live process
  has zero effective capabilities. Private files use restrictive modes/umask.
- Guarded upgrades build/test before cutover, require all ledgers flat and pinned
  policy hashes unchanged, back up state, verify exact preservation and roll back
  failures. A real failed hardening attempt rolled back successfully; the corrected
  bootstrap was tested separately before retry. Failure logs stay private.
- Future upgrades run the required version-bound recovery rehearsal before
  readiness, preventing a stale previous-release recovery report from approving
  a new image. Completed recovery copies are removed; failed copies remain private
  for operator review. Summaries contain no account bodies.
- CI checks Debian source-package versions against OSV and fails when an available
  fix remains. Unfixed advisory matches are reported, not hidden. Weekly CI also
  reruns the checks; scan/database failure is not treated as a clean result.

## Operating bounds

The original account retains 2% entry risk, at most five lots/three daily entries,
and one position. The experimental ledger retains its explicitly authorised 25%
entry/daily risk budgets, 30% drawdown halt threshold, 100-lot ceiling, six daily
entries, confirmed intraday replacement and separate capital. Admission thresholds
are not guaranteed loss limits. Its historical model replay lost about ₹1,53,628
and halted; higher exposure did not establish an edge.

Both use completed 15-minute bias and five-minute triggers, entries 09:45–14:30 IST
and a 15:15 square-off target when valid exit observations are available. Public
underlying/VIX data and nominal expiry assumptions do not establish real option
execution. A feed outage can delay exits. Calendar coverage ends 31 December 2026;
unreviewed years/sessions fail closed. Do not describe this as real-money ready.

`/api/operations` exposes allowlisted recovery and observation evidence after
sign-in; Risk & alerts displays it. API keys, private ledgers, recovery archives
and account exports are excluded from GitHub and public static assets. Existing
trader/viewer permissions and Site audience were retained. Both laptops can close;
the engine, schedules and external monitor run in Azure. Student credit is finite;
no new resource, subscription upgrade or paid service was created by this release.

## Reproduce and operate

Run the checks in `.github/workflows/ci.yml`. `tools/capacity_check.py` uses synthetic
state only. `tools/os_audit.py` sends only installed public package names/versions
to OSV. `tools/soak_probe.py --once` records a bounded HTTPS observation; missing
observations count as gaps. `deployment/recovery-drill.sh` is root-only on the
existing VM and never restores over the live volume. See the recovery runbook for
schedules, failure handling and the remaining replacement-VM procedure.

Primary references: [OSV query API](https://google.github.io/osv.dev/api/),
[NSE real-time data](https://www.nse.in/static/market-data/real-time-data-subscription),
[DPDP notification](https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf).
These references do not certify this application or supply a data licence.
