#!/usr/bin/env bash
# Build and test a LOL Pro image ON the VM without touching the running League engine.
# Prints the tested image tag; deploy it with: bash deployment/deploy-lolpro.sh <tag>
set -Eeuo pipefail
cd "$(dirname "$0")"
HOST=${LEAGUE_VM_HOST:-100.68.162.75}
KEY=${LEAGUE_SSH_KEY:-$HOME/.ssh/last_of_our_league_azure}
OPTS=(-i "$KEY" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15 -o BatchMode=yes)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
../.venv/bin/python package-engine.py >/dev/null
../.venv/bin/python -c "import tarfile;from pathlib import Path;t=tarfile.open('/private/tmp/lolpro-qa-tests.tar.gz','w:gz');t.add('../tests',arcname='tests',filter=lambda m:None if '__pycache__' in Path(m.name).parts else m);t.close()"
ssh "${OPTS[@]}" leagueadmin@"$HOST" "mkdir -m 700 -p /tmp/lolpro-build-$STAMP"
scp "${OPTS[@]}" league-engine-source.tar.gz /private/tmp/lolpro-qa-tests.tar.gz install-production-release.sh leagueadmin@"$HOST":/tmp/lolpro-build-$STAMP/
ssh "${OPTS[@]}" leagueadmin@"$HOST" "sudo bash -s '$STAMP'" <<'REMOTE'
set -Eeuo pipefail
STAMP=$1; DIR=/tmp/lolpro-build-$STAMP
mkdir "$DIR/source" "$DIR/qa"
tar --no-same-owner -xzf "$DIR/league-engine-source.tar.gz" -C "$DIR/source"
tar --no-same-owner -xzf "$DIR/lolpro-qa-tests.tar.gz" -C "$DIR/qa"
TAG=league-lolpro:candidate-$STAMP
nice -n 10 docker build -q -t "$TAG" "$DIR/source" >/dev/null
docker run --rm --network none --memory 768m --pids-limit 128 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$DIR/qa/tests:/app/tests:ro" -v "$DIR/install-production-release.sh:/app/deployment/install-production-release.sh:ro" \
  --entrypoint python "$TAG" \
  -c "from cloud_bootstrap import seed_storage;seed_storage('/state');import pytest;raise SystemExit(pytest.main(['-q','/app/tests','-k','not browser_model_matches']))" | tail -2
rm -rf "$DIR"
echo "TESTED_IMAGE=$TAG"
REMOTE
