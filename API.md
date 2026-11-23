# Paper engine API 1.1

This is the prepared local release. The deployed Azure service is still the
previous release because the user deferred Azure access on 20 November 2026.
Existing `/api/...` URLs are preserved. `/api/v1/...` aliases expose the same API.
No endpoint places broker orders, uploads files, runs supplied commands or fetches
user-supplied URLs. All users currently share one paper account.

Use HTTPS with `Authorization: Bearer username.private_key`. Keys are not cookies
or URL parameters. Server configuration stores SHA256 hashes. Optional per-user
`expires_at` must contain a timezone; `disabled: true` revokes a key. Rotation is
manual: generate a new private key, update that user's configured hash, restart
the service, and distribute the replacement privately. Existing keys are not
silently rotated, expired, or revoked by this release. MFA/SSO is not implemented.

| Method and route | Access | Response |
|---|---|---|
| GET `/healthz` | Public | Process liveness only. Does not claim the worker or feed is healthy. |
| GET `/readyz` | Public | Generic ready/degraded, HTTP 200/503. No private account details. |
| GET `/api/v1/health` | Authenticated | User role, control permission, paper worker status, operations, version. |
| GET `/api/v1/status` | Authenticated | Worker, latest research jobs, operations. |
| GET `/api/v1/dashboard` | Authenticated | Reports, current account totals, recent trades and activity. |
| GET `/api/v1/history/trades?limit=50&cursor=...` | Authenticated | Persisted raw closed trades, newest first; cursor is the last trade ID. |
| GET `/api/v1/history/events?limit=50&cursor=...` | Authenticated | Persisted activity, newest first; cursor is the last timestamp. |
| GET `/api/v1/operations` | Authenticated | Worker/data alerts, backup status, free disk, peak process RSS, feed circuits, counters. |
| POST `/api/v1/automation/start` | Trader | Persist enabled state and start paper entry checks. |
| POST `/api/v1/automation/pause` | Trader | Pause new entries; exit management continues. |
| POST `/api/v1/backtest/run` | Trader | HTTP 202; one research job at a time, returning an existing running job rather than queueing duplicates. |

POST requests require `Content-Type: application/json` and an empty object `{}`.
Malformed JSON, extra fields, negative/oversized lengths, invalid pagination and
unknown methods/routes are rejected before effects. History limit is 1–200.
Use the returned `next_cursor` unchanged until it is null; avoid offset paging.
Dashboard snapshots include up to 200 closed trades and 1,000 recent activity
records. Lifetime trade count and net closed P&L use database totals and remain
complete. Older rows remain in the ledger and are accessible through history APIs.

Supply a unique `Idempotency-Key` (8–128 letters/digits/underscores/hyphens) for each
new action. A completed action replays its stored result without repeating the
effect, including after restart. Reusing it for another action returns 409.
A crash leaving a pending record also returns 409: inspect status instead of
blindly replaying an uncertain action. Without a client key, a request gets its
own unique action record; the server cannot associate a later retry with it.
Completed records expire after seven days; unresolved records need operator review.
This does not promise exactly-once broker execution. There is no broker integration.

Rate limits per 60-second window: 240 ingress requests per client address, 15
failed authentications per address, 180 authenticated requests per user, 10 control
requests per user, and 120 preflights per address. Valid keys remain usable when
bad-key attempts are throttled. HTTP 429 includes Retry-After. The prepared Caddy
configuration overwrites X-League-Client-IP; trust that header only behind that
proxy with the application port restricted to loopback. Arbitrary forwarded
headers are ignored by default.

Dashboard JSON is built once per five-second cache window; concurrent readers
share that build. Successful control requests invalidate the cache. This is
server-side computation caching. Responses are `no-store`; browsers and service
workers must not persist account data or credentials. Do not retry uncertain POSTs
automatically. X-Request-ID is a server-generated identifier for error investigation.

The worker heartbeat is checked separately from web-server liveness. Readiness
reports stale/missing heartbeat, failed feed, unresolved square-off data, stopped
worker, failed backup, and less than 1 GiB free disk. Historical data is not treated
as live just because the HTTP server responds. Backup and audit records stay on
the same VM unless separately exported. No push/email alert destination is set.

Gunicorn must run one worker, four threads. A process/file lock prevents a second
worker on the same account. Do not add trading replicas to a load balancer.
