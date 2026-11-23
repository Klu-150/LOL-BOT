# Last of Our League: hosted paper trading

The dashboard is [available here](https://nifty-research-terminal.nearbydrape.chatgpt.site/#mobile).
The engine runs on an Azure for Students Linux VM independently of the laptop
and phone. All trades use virtual money and modelled option fills; there is no
broker execution.

## Sign in on iPhone

1. Open the dashboard in Safari and choose the App tab. The engine address is
   already filled in.
2. Use username **madhan** and the private key in the local
   `paper/cloud-access/owner-access.html` file. Tap **Connect paper engine**.
   Confirm **Hosted engine connected** before relying on displayed activity.
3. Use Safari Share → Add to Home Screen, enabling Open as Web App if shown.
   Signing in may be required after reopening the app; closing it does not pause
   the server.

The owner's key can start/pause paper entries and run backtests. Share only
`paper/cloud-access/friend-access.html` with the friend; that key is view-only.
Never publish either access file, the private JSON, SSH key or server environment.

## Automatic operation

The server checks every 60 seconds. Its unchanged strategy policy uses completed
market bars to choose directional spreads, an iron condor, or no trade.
Entries are permitted 09:45–14:30 IST, subject to triggers, data and risk filters.
Positions target a same-day square-off at 15:15 IST when completed data is available.
Turning off the laptop, closing the phone app or disconnecting the phone does not
stop the hosted engine. The phone needs internet to view/control it.

Public Yahoo bars and modelled options prices do not represent exchange-confirmed
option orders. Feed failures prevent new entries; exits also depend on available
observations. This deployment is paper research and has no demonstrated profit edge.

## Hosting and recovery

- Resource group: `rg-last-of-our-league`, region `indiasouthcentral`.
- VM: `league-engine`, Ubuntu 22.04, Standard_B1s, persistent 32 GB OS disk.
- Backend: `https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com`.
- Docker Compose in `/srv/league` runs one Gunicorn worker and a Caddy HTTPS gateway.
- Account, data, reports and enabled state persist under `/srv/league/state`.
- Restart policy: `unless-stopped`; Docker starts on VM boot. The service is not
  configured to sleep because no browser is open.
- SSH is restricted to the setup computer's internet address. HTTP/HTTPS are public;
  the raw engine port 8765 is bound to loopback. API access requires individual keys.
- The local migration marker prevents the old launcher/automatic runner from
  trading the same account again. Do not remove it while the hosted engine runs.

Existing account and exact pinned policy were migrated. A stopped local session
was recovered retrospectively with its original rules and no new entries before
migration; the historical 16 November close was not a real-time execution.

The user's budget is free hosting only. The Azure student subscription uses
eligible service allowances and US$100 credit; spending protection remains On.
Storage/public-IP usage can consume that credit. Do not remove protection or
upgrade to paid billing. The engine stops if credit expires or is exhausted.
See [Microsoft's student offer](https://azure.microsoft.com/en-us/free/students/)
and [spending-limit explanation](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit).

## Maintenance

`deployment/package-engine.py` creates an allowlisted source archive with the
required event calendar and trading plan, excluding live account files and keys.
Never reset an account fingerprint to bypass a policy mismatch. Build and verify
policy changes on a separate research account; keep one runner per account.
`deployment/verify-cloud.py` checks HTTPS, authorization, browser origin controls,
view-only access and the migrated account. Its account totals intentionally assert
the migration baseline; update those checks deliberately after subsequent trades.
Deployment progress and verification evidence are recorded in `deployment/status.json`.
