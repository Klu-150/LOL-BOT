#!/bin/sh
# Keep the LOL Pro paper terminal running in the background on this Mac (starts at login,
# restarts if it stops). The server itself runs the 15:20 IST daily decision, news and alerts.
# The Mac must be awake during market hours.   Remove:  sh pro/install_schedule.sh --remove
# Optional settings are read from ~/.lolpro.env (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
set -eu
LABEL=com.lastofourleague.pro-terminal
OLD=com.lastofourleague.pro-daily
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT=$(cd "$(dirname "$0")/.." && pwd)

launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/$OLD.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$OLD.plist"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/paper"
CMD="cd '$ROOT' || exit 1; if [ -f \"\$HOME/.lolpro.env\" ]; then set -a; . \"\$HOME/.lolpro.env\"; set +a; fi; exec '$ROOT/.venv/bin/python' -m pro.server"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0"><dict>'
  echo "  <key>Label</key><string>$LABEL</string>"
  echo "  <key>ProgramArguments</key><array><string>/bin/sh</string><string>-c</string><string>$CMD</string></array>"
  echo "  <key>WorkingDirectory</key><string>$ROOT</string>"
  echo '  <key>RunAtLoad</key><true/>'
  echo '  <key>KeepAlive</key><true/>'
  echo '  <key>ThrottleInterval</key><integer>30</integer>'
  echo "  <key>StandardOutPath</key><string>$ROOT/paper/pro_server.log</string>"
  echo "  <key>StandardErrorPath</key><string>$ROOT/paper/pro_server.log</string>"
  echo '</dict></plist>'
} > "$PLIST"
plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL. Open http://127.0.0.1:8787 (log: paper/pro_server.log)"
