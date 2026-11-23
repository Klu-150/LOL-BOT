# Source repository handoff

This repository contains the bot source, dashboard (working inputs and checked static build), tests, research modules, example strategies, historical underlying market data, and deployment templates. It supports paper trading only.

Private access keys, paper databases/backups, local environments, generated account/history/research reports, temporary dissertation extracts, cloud account inventory, nested Git metadata and dependency wheels are excluded. The original dissertation files are not distributed here. Research findings remain documented.

Recreate the Python environment using the hash-locked cloud requirements. On the intended Linux/Python 3.12 deployment target, download wheels with `python -m pip download --only-binary=:all: --require-hashes -r requirements-bootstrap.lock -r requirements-cloud.lock -d deployment/wheelhouse` before the offline Docker build. Do not commit that cache.

Run `python -m pytest -q` and the dashboard checks in `.github/workflows/ci.yml`. Build the static release with `node dashboard/build-release.mjs`, then `node dashboard/release-checks.mjs`. Use the Sites workflow for the existing hosted Site; this GitHub upload does not reconfigure the running VM or website.

Set your own deployment environment and credentials. `LEAGUE_VM_HOST` is required for a guarded VM upgrade. Read PRODUCTION_READINESS.md, SECURE_RELEASE.md and legal/READINESS.md before extending use. The retained historical results use modelled option fills and do not establish real execution.

The committed dashboard snapshot is a newly constructed empty demo, not the existing user account. Generated results are excluded from this public upload and Git history. Never replace the demo with a private account export. Existing local reports and the running cloud account were left untouched.
