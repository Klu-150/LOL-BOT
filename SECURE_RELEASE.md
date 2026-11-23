# Static release protection — 23 November 2026

## Assessment of the shared BLA post

Reviewed `qybaihe/bla` at commit
`2b7a7c4f2ac69623542c3ba98e22695855e26449` (package 3.5.7), including
the README, package metadata, empirical report and relevant JavaScript hardening,
runtime-shield and decoy generators. This was a targeted source review, not a full
dependency audit. No BLA package, setup integration or third-party code was executed.

The post is incomplete as release guidance. The repository currently says build
first, harden the build, explicitly promote the staged artifacts, then test the
promoted build. Rebuilding afterwards can replace the protected output. Its verify
command checks structural protection, not application behaviour. The project's
empirical table measures particular REA analyzer paths/default budgets, with several
budgets adjustable by the caller, and does not establish protection against all
reverse engineers or Ghidra/Frida. Its 14-target showcase and measured analysis
results should not be conflated with 14 successful real-world cloning preventions.

The reviewed JavaScript code generates decoy state/functions and runtime diagnostic
objects, including inspector/WebDriver observations and synthetic attestation labels.
The default harden intensity is `bankrupt`; the project itself warns about output
growth and the need for application testing. These are obfuscation/analysis-friction
features, not authentication, encrypted secret storage or a confidentiality boundary.
They are not introduced into this trading dashboard. Existing application tests and
clear operational diagnostics are more useful here than obscuring them with decoys.

## Changes applied

- The Sites hosting manifest now deploys only `dashboard/build`, a separate static
  release tree. Editable/generated working inputs remain in `dashboard/dist`; they
  are not the published directory.
- `node dashboard/build-release.mjs` fingerprints browser modules/styles and copies
  only required HTML, static resources, research JSON, licence notices, four icons,
  the service worker and hashed assets. Duplicate unversioned source modules/styles
  are excluded. There are no new external JavaScript dependencies or install scripts.
- The build fails on unapproved paths, symlinks/non-regular files, missing entries,
  incorrect asset hashes, unresolved local imports/worker URLs, oversize artifacts,
  source-map references or embedded source contents, common credential patterns,
  developer home paths, or any existing local access-key literal. The two known
  keys are read privately for comparison only; no values are logged or published.
- `dashboard/release-audit.json` records names, byte sizes and SHA256s without keys.
  It is source-side evidence, not part of the public artifact. Pattern scanning has
  false negatives and is not proof that all sensitive information is absent.
- `node dashboard/release-checks.mjs` exercises forbidden files, credentials, source
  maps, symlinks, tampering and missing entries, then imports the actual emitted
  modules and checks backtest, privacy and connection-validation parity. The existing
  ten dashboard suites remain applicable. Prepared CI includes privacy and release
  checks; a prepared workflow is not proof an external CI service is active.

## Operating procedure

1. Edit working inputs; run the application suites appropriate to the change.
2. Run `node dashboard/build-release.mjs`, then `node dashboard/release-checks.mjs`.
3. Preview **build**, not dist. Check the app, imports, research worker, privacy
   controls and connection permissions. Publish only the exact checked artifact via
   the Sites source helper with the committed `static.directory` set to `build`.
4. Retain the saved version/commit and deployment result. Do not edit/rebuild after
   packaging and before saving the version. Any later rebuild requires new checks.

On macOS, invoke the Sites source helper with `COPYFILE_DISABLE=1` to exclude AppleDouble
extended-attribute sidecars. The helper normalizes the static archive layout to `dist`;
this does not publish the working-input directory. Before saving/publishing, run
`python3 tools/check_site_archive.py /absolute/path/to/archive.tar.gz`. This checks
the normalized Site identity, exact file inventory, hashes and absence of sidecars,
links, private/extra paths and duplicate entries against the checked build audit.

The guarded cloud engine, account, policy, roles and private backups were not altered
or restarted for this static release change. No transformation was applied to the
live SQLite ledger or Python execution logic.

## Remaining limits

Every browser-executed algorithm, model parameter and downloaded research dataset
can be inspected or copied by its recipient, even in a minified/obfuscated build.
The strategy workshop intentionally runs modelled backtests in the browser; those
rules remain public. The authoritative account/order/risk worker stays on the
authenticated server. Keeping a future proprietary research algorithm private would
require moving that computation to an authenticated backend, with suitable access
and usage controls, rather than relying on decoy payloads. UI imitation cannot be
prevented by these build checks. Older already-downloaded releases cannot be recalled.

## Primary sources

- [BLA README at reviewed commit](https://github.com/qybaihe/bla/blob/2b7a7c4f2ac69623542c3ba98e22695855e26449/README.md)
- [BLA empirical REA validation](https://github.com/qybaihe/bla/blob/2b7a7c4f2ac69623542c3ba98e22695855e26449/docs/redteam/empirical-rea-validation.md)
- [Reviewed runtime shield](https://github.com/qybaihe/bla/blob/2b7a7c4f2ac69623542c3ba98e22695855e26449/src/shields/runtime/runtime-shield.ts)
- [OWASP key management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
