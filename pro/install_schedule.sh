#!/bin/sh
# Run the adaptive engine's PAPER daily job at 15:20 local time, Monday-Friday (macOS).
# The Mac must be awake at that time. Remove with:  sh pro/install_schedule.sh --remove
set -eu
LABEL=com.lastofourleague.pro-daily
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT=$(cd "$(dirname "$0")/.." && pwd)

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/paper"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0"><dict>'
  echo "  <key>Label</key><string>$LABEL</string>"
  echo "  <key>ProgramArguments</key><array><string>$ROOT/.venv/bin/python</string><string>-m</string><string>pro.daily</string><string>--include-today</string></array>"
  echo "  <key>WorkingDirectory</key><string>$ROOT</string>"
  echo '  <key>StartCalendarInterval</key><array>'
  for d in 1 2 3 4 5; do
    echo "    <dict><key>Weekday</key><integer>$d</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>20</integer></dict>"
  done
  echo '  </array>'
  echo "  <key>StandardOutPath</key><string>$ROOT/paper/pro_daily.log</string>"
  echo "  <key>StandardErrorPath</key><string>$ROOT/paper/pro_daily.log</string>"
  echo '</dict></plist>'
} > "$PLIST"
plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL: weekdays 15:20 -> $ROOT/paper/pro_engine_plan.json (log: paper/pro_daily.log)"
