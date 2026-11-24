# Security and privacy incident procedure

Scope: existing shared paper engine, static Site, backups, credentials and user data.
Primary operator: Venkata Madhan Kanakala, India; kvenkatamadhan734@gmail.com. A backup incident contact has not been designated.
Operational monitoring email is private and is not automatically a public privacy
contact. No breach has been asserted or notification sent as part of this work.

1. **Triage and record.** Note UTC and IST time, reporter, affected component,
   symptoms and whether this is an availability incident, suspected compromise or
   confirmed personal-data breach. An outage alert alone does not establish a breach.
   Use a private incident log; exclude full keys, identity documents and unrelated data.
2. **Contain proportionately.** Restrict affected access/routes using the existing
   authorized admin process. If appropriate pause new entries while preserving exit
   management. Paper positions may still need valid observations. Do not restart,
   wipe the ledger, delete logs or destroy evidence merely to clear an alert.
   Credential changes require the owner to complete the appropriate secure flow.
3. **Preserve evidence.** Capture relevant request IDs, bounded log excerpts,
   configuration/version fingerprints and affected time range to private storage.
   Preserve necessary evidence before routine retention removes it. Record access to
   the evidence and the reason/retention limit for the exceptional copy. Do not export
   the shared account database to a laptop without specific authorization.
4. **Assess impact and legal duties.** Determine data categories, affected people,
   recipients, likely consequences, encryption/credential status and whether data was
   accessed or exfiltrated. Establish applicable jurisdictions and statutory clocks
   from authoritative current guidance. Assess regulator, contractual and affected-user
   notifications, including any applicable Indian/CERT-In or UK/EU obligations.
   Get appropriate legal support; do not wait for certainty if an applicable clock runs.
5. **Communicate through verified channels.** Owner approves accurate, necessary
   notices stating what happened, affected data, containment, recommended actions and
   a contact. Do not disclose another user's records or exposed keys. Marketing consent
   is not incident-notice consent. No automatic external message is authorized by this
   runbook alone.
6. **Recover and validate.** Patch the cause, review access and rotate affected secrets
   through the authorized owner flow. Restore only a verified private snapshot in a
   separate path; reapply erasure restrictions. Check the ledger, policy, readiness,
   external monitoring and backup integrity before resuming entries. Keep one worker.
7. **Review and close.** Record decisions, notifications, evidence, timeline and
   prevention work. Define evidence disposal and follow-up ownership. Test this
   procedure with a non-destructive tabletop exercise before claiming it is proven.

Technical support: `deployment/RECOVERY_RUNBOOK.md`. A separate replacement-VM
recovery drill and an independent security review remain outstanding.
