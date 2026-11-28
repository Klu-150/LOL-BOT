#!/usr/bin/env bash
# Deploy the LOL Pro paper terminal as its own service on the existing VM (over Tailscale).
# Does not stop, rebuild or reconfigure the League engine.
#   bash deployment/deploy-lolpro.sh <image-on-vm>     e.g. league-engine:candidate-20261128T110306Z
# The image must already exist on the VM and contain pro/ (built and tested by the guarded installer).
set -Eeuo pipefail
cd "$(dirname "$0")"
IMAGE=${1:?image tag on the VM required}
[[ "$IMAGE" =~ ^league-(engine|lolpro):[A-Za-z0-9._-]+$ ]]
HOST=${LEAGUE_VM_HOST:-100.68.162.75}
KEY=${LEAGUE_SSH_KEY:-$HOME/.ssh/last_of_our_league_azure}
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15 -o BatchMode=yes leagueadmin@"$HOST")
"${SSH[@]}" "mkdir -m 700 -p /tmp/lolpro-upload"
scp -i "$KEY" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o BatchMode=yes lolpro/compose.yaml leagueadmin@"$HOST":/tmp/lolpro-upload/compose.yaml
scp -i "$KEY" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o BatchMode=yes Caddyfile leagueadmin@"$HOST":/tmp/lolpro-upload/Caddyfile
"${SSH[@]}" "sudo bash -s '$IMAGE'" <<'REMOTE'
set -Eeuo pipefail
IMAGE=$1
docker image inspect "$IMAGE" >/dev/null
docker run --rm --network none --entrypoint python "$IMAGE" -c "import pro.server, pro.constituents"
install -d -m 755 /srv/lolpro
install -d -m 700 -o 10001 -g 10001 /srv/lolpro/state
install -m 644 /tmp/lolpro-upload/compose.yaml /srv/lolpro/compose.yaml
OLD=$(docker image inspect league-lolpro:current --format '{{.Id}}' 2>/dev/null || true)
docker image tag "$IMAGE" league-lolpro:current
cd /srv/lolpro
if ! docker compose up -d --no-build; then
  [ -z "$OLD" ] || docker image tag "$OLD" league-lolpro:current
  exit 1
fi
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8787/api/session >/dev/null; then ok=1; break; fi
  sleep 3
done
[ "${ok:-}" = 1 ] || { docker compose logs --tail 40; exit 1; }
tailscale serve --bg --http=8787 http://127.0.0.1:8787 >/dev/null
# Public route /pro/ on the League gateway: only with a login key configured, and only after validation.
if grep -q '^LOLPRO_ACCESS_KEY_SHA256=[0-9a-f]\{64\}$' /srv/lolpro/lolpro.env 2>/dev/null; then
  if ! cmp -s /tmp/lolpro-upload/Caddyfile /srv/league/Caddyfile; then
    docker run --rm -e LEAGUE_DOMAIN=example.invalid -v /tmp/lolpro-upload/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine \
      caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile >/dev/null
    cp -a /srv/league/Caddyfile "/srv/league/Caddyfile.before-lolpro-$(date -u +%Y%m%dT%H%M%SZ)"
    cat /tmp/lolpro-upload/Caddyfile > /srv/league/Caddyfile   # in place: the gateway bind-mounts this inode
    (cd /srv/league && docker compose exec -T gateway caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile)
  fi
  echo "Public (login required): https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com/pro/"
else
  echo "No LOLPRO_ACCESS_KEY_SHA256 in /srv/lolpro/lolpro.env: public route NOT enabled"
fi
curl -fsS --max-time 5 http://127.0.0.1:8765/readyz >/dev/null && echo "League engine still ready"
echo "LOL Pro running: http://league-engine.taila6936a.ts.net:8787 (Tailscale only)"
REMOTE
