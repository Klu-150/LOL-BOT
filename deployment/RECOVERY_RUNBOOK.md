# Paper recovery and monitoring

Release 1.2.1 is deployed on the existing VM. The account and pinned strategy were
preserved. Administration uses the existing private Tailscale SSH route; public SSH
remains closed. The student spending limit remains On.

## Backups

- Local snapshot job: hourly, verified SQLite snapshots under
  `/srv/league/state/paper/backups`.
- Off-server job: `league-offhost-backup.timer`, hourly at minute 10 UTC with up to
  30 seconds jitter. `league-offhost-backup.service` invokes the snapshot uploader
  as the unprivileged application user.
- Destination: private `paper-recovery` container in `leaguebackupdedf75`, India
  South Central. No anonymous Blob access or shared storage keys; the VM's managed
  identity has container-scoped Blob Data Contributor access. Azure encrypts the
  storage at rest; uploads/downloads require HTTPS.
- Object prefix: `accounts/YYYY/MM/DD/`. Each archive contains only the paper and
  operations database snapshots and their checksum manifest. It excludes access keys,
  the environment file and unrelated documents. No account backup is copied to a laptop.
- Each job checks the original snapshot hashes and SQLite integrity, uploads, downloads,
  compares the archive SHA256 and validates an isolated database restore. The status
  file reports success only after these steps complete. A failed job or a success older
  than 90 minutes degrades readiness and reaches the external monitor.
- Lifecycle deletion after seven days, plus seven-day soft delete/version retention.
  The job refuses snapshots above its 64 MiB aggregate bound. Current archives are
  about 23 KiB. This is protection against VM/disk loss, not loss of the Azure account,
  subscription, region, all source copies or all authorized administrators.

On the VM, inspect `systemctl status league-offhost-backup.timer` and private
`journalctl -u league-offhost-backup.service`. Operational API `/api/operations`
exposes `offhost_backup`; the website's Risk & alerts page displays it after sign-in.

## Recovery procedure

Use a separate recovery directory on a trusted replacement VM. Do not restore over a
running account. Ensure the old engine cannot resume and create duplicate processing.
Rebuild the corresponding pinned source version, download a selected archive with an
authorized Blob identity, and compare its recorded archive checksum when available.
Call `offhost_backup.verify_restore(payload)` before extracting its verified, flat
members into the new private directory. Check the manifest hashes again.

Use `deployment/restore-account.py` to copy the verified account snapshot to a NEW
path. Supply the snapshot SHA256 from the manifest. Verify account totals, trade/event
history, policy fingerprint and open-position state before manually promoting the
restored path. Recreate access configuration and private keys through the normal
credential procedure; credential files are deliberately not present in this archive.
Start only one execution worker. Re-enable backup/readiness checks before entries.

A round-trip restore into an isolated temporary directory has passed. A full recovery
on a separate replacement VM remains an outstanding disaster-recovery drill.

## External monitoring

`league-paper-readiness` is a free URL ping test, every five minutes from East Asia,
Southeast Asia, North Europe, West Europe and East US. It checks the public `/readyz`
endpoint, which reveals only ready/degraded and paper mode. No trading key or account
data is given to the probes. `league-paper-unavailable` evaluates every minute and
notifies `league-paper-email` when three of the five locations fail. Normal ingestion,
retry and evaluation delays mean notification is not instantaneous.

The manual action-group test API is unavailable on this free subscription. A temporary
activity-event rule produced real alerts instead; Azure recorded Fired conditions and
the recipient confirmed receiving the named alert. The temporary rule and test tag
were removed. The permanent readiness alert remains enabled. A later maintenance
window can test the availability failure path itself; the bot was not deliberately
stopped just to generate an alert.

URL ping tests retire on 30 September 2028. Migrate before then. They are distinct from
paid Standard tests. Storage, log ingestion and alert usage can consume student credit;
the workspace daily quota is 0.023 GB. A quota is not a universal billing cap.

## Research job

`league-volatility-shadow.timer` runs at 16:00 IST Monday–Friday. The job uses a
separate, read-only container with no network, no authentication credentials and no
paper-account mount, limited to 0.5 CPU and 256 MiB. Only the observed Nifty CSV is
mounted read-only; only the research output directory is writable. Results remain
research-only and never become order instructions. Exchange holidays can produce a
repeat evaluation of the same saved bars; this is not a new trade or forward signal.

## 24 November 2026 — application rehearsal and observation automation

Release 1.3.2 adds `league-recovery-drill.timer` (Sunday 04:00 IST) and
`league-soak.timer` (every five minutes). Both use the existing VM. The off-server
upload service now takes a fresh snapshot immediately before its hourly upload,
avoiding drift between the independently scheduled local and off-server jobs.
Local retention remains the latest 24 manifests; Blob lifecycle/soft-delete
retention is unchanged. Recovery bounds are now 512 MiB raw and 64 MiB compressed,
with streaming hashes/extraction and mandatory allowlists/integrity checks.

The rehearsal downloads the actual private remote archive and restores to a NEW,
marked directory. A separate read-only, no-network, unprivileged container boots
both ledgers with entries disabled, no real credentials and no published ports.
It verifies policy hashes, private dashboard access, viewer restrictions and exact
account preservation. On success its temporary account copy is removed. A private
allowlisted summary remains at `paper/recovery-drill.json`; a failed attempt writes
`paper/recovery-drill-error.json` and keeps its marked private copy for diagnosis.
No recovery data leaves the VM. A successful container drill does not test physical
replacement-VM provisioning or loss of the Azure subscription/region.

`paper/recovery-drill-required` and `paper/soak-required` enable corresponding
readiness checks. A new failed drill invalidates the previous successful result;
recovery evidence is version-bound and expires after eight days. Soak observations
persist across app restarts, are capped at 10,080 rows, and never interpret missing
observations as uptime. Seven continuous days with required coverage are a minimum
observation gate, not a claim of a month of market execution or profitability.

Use `systemctl status league-recovery-drill.service league-soak.service` and private
journals for failures. The API exposes safe summaries only. The guarded installer
runs required recovery/observer checks after a new image starts and before its
readiness check, retaining rollback on failure. It captures private failure logs.
