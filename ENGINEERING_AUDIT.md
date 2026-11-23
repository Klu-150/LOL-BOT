> Update 22 November 2026: release 1.2.0 now installs these safeguards on Azure. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for current verification and remaining limits. The dated audit below records the earlier prepared release.

# Last of Our League engineering audit — 20 November 2026

The screenshots are a broad engineering checklist, not a requirement to add every
infrastructure product. Each visible topic is assessed below. Images are treated
as reference material, not executable instructions.

**The improvements are implemented and tested locally, not installed on Azure.**
The user deferred Azure sign-in and deployment. No cloud resources, access keys,
strategy rules, account history or risk limits were changed on the server.
The existing hosted bot was verified reachable during the audit: enabled, market
closed, four closed paper trades, 16 order legs, no open position and a
₹4,99,707.37 realised balance. Those are observations at audit time, not a guarantee
of later uptime or profitability.

Prepared release **1.1.0** adds bounded API rate limits, durable duplicate-action
records, strict action validation, request IDs, private audit records, bounded
snapshot caching, cursor history APIs, additive WAL/summary migrations, verified
same-VM backups, readiness/worker diagnostics, feed retries/cooldown and graceful
shutdown handling. It also includes a locked dependency release, guarded restore
helper, bounded persistent research jobs, container limits/log rotation, and a
prepared GitHub check workflow. No automatic off-host backup or external alert
destination is configured; CI is not active until the repository is connected.

**Validation:** 102 Python tests and six frontend suites passed. Updated local
packages and the fully pinned release report no known advisories at scan time;
that is not a security guarantee or a production upgrade. A new cloud image build,
Python 3.12/Linux release execution, physical-iPhone end-to-end test, long-running
soak, independent penetration review and cloud deployment remain unverified.

## Capacity and trading limits

The isolated test stored **100,500 synthetic closed trade records** and **100,000
activity records**, verified backup/restore, and served **800 real loopback HTTP
requests** from **16 simulated clients**, using one Gunicorn worker and four
threads, with **zero errors**. The separate overload burst accepted 180 requests
and correctly limited 20. Its simulated proxy client-address setting exists only
in the marked, temporary, read-only fixture; production proxy headers must be
overwritten by Caddy.

This computer (Apple arm64, Python 3.14) measured 984.3 requests/second and a
19.50 ms p95 response time. The test included large cached dashboard responses,
not TLS/WAN, real broker fills, many accounts, market liquidity or Azure B1s
hardware. The SQLite transaction measurement excludes strategy/pricing work and
is not an order-execution benchmark. Original market-data signals and completed
bar rules were not altered to create the synthetic records.

The actual strategy still supports **one open position**, **up to three entries
per day**, **up to five lots where the risk budget permits**, and a **2% per-entry
risk limit**. It cannot responsibly be described as a high-frequency or large
multi-account execution engine. Raising the daily limit or capital requires a
separate strategy/risk evaluation, not merely faster storage. There is no real
broker execution.

SQLite WAL allows concurrent readers while retaining one writer; adding trading
workers is not a scaling solution for this account. See [SQLite's WAL documentation](https://www.sqlite.org/wal.html).
The API controls follow the scoped principles in [OWASP's REST security guidance](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

## Screenshot checklist

| Topic | Assessment | Evidence or limitation |
|---|---|---|
| Load balancing | Not needed at current scope | One shared account, one execution worker; API scaling must be separated from execution before replicas are introduced. |
| Read replicas | Not needed at current scope | One shared account, one execution worker; API scaling must be separated from execution before replicas are introduced. |
| Horizontal vs vertical scaling | Not needed at current scope | One shared account, one execution worker; API scaling must be separated from execution before replicas are introduced. |
| Stateless services | Not needed at current scope | One shared account, one execution worker; API scaling must be separated from execution before replicas are introduced. |
| Rate limiting | Local release tested | Bounded per-address/user limits and 429/Retry-After; bad-key throttling does not lock out a valid account. Permanent account lockouts intentionally avoided. |
| Brute force protection | Local release tested | Bounded per-address/user limits and 429/Retry-After; bad-key throttling does not lock out a valid account. Permanent account lockouts intentionally avoided. |
| Account lockout | Local release tested | Bounded per-address/user limits and 429/Retry-After; bad-key throttling does not lock out a valid account. Permanent account lockouts intentionally avoided. |
| Environment variables | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Secrets management | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Authentication | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Authorization | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Principle of least privilege | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| API keys | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Role-based access control | Existing plus local hardening | Environment hashes, constant-time checks, separate trader/viewer roles, private raw-key files, non-root serving; proxy no longer receives user hashes in prepared Compose. |
| Input validation | Local release tested | Strict empty-object actions, bounded bodies/queries, generic errors, request IDs, correct rejection before effects. |
| Data validation on the server | Local release tested | Strict empty-object actions, bounded bodies/queries, generic errors, request IDs, correct rejection before effects. |
| HTTP status codes | Local release tested | Strict empty-object actions, bounded bodies/queries, generic errors, request IDs, correct rejection before effects. |
| Error handling | Local release tested | Strict empty-object actions, bounded bodies/queries, generic errors, request IDs, correct rejection before effects. |
| Automated testing | Tested | 102 backend tests plus six frontend suites and real loopback HTTP load. No new physical-iPhone end-to-end test or new Azure container build. |
| Unit vs integration vs end-to-end tests | Tested | 102 backend tests plus six frontend suites and real loopback HTTP load. No new physical-iPhone end-to-end test or new Azure container build. |
| Database indexing | Local release tested | Existing primary/unique indexes, transactional additive schema version 1, trigger-maintained complete totals. Preserve account JSON and exact pinned policy; no rewrite to normalize trading state. |
| Database migrations | Local release tested | Existing primary/unique indexes, transactional additive schema version 1, trigger-maintained complete totals. Preserve account JSON and exact pinned policy; no rewrite to normalize trading state. |
| Database normalization | Local release tested | Existing primary/unique indexes, transactional additive schema version 1, trigger-maintained complete totals. Preserve account JSON and exact pinned policy; no rewrite to normalize trading state. |
| Backups | Local release tested; off-host gap | SQLite online backup, integrity check, checksum, startup/hourly copies, bounded 24-generation retention, new-path restore helper and concurrent-write restore tests. Same-VM copies do not protect against VM/disk loss; no automatic off-host destination. |
| Disaster recovery | Local release tested; off-host gap | SQLite online backup, integrity check, checksum, startup/hourly copies, bounded 24-generation retention, new-path restore helper and concurrent-write restore tests. Same-VM copies do not protect against VM/disk loss; no automatic off-host destination. |
| Caching | Local release tested | Single-flight encoded snapshot, five-second TTL, invalidated after accepted controls; account responses remain no-store. |
| Cache invalidation | Local release tested | Single-flight encoded snapshot, five-second TTL, invalidated after accepted controls; account responses remain no-store. |
| CDNs | Existing | Public Sites static frontend delivery. No private account caching or new CDN provisioned. |
| Logging | Local release tested | Structured application events, server-generated request IDs, bounded private operational audit, generic client errors, container log rotation prepared. No credential/body logging. |
| Structured logging | Local release tested | Structured application events, server-generated request IDs, bounded private operational audit, generic client errors, container log rotation prepared. No credential/body logging. |
| Audit logs | Local release tested | Structured application events, server-generated request IDs, bounded private operational audit, generic client errors, container log rotation prepared. No credential/body logging. |
| Error tracking | Local release tested | Structured application events, server-generated request IDs, bounded private operational audit, generic client errors, container log rotation prepared. No credential/body logging. |
| Monitoring | Local release tested; external gap | Public liveness/readiness plus protected worker/feed/backup/disk/RSS/counter diagnostics. No independent off-VM uptime monitor or outbound phone/email notifications configured. |
| Health checks | Local release tested; external gap | Public liveness/readiness plus protected worker/feed/backup/disk/RSS/counter diagnostics. No independent off-VM uptime monitor or outbound phone/email notifications configured. |
| Uptime monitoring | Local release tested; external gap | Public liveness/readiness plus protected worker/feed/backup/disk/RSS/counter diagnostics. No independent off-VM uptime monitor or outbound phone/email notifications configured. |
| Alerting | Local release tested; external gap | Public liveness/readiness plus protected worker/feed/backup/disk/RSS/counter diagnostics. No independent off-VM uptime monitor or outbound phone/email notifications configured. |
| Timeouts | Local release tested | Ten-second socket timeouts, two bounded GET attempts, growing retry delays across successive failures, jitter, per-instrument cooldown after three failures; stale data cannot authorize entries. |
| Exponential backoff | Local release tested | Ten-second socket timeouts, two bounded GET attempts, growing retry delays across successive failures, jitter, per-instrument cooldown after three failures; stale data cannot authorize entries. |
| Circuit breakers | Local release tested | Ten-second socket timeouts, two bounded GET attempts, growing retry delays across successive failures, jitter, per-instrument cooldown after three failures; stale data cannot authorize entries. |
| Idempotency | Local release tested | Durable action claims/replays, pending-action conflict after uncertain failures, one-writer transactions, duplicate-bar entry/exit concurrency tests, process locks. |
| Race conditions | Local release tested | Durable action claims/replays, pending-action conflict after uncertain failures, one-writer transactions, duplicate-bar entry/exit concurrency tests, process locks. |
| Concurrency | Local release tested | Durable action claims/replays, pending-action conflict after uncertain failures, one-writer transactions, duplicate-bar entry/exit concurrency tests, process locks. |
| Reverse proxies | Existing; release config prepared | Caddy HTTPS terminates TLS, API port binds loopback, explicit body/time/header limits. A separate API gateway is unnecessary for this account. New image/Compose not built or deployed this turn. |
| API gateways | Existing; release config prepared | Caddy HTTPS terminates TLS, API port binds loopback, explicit body/time/header limits. A separate API gateway is unnecessary for this account. New image/Compose not built or deployed this turn. |
| Docker | Existing; release config prepared | Caddy HTTPS terminates TLS, API port binds loopback, explicit body/time/header limits. A separate API gateway is unnecessary for this account. New image/Compose not built or deployed this turn. |
| HTTPS / TLS | Existing; release config prepared | Caddy HTTPS terminates TLS, API port binds loopback, explicit body/time/header limits. A separate API gateway is unnecessary for this account. New image/Compose not built or deployed this turn. |
| Encryption in transit | Existing; release config prepared | Caddy HTTPS terminates TLS, API port binds loopback, explicit body/time/header limits. A separate API gateway is unnecessary for this account. New image/Compose not built or deployed this turn. |
| CI/CD | Prepared, not active | Read-only GitHub check workflow, dependency-update config, Dockerfile and Compose. Root is not connected to an active Git checkout; workflows not pushed/run. Independent human review and remote CI remain outstanding. |
| Branching strategies | Prepared, not active | Read-only GitHub check workflow, dependency-update config, Dockerfile and Compose. Root is not connected to an active Git checkout; workflows not pushed/run. Independent human review and remote CI remain outstanding. |
| Code review | Prepared, not active | Read-only GitHub check workflow, dependency-update config, Dockerfile and Compose. Root is not connected to an active Git checkout; workflows not pushed/run. Independent human review and remote CI remain outstanding. |
| Infrastructure as code | Prepared, not active | Read-only GitHub check workflow, dependency-update config, Dockerfile and Compose. Root is not connected to an active Git checkout; workflows not pushed/run. Independent human review and remote CI remain outstanding. |
| Message queues | Existing plus local hardening | One bounded research slot with 20 retained persisted job records; interrupted jobs are not replayed. Trading and backup worker loops are independent of phones. Redis/message broker/cron unnecessary for these loops. |
| Background jobs | Existing plus local hardening | One bounded research slot with 20 retained persisted job records; interrupted jobs are not replayed. Trading and backup worker loops are independent of phones. Redis/message broker/cron unnecessary for these loops. |
| Cron jobs | Existing plus local hardening | One bounded research slot with 20 retained persisted job records; interrupted jobs are not replayed. Trading and backup worker loops are independent of phones. Redis/message broker/cron unnecessary for these loops. |
| Session management | Local release tested; manual lifecycle | Bearer keys stay in app memory, not browser storage; configurable expiration/disable, manual key replacement and restart documented. No refresh-token/session-cookie subsystem or automatic secret manager. |
| Token expiration and refresh | Local release tested; manual lifecycle | Bearer keys stay in app memory, not browser storage; configurable expiration/disable, manual key replacement and restart documented. No refresh-token/session-cookie subsystem or automatic secret manager. |
| Secret rotation | Local release tested; manual lifecycle | Bearer keys stay in app memory, not browser storage; configurable expiration/disable, manual key replacement and restart documented. No refresh-token/session-cookie subsystem or automatic secret manager. |
| Two-factor authentication | Not implemented | Current app uses privately issued high-entropy access keys, not password accounts. These alternative identity features are not prerequisites for this two-person paper deployment; reassess before expanding access or adding real-money execution. |
| Passkeys | Not implemented | Current app uses privately issued high-entropy access keys, not password accounts. These alternative identity features are not prerequisites for this two-person paper deployment; reassess before expanding access or adding real-money execution. |
| Single sign-on (SSO) | Not implemented | Current app uses privately issued high-entropy access keys, not password accounts. These alternative identity features are not prerequisites for this two-person paper deployment; reassess before expanding access or adding real-money execution. |
| Magic links | Not implemented | Current app uses privately issued high-entropy access keys, not password accounts. These alternative identity features are not prerequisites for this two-person paper deployment; reassess before expanding access or adding real-money execution. |
| Password reset flows | Not implemented | Current app uses privately issued high-entropy access keys, not password accounts. These alternative identity features are not prerequisites for this two-person paper deployment; reassess before expanding access or adding real-money execution. |
| SQL injection | Scoped protection tested | Parameterized data values, allowlisted routes/tables, strict request fields and authentication. Both users intentionally share one account; multiple tenants/row-level account isolation are not implemented. |
| Mass assignment | Scoped protection tested | Parameterized data values, allowlisted routes/tables, strict request fields and authentication. Both users intentionally share one account; multiple tenants/row-level account isolation are not implemented. |
| IDOR | Scoped protection tested | Parameterized data values, allowlisted routes/tables, strict request fields and authentication. Both users intentionally share one account; multiple tenants/row-level account isolation are not implemented. |
| Row-level security | Scoped protection tested | Parameterized data values, allowlisted routes/tables, strict request fields and authentication. Both users intentionally share one account; multiple tenants/row-level account isolation are not implemented. |
| XSS (Cross-site scripting) | Existing plus local hardening | Frontend escaping tests, no ambient authentication cookies, exact-origin controls and bearer tokens; API no-store/nosniff/HSTS/frame-denial/CSP headers added. Public frontend CSP not changed or penetration-tested. |
| CSRF | Existing plus local hardening | Frontend escaping tests, no ambient authentication cookies, exact-origin controls and bearer tokens; API no-store/nosniff/HSTS/frame-denial/CSP headers added. Public frontend CSP not changed or penetration-tested. |
| Content Security Policy | Existing plus local hardening | Frontend escaping tests, no ambient authentication cookies, exact-origin controls and bearer tokens; API no-store/nosniff/HSTS/frame-denial/CSP headers added. Public frontend CSP not changed or penetration-tested. |
| Security headers | Existing plus local hardening | Frontend escaping tests, no ambient authentication cookies, exact-origin controls and bearer tokens; API no-store/nosniff/HSTS/frame-denial/CSP headers added. Public frontend CSP not changed or penetration-tested. |
| Clickjacking | Existing plus local hardening | Frontend escaping tests, no ambient authentication cookies, exact-origin controls and bearer tokens; API no-store/nosniff/HSTS/frame-denial/CSP headers added. Public frontend CSP not changed or penetration-tested. |
| Dependency vulnerabilities | Scanned and updated locally | Old local Pillow and pip advisories addressed. Prepared fully pinned/hash-locked release and post-upgrade local environment report zero known advisories. Production packages were not upgraded. |
| Connection pooling | Not needed at current scope | SQLite with short connections, WAL, busy timeout and bounded readers; no database server connection pool or multi-writer throughput promise. |
| Soft deletes | Not needed at current scope | No API deleting/editing trades. Trading events remain persisted; bounded audit/backups have explicit retention, not silent trade deletion. |
| File upload security | No server feature exposed | Report import is browser-only. No server file upload or inbound webhook endpoint was introduced. |
| Webhooks | No server feature exposed | Report import is browser-only. No server file upload or inbound webhook endpoint was introduced. |
| Graceful shutdown | Local release tested/configured | In-flight paper/data work gets a bounded drain; research subprocess termination, executor drain, Gunicorn grace and Compose stop period aligned. Full new-container shutdown not tested on Azure. |
| Distributed tracing | Not needed at current scope | One process and one account use request IDs and structured events. No distributed tracing service. |
| Feature flags | Existing | Auto-start, persisted enabled state, role permissions, optional key expiry and trusted-proxy setting; no paid flag service. |
| Staging environments | Local fixture tested | Marked temporary synthetic database and read-only Gunicorn fixture; no remote staging VM or second account execution worker created. |
| Semantic versioning | Implemented locally | Prepared release 1.1.0, compatible legacy paths, /api/v1 aliases and API.md. Current cloud service remains previous version. |
| API versioning | Implemented locally | Prepared release 1.1.0, compatible legacy paths, /api/v1 aliases and API.md. Current cloud service remains previous version. |
| API documentation | Implemented locally | Prepared release 1.1.0, compatible legacy paths, /api/v1 aliases and API.md. Current cloud service remains previous version. |
| Load testing | Measured locally | 100,500 trade records, 100,000 events, 16 simulated clients, 800 real HTTP requests, no errors; overload burst verifies 429. Detailed timings in results/capacity.json. No Azure throughput SLA, sustained soak or exchange/broker throughput claim. |
| Profiling | Measured locally | 100,500 trade records, 100,000 events, 16 simulated clients, 800 real HTTP requests, no errors; overload burst verifies 429. Detailed timings in results/capacity.json. No Azure throughput SLA, sustained soak or exchange/broker throughput claim. |
| Performance budgets | Measured locally | 100,500 trade records, 100,000 events, 16 simulated clients, 800 real HTTP requests, no errors; overload burst verifies 429. Detailed timings in results/capacity.json. No Azure throughput SLA, sustained soak or exchange/broker throughput claim. |
| Debugging | Engineering process | Regression tests, diagnostics, request IDs, API/recovery instructions and explicit deferred gaps recorded. These are working practices rather than checkboxes or automatic production guarantees. |
| Reading error messages | Engineering process | Regression tests, diagnostics, request IDs, API/recovery instructions and explicit deferred gaps recorded. These are working practices rather than checkboxes or automatic production guarantees. |
| Reading documentation | Engineering process | Regression tests, diagnostics, request IDs, API/recovery instructions and explicit deferred gaps recorded. These are working practices rather than checkboxes or automatic production guarantees. |
| Technical debt | Engineering process | Regression tests, diagnostics, request IDs, API/recovery instructions and explicit deferred gaps recorded. These are working practices rather than checkboxes or automatic production guarantees. |
| Time zones | Existing and exercised | Timezone-aware completed bars and IST session rules; UTC operational records and UTF-8 JSON. Tests include same-day exits, historical catch-up and future-data exclusion. |
| Character encoding | Existing and exercised | Timezone-aware completed bars and IST session rules; UTC operational records and UTF-8 JSON. Tests include same-day exits, historical catch-up and future-data exclusion. |
| Async / await | Appropriate current implementation | Browser uses async requests; server uses bounded threads, a single executor slot and serialized account writes. Async syntax is not required to make this workload correct. |
| Memory leaks | Partly bounded; long soak not performed | Snapshot cache, rate-limit keys, request records, audit rows, job records, history windows and log sizes are bounded. Account history is intentionally retained; 1 GiB disk-space alert added. Long-duration memory-leak testing remains outstanding. |
| Cost monitoring | Existing spending protection; not rechecked | Previously verified Azure student spending limit On. No new paid resources created. Live credit/cost data could not be rechecked after Azure access was deferred; no automated cost monitor configured. |
| Data privacy (GDPR) | Scoped measures; no compliance claim | Private account API, no-store, raw keys kept private, no new external telemetry destination. No legal GDPR compliance certification or tenant data-management system asserted. |
| Accessibility | Existing tests; limited verification | iPhone Home Screen metadata, responsive navigation, form labels and rendered-view checks pass. No new physical-device, full keyboard/screen-reader or WCAG audit. |
| Mobile responsiveness | Existing tests; limited verification | iPhone Home Screen metadata, responsive navigation, form labels and rendered-view checks pass. No new physical-device, full keyboard/screen-reader or WCAG audit. |
| SSRF | Scoped defenses tested | No user-supplied backend URL/path/command endpoints; market-data host and redirects allowlisted, static subprocess argument list, file paths fixed. No broad penetration-test claim. |
| Open redirects | Scoped defenses tested | No user-supplied backend URL/path/command endpoints; market-data host and redirects allowlisted, static subprocess argument list, file paths fixed. No broad penetration-test claim. |
| Path traversal | Scoped defenses tested | No user-supplied backend URL/path/command endpoints; market-data host and redirects allowlisted, static subprocess argument list, file paths fixed. No broad penetration-test claim. |
| Command injection | Scoped defenses tested | No user-supplied backend URL/path/command endpoints; market-data host and redirects allowlisted, static subprocess argument list, file paths fixed. No broad penetration-test claim. |
| Cookie flags (HttpOnly, Secure, SameSite) | Not applicable to current authentication | No authentication cookies are used. Bearer keys are sent in Authorization; cookie flags would matter if cookie sessions are introduced. |
| Encryption at rest | Partly existing; at-rest verification gap | Random API keys are SHA256-hashed, not reversibly encrypted; password hashing/salting is inapplicable because no user passwords exist. Local backups use restrictive permissions, not application encryption. Azure disk encryption was not reverified this turn. |
| Hashing vs encryption | Partly existing; at-rest verification gap | Random API keys are SHA256-hashed, not reversibly encrypted; password hashing/salting is inapplicable because no user passwords exist. Local backups use restrictive permissions, not application encryption. Azure disk encryption was not reverified this turn. |
| Salting | Partly existing; at-rest verification gap | Random API keys are SHA256-hashed, not reversibly encrypted; password hashing/salting is inapplicable because no user passwords exist. Local backups use restrictive permissions, not application encryption. Azure disk encryption was not reverified this turn. |
| Penetration testing (partially visible final screenshot line) | Not performed as a comprehensive assessment | Focused API security/regression checks only; not a formal third-party penetration test. |

## Review and reproduce

- `API.md` documents compatibility, history windows, authorization, idempotency and rate limits.
- `results/capacity.json` contains the measured hardware, request counts, latencies and explicit exclusions.
- `results/dependency-audit-local.json` is the initial scan; `dependency-audit-local-after.json` and `dependency-audit-release.json` are the completed post-fix scans.
- `tools/capacity_check.py` creates a marked temporary fixture and starts no trading worker. The live account is never a load-test target.
- `tests/test_reliability.py` and `tests/test_concurrency.py` cover malformed inputs, privilege checks, rate recovery, stale worker readiness, duplicate requests/bars, rollback, paging and backups during writes.
- `deployment/restore-account.py` requires a trusted checksum and a new destination; it refuses to overwrite an account.
- `.github/workflows/ci.yml` and `.github/dependabot.yml` are prepared files, not active remote workflows.

For future deployment: back up the current cloud database and exact policy first,
verify the new container on Linux, stop the one execution worker during cutover,
retain the persistent `/state` disk and existing control/key settings, and run the
read-only `deployment/verify-cloud.py --expect-ready` check. The additive migration
must preserve the pinned fingerprint. Compare account totals and trade identities
before/after, then verify restart recovery. Never upload the local migration marker
or replace the hosted database with the older laptop copy. No deployment was
performed during this audit.
