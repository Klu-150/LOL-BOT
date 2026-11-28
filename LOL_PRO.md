# LOL Pro terminal — paper trading guide

LOL Pro is the new terminal for this project. It runs on this Mac, trades **on paper only** (no broker,
no real orders) and replaces the intraday options bot with a positional, regime-based options strategy.

## Start it

Double-click **Launch LOL Pro.command** (keep the window open), or run:

```sh
.venv/bin/python -m pro.server        # then open http://127.0.0.1:8787
```

To keep it running in the background (starts at login, restarts if it stops):
`sh pro/install_schedule.sh` — remove with `sh pro/install_schedule.sh --remove`.
The Mac must be awake around 15:20 IST on trading days, when the daily decision runs.

### Optional settings — `~/.lolpro.env`

```sh
ANTHROPIC_API_KEY=sk-ant-...        # turns on the Claude-powered assistant (model: claude-opus-5-5)
TELEGRAM_BOT_TOKEN=123456:ABC...    # phone alerts via your own Telegram bot (create one with @BotFather)
TELEGRAM_CHAT_ID=123456789
PRO_DESKTOP_NOTIFY=1                # macOS notifications (default on)
```

Without an API key the assistant still answers from the terminal's live data, in a simpler style.
With a key it sends the terminal's data snapshot and your question to Anthropic's API (paid per use).

## What each section shows

| Section | What it is for |
|---|---|
| Overview | What the bot is doing and why, account, open spread, Nifty today, alerts and market-moving news |
| Markets | Live Nifty 50 and Sensex cards; all 50 Nifty and 30 Sensex companies as a heatmap or sortable list (updated every minute in market hours); click a company for its live 1-minute chart, 1-year chart, day and 52-week range, volume and news; 12-month Nifty chart with the regime the bot detected each day |
| News | Live headlines from Google News, Economic Times, Livemint and Business Standard (every 2 min), sentiment/impact tags, company news, news-risk gauge |
| Assistant | Ask about the market, the bot's decision, performance, news, issues or go-live readiness |
| Performance | One-month trial scorecard (checks, pros, cons), equity curve, trades, 10-year research results |
| Alerts | Every alert, system health, where alerts are delivered, "Run decision now" |
| How it works | Regimes, playbook, the options trade and the safety rules in plain language |

## How the bot trades

1. After 15:20 IST it reads the completed daily chart, India VIX and the news risk.
2. It classifies the regime (uptrend, transition, range, downtrend, stress) and applies that playbook.
3. On a long signal it opens a **bull put credit spread** at the next open: sell a ~0.30-delta put, buy a put
   300 points lower, monthly expiry ≥ 28 days away. Max loss is fixed (≤ 4% of the account per trade).
4. It rolls the spread with 7 days to expiry and closes it when the engine exits (stop, exit rule or regime change).
5. High negative news risk blocks new entries. News never opens or closes a trade by itself.

Why this structure: on the same 2016–2026 signals, every option-buying structure lost money after costs, and the
bull put spread was the only option structure profitable in both 2016–22 and 2023–26
(`python -m pro.options_research`). Option prices are modelled from India VIX, so real fills will differ.

## Alerts you will get

New trade signals · entry vetoed by news · Nifty below the protective stop during market hours ·
spread loss above half its maximum · high news risk · market or news feeds failing · daily decision failed ·
stale data · missing NSE holiday calendar for a new year.

## The one-month paper trial — be realistic

- The engine is a **swing system**: it traded about twice in the last 14 months. One month will probably show
  0–2 trades, which cannot prove the strategy works. The trial mainly proves the **system runs reliably**.
- Use the Performance page each week. Write down anything odd (missed runs, alerts, prices that look wrong).
- Before real money: all trial checks green, no unresolved errors, and you understand the maximum loss of
  each spread. Start with **1 lot**, compare real fills with the paper book, and keep the same rules.
- Real trading needs a broker account with F&O enabled and margin for the spread (ask your broker for the
  hedged-spread margin per lot; it is much lower than selling a naked put). This terminal does not place real orders.

## Files

| Path | Contents |
|---|---|
| `paper/pro_options_ledger.json` | Options paper book (positions, trades, equity history) |
| `paper/pro_engine_ledger.json` | Index-ETF comparison book |
| `paper/pro_engine_plan.json`, `paper/pro_engine_decisions.jsonl` | Latest plan and every decision |
| `paper/pro_alerts.json` | Alert history |
| `data/intraday_archive.csv` | Growing 5-minute archive for future intraday research |
| `data/indices/nifty50.csv`, `data/indices/sensex30.csv` | Index members (NSE official list; Sensex reviewed 28 Nov 2026). Update when the indices rebalance (June and December) |
