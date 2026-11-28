"""Trading assistant. Uses Claude when credentials exist, else built-in answers from live data.

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile). The model only
sees the terminal's own data snapshot; it cannot place orders.
"""
import json
import os
from pathlib import Path

MODEL = "claude-opus-5-5"
SYSTEM = """You are the assistant inside "LOL Pro", a PAPER-trading terminal for the Indian Nifty 50 index.
You explain the market, the bot's decisions, its paper performance, news and alerts in plain, friendly English.

How the bot trades:
- Daily-bar regime engine. Regimes: uptrend, transition, range, downtrend, stress (high VIX).
- Playbook: in an uptrend it takes long signals (trend pullback, 55-day channel breakout, trend rider);
  in transition only a confirmed 55-day breakout; in range, downtrend and stress it stays in cash.
- A walk-forward kill switch disables a strategy whose recent record in the current regime is broken.
- Main paper book: positional bull put credit spreads (sell ~0.30-delta put, buy a put 300 points lower,
  monthly expiry 28+ days out, rolled with 7 days left, closed when the engine exits). Max loss is fixed at entry.
- News is only a risk veto: new entries are skipped while market news risk is "high". News never triggers trades.
- 2016-2026 research: the engine cut the worst drawdown from -38% (buy and hold) to about -10% but earned less
  than buy and hold. It trades rarely (a few times a year). Option prices in the paper book are modelled, not quotes.

Rules:
- Use only the data in <terminal_data>. Quote numbers with their timestamps. If something is missing or stale, say so.
- This is paper trading only. Never claim guaranteed profit. Never tell the user to put money into a specific trade.
- If asked whether to go live with real money, weigh the evidence honestly (sample size, drawdown, alerts).
- Be concise: short paragraphs or bullets, rupees as ₹ with Indian digit grouping where natural."""


def configured():
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").exists()


def _context(state):
    """Compact, JSON-serialisable snapshot of what the terminal knows right now."""
    news = state.get("news", {})
    return {
        "now": state.get("now"),
        "plan": state.get("plan"),
        "options_account": state.get("options_account"),
        "etf_comparison_account": state.get("etf_account"),
        "market": {k: v for k, v in (state.get("market") or {}).items() if k != "nifty_intraday"},
        "nifty_intraday_last": (state.get("market") or {}).get("nifty_intraday", [])[-12:],
        "news_risk": news.get("risk"),
        "headlines": [{k: i[k] for k in ("title", "source", "published", "sentiment", "impact", "companies")}
                      for i in news.get("items", [])[:25]],
        "alerts": state.get("alerts", [])[:15],
        "trial": state.get("trial"),
        "backtest": state.get("backtest"),
    }


def ask(question, history, state):
    """Return {"answer", "source"}. history: [{"role": "user"|"assistant", "content": str}, ...]."""
    if not configured():
        return {"answer": fallback(question, state), "source": "built-in (add ANTHROPIC_API_KEY for the AI assistant)"}
    import anthropic

    client = anthropic.Anthropic()
    turns = [m for m in history[-12:] if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    data = json.dumps(_context(state), default=str, separators=(",", ":"))
    messages = turns + [{"role": "user", "content": f"<terminal_data>{data}</terminal_data>\n\n{question}"}]
    try:
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, messages=messages,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.AuthenticationError:
        return {"answer": fallback(question, state), "source": "built-in (Claude credentials were rejected)"}
    except anthropic.RateLimitError:
        return {"answer": fallback(question, state), "source": "built-in (Claude rate limit; try again shortly)"}
    except anthropic.APIStatusError as exc:
        return {"answer": fallback(question, state), "source": f"built-in (Claude API error {exc.status_code})"}
    except anthropic.APIConnectionError:
        return {"answer": fallback(question, state), "source": "built-in (no connection to Claude)"}
    if resp.stop_reason == "refusal":
        return {"answer": "I can't help with that request. Ask me about the market, the bot, its trades or news.",
                "source": "claude"}
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {"answer": text or fallback(question, state), "source": f"claude ({resp.model})"}


def _rs(x):
    """Rupees with Indian digit grouping, e.g. ₹5,00,000."""
    if x is None:
        return "—"
    neg, n = x < 0, f"{abs(x):.0f}"
    head, tail = n[:-3], n[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if neg else "") + "₹" + ",".join(groups + [tail]) if groups else ("-" if neg else "") + "₹" + tail


def fallback(question, state):
    q = question.lower()
    plan, opt = state.get("plan") or {}, state.get("options_account") or {}
    mkt, news = state.get("market") or {}, state.get("news") or {}
    n, v = mkt.get("nifty") or {}, mkt.get("vix") or {}
    parts = []
    if any(w in q for w in ("market", "nifty", "today", "running", "index", "vix")):
        b = mkt.get("breadth") or {}
        parts.append(f"Nifty {n.get('price', '—')} ({n.get('change_pct', 0):+.2f}% on {n.get('as_of', '—')}), "
                     f"India VIX {v.get('price', '—')} ({v.get('change_pct', 0):+.2f}%). "
                     f"Heavyweights: {b.get('advancing', '—')} up / {b.get('declining', '—')} down. "
                     f"The engine reads the regime as **{plan.get('regime', 'unknown')}** (ADX {plan.get('adx', '—')}).")
    if any(w in q for w in ("position", "holding", "spread", "open", "buy", "sell", "doing")) or ("trade" in q and "real" not in q):
        pos = opt.get("position")
        if pos:
            m = pos.get("mark") or {}
            parts.append(f"Open paper spread: {pos['label']}, {pos['lots']} lot(s), credit {pos['credit_pts']} pts, "
                         f"P&L {_rs(m.get('pnl_rs'))} (max loss {_rs(pos['max_loss_rs'])}), {m.get('days_to_expiry', '—')} days to expiry.")
        elif opt.get("pending") == "OPEN":
            parts.append("No spread is open yet: a bull put spread will open at the next market open.")
        else:
            parts.append("No open options position right now.")
        parts.append(f"Today's decision: **{plan.get('action', '—')}** — {plan.get('reason', '')}")
    if any(w in q for w in ("performance", "profit", "loss", "p&l", "pnl", "money", "return", "equity")):
        parts.append(f"Options paper account: {_rs(opt.get('equity'))} ({opt.get('return_pct', 0):+.2f}%), "
                     f"{len(opt.get('trades', []))} closed trade(s), realised {_rs(opt.get('realised_rs'))}.")
    if "news" in q or "headline" in q:
        r = news.get("risk") or {}
        heads = "; ".join(i["title"] for i in news.get("items", [])[:5])
        parts.append(f"News risk is **{r.get('level', 'unknown')}** ({r.get('score', '—')}/100). Latest: {heads}")
    if any(w in q for w in ("alert", "issue", "problem", "error", "wrong")):
        al = [a for a in state.get("alerts", []) if a["level"] in ("warning", "error", "critical") and not a.get("resolved")][:5]
        parts.append("Open issues: " + ("; ".join(f"{a['title']} — {a['message']}" for a in al) if al else "none."))
    if any(w in q for w in ("ready", "real money", "live", "go-live", "go live")):
        t = state.get("trial") or {}
        checks = "\n".join(f"- {'✓' if c['ok'] else '…'} {c['name']}: {c['value']}" for c in t.get("checks", []))
        parts.append(f"**{t.get('verdict', 'The paper trial has not started yet.')}**\n{checks}")
        if t.get("cons"):
            parts.append("Watch-outs:\n" + "\n".join(f"- {c}" for c in t["cons"][:3]))
    if any(w in q for w in ("why", "strategy", "regime", "how")):
        parts.append(f"Regime **{plan.get('regime')}**: in an uptrend the bot buys pullbacks or breakouts; "
                     "otherwise it waits in cash. News is used only to veto new entries.")
    if not parts:
        parts.append(f"Regime **{plan.get('regime', '—')}**, decision **{plan.get('action', '—')}**. "
                     f"Options paper account {_rs(opt.get('equity'))}. Ask about the market, position, performance, news or alerts.")
    return "\n\n".join(parts)
