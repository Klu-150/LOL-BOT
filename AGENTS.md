# Shared repository workflow

The user wants completed source changes synchronized to Klu-150/LOL-BOT so both
developers can collaborate. Fetch the destination branch before editing/syncing,
preserve other developers' work, test the change, inspect the staged diff, commit
and push completed authorized source changes, and verify the remote commit.
Never force-push shared branches. Stop and report unresolved merge/auth blockers.

If this workspace is an exported copy without `.git`, use a clean Git checkout of
the shared repository for the reviewed commit. Copy only intended source changes.
Preserve its sanitized demo data and exclusions. Never synchronize account data,
credentials, private reports, backups, vendor ZIPs, runtime files or unrelated edits.

Read COLLABORATION.md for the two-developer workflow. A Git push is distinct from
website publication and engine deployment; report each status accurately. Keep
automatic trading in paper mode and preserve the running account and pinned policy.
