#!/usr/bin/env bash
# Local operator: no public SSH exposure, no credential output, no new cloud resource.
set -Eeuo pipefail
cd "$(dirname "$0")"
# Private Tailscale address: works from any network; public SSH port is closed.
HOST=${LEAGUE_VM_HOST:?Set LEAGUE_VM_HOST to your authorized private VM address}
KEY=${LEAGUE_SSH_KEY:-$HOME/.ssh/last_of_our_league_azure}
KNOWN=${LEAGUE_SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}
SSH=(ssh -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15 -o BatchMode=yes leagueadmin@"$HOST")
SCP=(scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15 -o BatchMode=yes)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
UPLOAD=/tmp/league-production-$STAMP
SHA=$(shasum -a 256 league-engine-source.tar.gz | cut -d' ' -f1)
VERSION=$(../.venv/bin/python -c "import sys;sys.path.insert(0,'..');from cloud_server import VERSION;print(VERSION)")
[ -f "$KNOWN" ]
"${SSH[@]}" "mkdir -m 700 '$UPLOAD'"
../.venv/bin/python -c "import tarfile;from pathlib import Path;t=tarfile.open('/private/tmp/league-production-qa-tests.tar.gz','w:gz');t.add('../tests',arcname='tests',filter=lambda member:None if '__pycache__' in Path(member.name).parts else member);t.close()"
"${SCP[@]}" league-engine-source.tar.gz compose.yaml Caddyfile install-production-release.sh /private/tmp/league-production-qa-tests.tar.gz leagueadmin@"$HOST":"$UPLOAD/"
"${SSH[@]}" "mv '$UPLOAD/league-production-qa-tests.tar.gz' '$UPLOAD/qa-tests.tar.gz' && sudo bash '$UPLOAD/install-production-release.sh' '$STAMP' '$SHA' '$VERSION' '${LEAGUE_VM_WHEEL_CACHE:-}'"
printf 'Installed release stamp: %s\n' "$STAMP"

