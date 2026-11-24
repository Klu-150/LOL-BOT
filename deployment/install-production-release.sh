#!/usr/bin/env bash
# Run as root on the EXISTING VM. Build/test before the account is stopped.
set -Eeuo pipefail
umask 077
STAMP=${1:?release stamp required}
ARCHIVE_SHA=${2:?archive hash required}
EXPECTED_VERSION=${3:?version required}
WHEEL_CACHE=${4:-}
[[ "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
[[ "$ARCHIVE_SHA" =~ ^[0-9a-f]{64}$ ]]
[[ "$EXPECTED_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
cd "${LEAGUE_DEPLOY_ROOT:-/srv/league}"
exec 9>production-deploy.lock
flock -n 9 || { echo 'Another production deployment holds the lock.'; exit 1; }
UPLOAD=${LEAGUE_DEPLOY_UPLOAD:-/tmp/league-production-$STAMP}
STAGE=releases/production-$STAMP
chmod 700 releases
mkdir -m 700 "$STAGE"
[ "$(sha256sum "$UPLOAD/league-engine-source.tar.gz" | cut -d' ' -f1)" = "$ARCHIVE_SHA" ]
mkdir "$STAGE/source"
tar --no-same-owner -xzf "$UPLOAD/league-engine-source.tar.gz" -C "$STAGE/source"
if [ -n "$WHEEL_CACHE" ]; then
  [[ "$WHEEL_CACHE" == /tmp/league-verified-wheels/deployment/wheelhouse ]]
  [ -d "$WHEEL_CACHE" ]
  mkdir -p "$STAGE/source/deployment/wheelhouse"
  cp -a "$WHEEL_CACHE/." "$STAGE/source/deployment/wheelhouse/"
fi
CANDIDATE=league-engine:candidate-$STAMP
docker build -t "$CANDIDATE" "$STAGE/source"
# Linux/Python release tests run with isolated state, no network and no broker.
mkdir "$STAGE/qa"
tar --no-same-owner -xzf "$UPLOAD/qa-tests.tar.gz" -C "$STAGE/qa"
docker run --rm --network none --memory 768m --pids-limit 128 \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$PWD/$STAGE/qa/tests:/app/tests:ro" \
  -v "$UPLOAD/install-production-release.sh:/app/deployment/install-production-release.sh:ro" --entrypoint python "$CANDIDATE" \
  -c "from cloud_bootstrap import seed_storage;seed_storage('/state');import pytest;raise SystemExit(pytest.main(['-q','/app/tests','-k','not browser_model_matches']))"
# Refuse cutover with any open position or a changed strategy fingerprint.
python3 - "$STAGE/source" "$STAGE/account-before.json" <<'PY'
import hashlib,json,pathlib,sqlite3,sys
root=pathlib.Path(sys.argv[1])
from datetime import datetime
from zoneinfo import ZoneInfo
now=datetime.now(ZoneInfo('Asia/Kolkata'))
sys.path.insert(0,str(root))
from exchange_calendar import deployment_allowed
assert deployment_allowed(now),'Deploy only outside a reviewed exchange session'
with sqlite3.connect('file:state/paper/intraday_500k.sqlite3?mode=ro',uri=True) as db:
    state=json.loads(db.execute('select body from account where id=1').fetchone()[0])
assert state['position'] is None,'An open paper position prevents deployment'
assert all((root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest()==value for name,value in state['fingerprint'].items()),'Strategy fingerprint changed'
pathlib.Path(sys.argv[2]).write_text(json.dumps(state,sort_keys=True))
PY
OLD_IMAGE=$(docker inspect league-engine-1 --format '{{.Image}}')
cp -a compose.yaml Caddyfile "$STAGE/"
CHANGED=false
rollback(){
  result=$?
  [ "$result" -ne 0 ] || result=1
  if $CHANGED; then
    echo 'Release verification failed; restoring the previous image and configuration.'
    docker compose stop engine || true
    [ ! -d "$STAGE/old-source" ] || { mv source "$STAGE/failed-source"; mv "$STAGE/old-source" source; }
    cp "$STAGE/compose.yaml" "$STAGE/Caddyfile" .
    docker image tag "$OLD_IMAGE" league-engine:current
    docker compose up -d --no-build || true
  fi
  exit "$result"
}
trap rollback ERR INT TERM
CHANGED=true
docker compose stop engine
# Frozen, private backup of the full persistent state, including SQLite WAL files.
tar czf "$STAGE/state-before.tar.gz" state
sha256sum "$STAGE/state-before.tar.gz" > "$STAGE/state-before.sha256"
mv source "$STAGE/old-source"
mv "$STAGE/source" source
cp "$UPLOAD/compose.yaml" "$UPLOAD/Caddyfile" .
docker image tag "$CANDIDATE" league-engine:current
docker compose up -d --no-build
ready=false
for attempt in $(seq 1 35); do
  if curl --max-time 5 -fsS http://127.0.0.1:8765/readyz >/dev/null; then ready=true; break; fi
  sleep 2
done
$ready
# Verify the running version and exact account preservation without printing keys.
docker compose exec -T engine python - "$EXPECTED_VERSION" <<'PY'
import sys
from cloud_server import VERSION
assert VERSION==sys.argv[1],(VERSION,sys.argv[1])
PY
python3 - "$STAGE/account-before.json" <<'PY'
import json,pathlib,sqlite3,sys
before=json.loads(pathlib.Path(sys.argv[1]).read_text())
with sqlite3.connect('file:state/paper/intraday_500k.sqlite3?mode=ro',uri=True) as db:
    after=json.loads(db.execute('select body from account where id=1').fetchone()[0])
    assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
assert before==after,'Account state changed during cutover; operator review required'
PY
CHANGED=false
trap - ERR INT TERM
printf 'Production release %s installed; readiness, ledger integrity and unchanged account verified.\n' "$EXPECTED_VERSION"
printf 'Recovery directory: %s\n' "$STAGE"
