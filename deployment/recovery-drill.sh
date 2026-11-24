#!/usr/bin/env bash
# Root on the existing VM: downloaded recovery data NEVER leaves this VM.
set -Eeuo pipefail
umask 077
cd /srv/league
exec 8>recovery-drill.lock
flock -n 8 || exit 0
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
START=$(date +%s)
ROOT_DIR=/srv/league/state/paper/recovery-drills/drill-$STAMP
NAME=league-recovery-$STAMP
finish(){
  result=$?
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  if [ "$result" -ne 0 ]; then
    python3 - <<'FAILURE'
from datetime import datetime,timezone
import json,os,pathlib
path=pathlib.Path('/srv/league/state/paper/recovery-drill-error.json');temporary=path.with_suffix('.tmp')
with temporary.open('w') as stream:json.dump({'at':datetime.now(timezone.utc).isoformat(),'state':'failed'},stream);stream.flush();os.fsync(stream.fileno())
os.chmod(temporary,0o600);os.chown(temporary,10001,10001);os.replace(temporary,path)
FAILURE
  fi
  exit "$result"
}
trap finish EXIT
# Only the running image has access to managed identity; the verifier has NONE.
docker exec --user 10001 league-engine-1 python /app/tools/recovery_drill.py prepare \
  --account leaguebackupdedf75 --destination /state/paper/recovery-drills/drill-$STAMP
IMAGE=$(docker inspect league-engine-1 --format '{{.Image}}')
docker run --rm --name "$NAME" --network none --memory 256m --cpus 0.5 --pids-limit 64 \
  --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$ROOT_DIR/state:/state" -v "$ROOT_DIR/RECOVERY_DRILL_ONLY:/recovery-marker:ro" \
  --entrypoint python "$IMAGE" /app/tools/recovery_drill.py verify --state /state > "$ROOT_DIR/result.jsonl"
python3 - "$ROOT_DIR" "$START" <<'PY'
from datetime import datetime,timezone
import json,pathlib,sys,time,os,shutil
root=pathlib.Path(sys.argv[1]);lines=root.joinpath('result.jsonl').read_text().splitlines()
result=json.loads(lines[-1]);assert result['boot_verified'] and result['exact_account_preservation']
meta=json.loads(root.joinpath('manifest.json').read_text())
value={**result,'at':datetime.now(timezone.utc).isoformat(),'recovery_seconds':round(time.time()-int(sys.argv[2]),1),
       'snapshot_at':meta['snapshot_at'],'archive_sha256':meta['archive_sha256'],
       'scope':'Fresh isolated container on existing VM; does not verify provisioning a replacement VM or lost-subscription recovery'}
path=pathlib.Path('/srv/league/state/paper/recovery-drill.json');temporary=path.with_suffix('.tmp')
with temporary.open('w') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
os.chmod(temporary,0o600);os.chown(temporary,10001,10001);os.replace(temporary,path)
print(json.dumps(value))
assert root.parent==pathlib.Path("/srv/league/state/paper/recovery-drills") and root.name.startswith("drill-") and (root/"RECOVERY_DRILL_ONLY").is_file()
shutil.rmtree(root)
PY
