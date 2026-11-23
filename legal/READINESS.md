# Privacy and usage checklist — 23 November 2026

This maps the user's 15-item screenshot to the actual invited, shared-account paper
workspace. The screenshot is a checklist, not legal authority. Technical controls
and draft operational procedures do not establish legal compliance. No agreement
has been accepted on the operator's behalf. No customer billing or marketing added.

| Item | Implementation / evidence | Remaining operator decision |
| --- | --- | --- |
| Privacy policy | Public `privacy.html`: data, purpose, visibility, recipients, retention, rights, security and device controls | Confirm operator legal identity, country, public contact and applicable notice/rights wording before wider customer use |
| Terms and conditions | Current usage rules explain authorized access, one shared virtual account, modelled fills, service limits and no payment | Legal review and approval of an actual contract, governing law and appropriate remedies before commercial launch; no fabricated click-through acceptance |
| GDPR compliance | Applicability explicitly unresolved; technical safeguards do not claim certification | Assess UK/EU territorial scope, roles, exemptions, registration/representation and rights duties, as applicable; also assess Indian requirements |
| Cookie consent | App has no ad/analytics SDK or app-set tracking cookie; device storage is disclosed and manageable | Review host-controlled cookies and classifications; do not add optional tracking without required opt-in and withdrawal controls |
| Legal basis | Purposes documented: requested features, access, security, shared research history and recovery | Record applicable basis per purpose/jurisdiction; do not treat a privacy-page visit as consent or invent a contract basis |
| Marketing consent | No marketing list, marketing sender or promotional subscription system | Separate freely chosen opt-in, unsubscribe and suppression process if introduced; operational alerts are not marketing opt-in |
| Data deletion | Confirmed, category-scoped device deletion; no cloud destructive endpoint | Verify and action applicable server rights requests without deleting another user's records; observe backup expiration and restoration suppression |
| Retention | Actual bounds documented below | Approve time-based retention for account history/audits if required; existing record-count bounds are not time-based erasure |
| Processing agreements | Azure/Sites/data-provider register below | Identify controller/processors; review applicable DPAs, subprocessors, transfers and student/hosting terms. No DPA was signed or presumed accepted |
| Third-party disclosure | Public provider, network, region and shared-user disclosures | Confirm provider-side retention, exact legal service entities, transfer mechanisms and whether external data redistribution is permitted |
| Security | Existing roles/TLS/CORS/rate limits/private backup/restore/email monitoring; scoped browser controls | Independent security and OS/container review remain outstanding |
| Breach procedure | `legal/INCIDENT_RESPONSE.md` | Name accountable operator and backup, assess legal notification duties and run a tabletop exercise |
| Intellectual property | No new licence assigned to app, brand or dissertation; original documents untouched | Confirm ownership, university rules and rights to code, branding, datasets and any commercial reuse |
| Open-source licences | 19 exact hash-locked application/bootstrap wheels inventoried; bundled licence/notice texts preserved in public download | Review obligations before distribution, including bundled components; OS/container/services excluded and still require review |
| Payments/subscriptions | No checkout, user fee, recurring customer charge or refund flow | Introduce accurate pricing, tax, cancellation/renewal/refund terms before charging; hosting costs are the owner's separate account commitment |

## Actual retention and data map

- `league_strategy_library_v1`: browser strategy drafts/test summaries, up to 50;
  until user removal. `league_tools_v1`: notes (up to 500), alerts (up to 30), recent
  alert activity (up to 100); until removal or bounded replacement. These are not
  sent to the cloud automatically. Explicit exports may contain private content.
- `league_theme_v2` and `league_cloud_server`: requested display/connection
  preferences, until removal. Theme initialization no longer writes a default
  preference merely because a page was opened.
- Cloud credentials: existing per-user configuration; browser key is page-memory
  only. Account records are shared between the authorized users, not tenant-isolated.
- Cloud paper history: retained for continuity with no age-based purge. Current
  account cannot be reset/deleted casually while managing an open position.
- Audit DB: latest 20,000 events, containing actor/action/status/request ID/time.
  This is a count bound, not a retention duration. Idempotency completed requests
  are cleaned after seven days upon subsequent request claims; pending records can
  remain. Neither is a guaranteed deletion at an exact wall-clock time.
- Local backup: latest 24 snapshots. Off-server: delete after seven days plus
  seven-day soft deletion. Recovery archives include paper/operations snapshots
  and manifests, not credential/environment files. Restore must reapply outstanding
  erasure decisions before returning data to service.
- Docker engine/gateway logs: configured 3 x 10 MB per service, not an age bound.
  Caddy application config has no access-log directive. Provider/host logs may differ.
- Azure monitoring workspace configured for 30-day retention. Alert delivery
  processes the designated recipient email; this address is not published in the
  public notice. Student account identity/billing records are provider-managed.

## Provider and rights-request register

| Provider / recipient | Purpose and data | Review status |
| --- | --- | --- |
| ChatGPT Sites hosting | Static assets/public research snapshot, browser requests/network metadata; platform security cookies may be separate | Hosting agreement, provider logging/retention, legal entity and transfer assessment pending |
| Microsoft Azure | VM/private paper records, identity, Blob recovery, monitoring events and operational alert recipient | Existing student subscription; regional storage plus multi-region probes; applicable DPA/subprocessors/transfers still require operator review |
| Public market-data feed | Underlying/VIX research observations and server request metadata | Check current provider terms and commercial/redistribution rights; no licensed live options feed connected |
| Authorized workspace users | One shared virtual account, orders, strategy activity | Existing roles only; no expanded audience or new access grant |

For server access/correction/deletion requests: record request and verified identity,
scope, applicable legal basis, response deadline and outcome in a private register.
Use the existing access channel; never ask for the user's private key. Verify identity
proportionately without collecting unnecessary identity documents. Export only that
user's eligible records through a secure authorized channel, protect the other user's
shared data, and explain any lawful restriction. Suspend access only through an
authorized process; do not delete or reset the trading ledger through browser controls.
Record erasure decisions so old backups do not silently reintroduce erased data.
Do not claim a completed request until server data, retained copies and exceptions
have actually been assessed. No real user data has been deleted by this change.

## Legal sources checked

- [ICO: UK GDPR applicability](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/personal-information-what-is-it/who-does-the-uk-gdpr-apply-to): scope depends on establishment/activities; do not infer it just from the market traded.
- [ICO: cookies and similar technologies](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/): local storage is also covered; essential-use exemptions require an actual assessment. Host technology is separate from app source.
- [MeitY: DPDP rules](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025-2): staged commencement and applicable duties must be checked against current notifications, not a social-media checklist.

These sources inform the implementation; they do not constitute an independent
legal opinion or resolve the operator's jurisdiction. This checklist remains open
for the explicitly identified owner/legal tasks.
