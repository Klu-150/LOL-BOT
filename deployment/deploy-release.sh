#!/usr/bin/env bash
# Compatibility entry point: all upgrades use prebuild, backups and rollback guards.
set -euo pipefail
exec bash "$(dirname "$0")/upgrade-paper-engine.sh" "$@"
