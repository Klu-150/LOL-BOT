#!/usr/bin/env bash
# Store a LOL Pro setting on the server without echoing it or saving it on this Mac, then restart LOL Pro.
#   bash deployment/set-lolpro-secret.sh ANTHROPIC_API_KEY      (enables the Claude assistant)
#   bash deployment/set-lolpro-secret.sh TELEGRAM_BOT_TOKEN     (phone alerts, with TELEGRAM_CHAT_ID)
#   bash deployment/set-lolpro-secret.sh TELEGRAM_CHAT_ID
# The value is written only to /srv/lolpro/lolpro.env (root-only, mode 600) on the VM.
set -Eeuo pipefail
NAME=${1:?setting name required}
case "$NAME" in ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID) ;; *) echo "Unsupported setting: $NAME"; exit 2;; esac
HOST=${LEAGUE_VM_HOST:-100.68.162.75}
KEY=${LEAGUE_SSH_KEY:-$HOME/.ssh/last_of_our_league_azure}
read -r -s -p "Value for $NAME (input hidden): " VALUE; echo
[ -n "$VALUE" ] || { echo "Empty value; nothing changed."; exit 1; }
case "$VALUE" in *[[:space:]]*|*\'*|*\"*|*\\*) echo "Value contains spaces or quotes; nothing changed."; exit 1;; esac
printf '%s\n' "$VALUE" | ssh -i "$KEY" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15 -o BatchMode=yes \
  leagueadmin@"$HOST" "sudo bash -c 'set -Eeuo pipefail; umask 077; IFS= read -r v; f=/srv/lolpro/lolpro.env; touch \$f;
    grep -v \"^$NAME=\" \$f > \$f.new || true; printf \"%s=%s\n\" $NAME \"\$v\" >> \$f.new; mv \$f.new \$f; chmod 600 \$f;
    cd /srv/lolpro && docker compose up -d --no-build >/dev/null 2>&1; echo \"$NAME saved; LOL Pro restarted.\"'"
