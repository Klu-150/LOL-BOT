#!/bin/sh
# Double-click to start the LOL Pro paper terminal and open it in the browser.
# Keep this window open while you want the bot to run. Paper trading only.
cd "$(dirname "$0")" || exit 1
if [ -f "$HOME/.lolpro.env" ]; then
  # Optional settings, e.g. ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  set -a; . "$HOME/.lolpro.env"; set +a
fi
( sleep 3; open "http://127.0.0.1:8787" ) &
exec .venv/bin/python -m pro.server
