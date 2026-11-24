# Working together on Last of Our League

The shared source repository is https://github.com/Klu-150/LOL-BOT. Both developers
should edit a Git clone of this repository. A downloaded ZIP does not synchronize
with GitHub. Saving a file changes only that laptop until it is committed and pushed.

## Start work

```sh
git clone git@github.com:Klu-150/LOL-BOT.git
cd LOL-BOT
git switch main
git pull --ff-only origin main
git switch -c feature/my-change
```

For an existing clone, omit clone/cd. Finish or stash unrelated edits before
switching branches. Each person uses a separate feature branch; agree on ownership
before editing the same file. The repository owner must grant the friend collaborator
access through GitHub if they do not already have write access.

## Test and share

Run the checks in `.github/workflows/ci.yml`. For dashboard-only changes:

```sh
node dashboard/build-release.mjs
node dashboard/terminal-analytics-checks.mjs
node dashboard/render-checks.mjs
node dashboard/release-checks.mjs
git add dashboard/dist/app.js dashboard/dist/terminal-theme.css
git diff --cached
git commit -m "Describe the change"
git push -u origin feature/my-change
```

Stage all intended source/build/test files for your change; the paths above are an
example, not a full release manifest. Open a pull request on GitHub, wait for CI,
review and merge. Before the next change, pull the merged `main`. If Git reports a
conflict, resolve it and rerun checks. Never force-push shared `main`.

## Data and deployment

Keep the committed dashboard data as the empty demo. Never commit access keys,
`.env` files, paper databases, account exports, backups, personal reports, vendor
archives or cloud inventory. GitHub holds source; the engine owns private state.
Device notes, layouts and unsaved strategy drafts are not repository changes.

GitHub push does not by itself update the running Azure engine or the Sites
website. Publish the tested static build using the retained Sites workflow. Engine
changes require the separate guarded deployment process. UI changes should preserve
API compatibility, current sign-ins, the running paper account and pinned policy.

During Codex-assisted work, request that completed changes be committed and pushed.
The agent must fetch first, inspect the staged diff and verify the push result.
It should report the commit/link and distinguish source push from deployment.
