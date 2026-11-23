#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print 'The bot Python environment is missing. Open the project in Codex to restore it.'
  read '?Press Enter to close.'
  exit 1
fi
print 'Last of Our League — virtual money only'
if [[ -f paper/cloud_migration.json ]]; then
  print 'Your account now runs on the hosted engine. Open App & connection to sign in.'
  open -a Safari 'https://nifty-research-terminal.nearbydrape.chatgpt.site/#mobile'
  exit 0
fi
print 'Keep this window open. Open http://127.0.0.1:8765/#terminal and click Start auto paper.'
.venv/bin/python dashboard.py
read '?The dashboard has stopped. Press Enter to close.'
