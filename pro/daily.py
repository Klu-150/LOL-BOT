"""Daily unattended paper run.  python -m pro.daily [--include-today]

1. Archives public 5-minute bars (Yahoo keeps only ~60 days) so intraday ideas
   such as an opening-range breakout can be validated once enough history exists.
2. Builds the daily plan from stored + latest public daily bars (pro.live).
3. Applies the news-risk veto: a new entry is skipped while market news risk is high.
4. Updates two forward PAPER books: the main options book (positional bull put
   credit spreads, pro/options_paper.py) and an index-ETF comparison book.
No broker, no real orders. Ledgers: paper/pro_options_ledger.json, paper/pro_engine_ledger.json
"""
import argparse
import json
from datetime import datetime

import pandas as pd

import intraday_feed
from data import ROOT
from pro import features, live, news, options_paper

LEDGER = ROOT / "paper" / "pro_engine_ledger.json"
OPTIONS_LEDGER = ROOT / "paper" / "pro_options_ledger.json"
CHART = ROOT / "paper" / "pro_engine_chart.json"
# Separate from data/intraday_nifty.csv, which is the published research dataset.
ARCHIVE = ROOT / "data" / "intraday_archive.csv"
CAPITAL = 500_000.0
CASH_YIELD = 0.06
COST_PCT = 0.0010  # per side


def _new(asof):
    return {"mode": "paper", "orders_submitted": False, "instrument": "Nifty index ETF proxy",
            "started": asof, "capital": CAPITAL, "cash": CAPITAL, "units": 0.0, "last_bar": asof,
            "last_close": None, "position": None, "fills": []}


def update_ledger(result, f):
    """Apply the previous run's pending order at this bar's open, accrue cash, mark to close."""
    led = json.loads(LEDGER.read_text()) if LEDGER.exists() else _new(result["as_of_bar"])
    bars = f.loc[f.index > led["last_bar"]] if led.get("last_close") is not None else f.iloc[-1:]
    for d, r in bars.iterrows():
        prev = led.get("last_bar")
        days = max((d - pd.Timestamp(prev)).days, 0) if prev else 0
        led["cash"] *= (1 + CASH_YIELD) ** (days / 365)
        order = led.pop("pending", None)
        if order == "BUY" and led["units"] == 0:
            px = float(r.Open) * (1 + COST_PCT)
            led["units"], led["cash"] = led["cash"] / px, 0.0
            led["fills"].append({"date": str(d.date()), "side": "BUY", "price": round(px, 2), "units": round(led["units"], 4)})
        elif order == "SELL" and led["units"] > 0:
            px = float(r.Open) * (1 - COST_PCT)
            led["cash"] += led["units"] * px
            led["fills"].append({"date": str(d.date()), "side": "SELL", "price": round(px, 2), "units": round(led["units"], 4)})
            led["units"] = 0.0
        led["last_bar"], led["last_close"] = str(d.date()), float(r.Close)
        led.setdefault("history", []).append({"date": str(d.date()), "equity": round(led["cash"] + led["units"] * float(r.Close), 2)})
    action = result["action"]
    if action == "BUY_AT_NEXT_OPEN" and led["units"] == 0:
        led["pending"] = "BUY"
    elif action == "SELL_AT_NEXT_OPEN" and led["units"] > 0:
        led["pending"] = "SELL"
    elif action == "HOLD" and led["units"] == 0 and not led["fills"]:
        led["pending"] = "BUY"  # first run: adopt the engine's open position at the next open
    elif action == "STAND_ASIDE" and led["units"] > 0:
        led["pending"] = "SELL"  # the engine is flat (e.g. stop hit); follow it
    equity = led["cash"] + led["units"] * (led["last_close"] or 0)
    led.update(equity=round(equity, 2), return_pct=round(100 * (equity / led["capital"] - 1), 2),
               invested=led["units"] > 0, updated_at=result["generated_at"])
    LEDGER.write_text(json.dumps(led, indent=2))
    return led


def _options_new(asof):
    return {"mode": "paper", "orders_submitted": False, "structure": "bull put credit spread (positional)",
            "started": asof, "capital": CAPITAL, "realised_rs": 0.0, "position": None, "trades": [],
            "last_bar": None, "last_vix": None}


def _realise(led, pos, value, d, reason):
    led["realised_rs"] = round(led["realised_rs"] + value["pnl_rs"], 2)
    led["trades"].append({**{k: pos[k] for k in ("label", "opened", "expiry", "lots", "credit_pts", "max_loss_rs")},
                          "closed": str(d), "reason": reason, "pnl_rs": value["pnl_rs"]})


def update_options_ledger(result, f):
    """Bull put spread book. Orders decided at a close fill at the next session's open."""
    led = json.loads(OPTIONS_LEDGER.read_text()) if OPTIONS_LEDGER.exists() else _options_new(result["as_of_bar"])
    bars = f.loc[f.index > led["last_bar"]] if led.get("last_bar") else f.iloc[0:0]
    for ts, r in bars.iterrows():
        d, vix_open = ts.date(), led.get("last_vix") or float(r.VIX)
        order = led.pop("pending", None)
        pos = led.get("position")
        if order == "CLOSE" and pos:
            _realise(led, pos, options_paper.mark(pos, float(r.Open), d, vix_open), d, "engine exit")
            led["position"] = pos = None
        elif order == "OPEN" and not pos:
            led["position"] = pos = options_paper.open_spread(CAPITAL + led["realised_rs"], float(r.Open), d, vix_open)
        if pos and options_paper.needs_roll(pos, d):
            _realise(led, pos, options_paper.mark(pos, float(r.Close), d, float(r.VIX)), d, "roll")
            led["position"] = pos = options_paper.open_spread(CAPITAL + led["realised_rs"], float(r.Close), d, float(r.VIX))
        if pos:
            pos["mark"] = options_paper.mark(pos, float(r.Close), d, float(r.VIX))
        led["last_bar"], led["last_vix"] = str(d), float(r.VIX)
        eq = CAPITAL + led["realised_rs"] + (pos["mark"]["pnl_rs"] if pos else 0.0)
        led.setdefault("history", []).append({"date": str(d), "equity": round(eq, 2), "nifty": round(float(r.Close), 2)})
    if not led.get("last_bar"):
        led["last_bar"], led["last_vix"] = str(f.index[-1].date()), float(f.iloc[-1].VIX)
    action, pos = result["action"], led.get("position")
    if action == "BUY_AT_NEXT_OPEN" and not pos:
        led["pending"] = "OPEN"
    elif action == "HOLD" and not pos and not led["trades"]:
        led["pending"] = "OPEN"  # first run: join the engine's open long signal at the next open
    elif action in ("SELL_AT_NEXT_OPEN", "STAND_ASIDE") and pos:
        led["pending"] = "CLOSE"
    open_pnl = pos["mark"]["pnl_rs"] if pos and pos.get("mark") else 0.0
    equity = CAPITAL + led["realised_rs"] + open_pnl
    led.update(equity=round(equity, 2), return_pct=round(100 * (equity / CAPITAL - 1), 2),
               open_pnl_rs=round(open_pnl, 2), updated_at=result["generated_at"])
    OPTIONS_LEDGER.write_text(json.dumps(led, indent=2))
    return led


def fill_pending_at_open(open_px, day, path=None):
    """Record a pending options order at today's opening price, as soon as the session has opened.

    Uses exactly what the 15:20 run would use (today's open, the prior close's VIX), so the books are
    identical; the later daily run sees no pending order and only marks/rolls the position.
    Returns a description of the fill, or None when nothing was pending.
    """
    path = path or OPTIONS_LEDGER
    if not path.exists():
        return None
    led = json.loads(path.read_text())
    order, pos = led.get("pending"), led.get("position")
    if not order or not led.get("last_bar") or str(day) <= led["last_bar"]:
        return None
    vix = led.get("last_vix")
    if not vix:
        return None
    if order == "OPEN" and not pos:
        pos = options_paper.open_spread(CAPITAL + led["realised_rs"], float(open_px), day, vix)
        led["position"] = pos
        if pos:
            pos["filled_live"] = True
            pos["mark"] = options_paper.mark(pos, float(open_px), day, vix)
        what = f"Opened {pos['label']}, {pos['lots']} lot(s), credit {pos['credit_pts']} pts" if pos else \
            "Entry skipped: the spread did not fit the risk budget"
    elif order == "CLOSE" and pos:
        value = options_paper.mark(pos, float(open_px), day, vix)
        _realise(led, pos, value, day, "engine exit")
        led["position"] = None
        what = f"Closed {pos['label']} at the open: P&L ₹{value['pnl_rs']:,.0f}"
    else:
        led.pop("pending", None)
        path.write_text(json.dumps(led, indent=2))
        return None
    led.pop("pending", None)
    open_pnl = led["position"]["mark"]["pnl_rs"] if led.get("position") else 0.0
    equity = CAPITAL + led["realised_rs"] + open_pnl
    led.update(equity=round(equity, 2), return_pct=round(100 * (equity / CAPITAL - 1), 2), open_pnl_rs=round(open_pnl, 2))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(led, indent=2))
    tmp.replace(path)
    return {"order": order, "day": str(day), "open": round(float(open_px), 2), "message": what}


NEWS_VETO_LEVEL = "high"


def run(include_today=False, news_snapshot=None):
    try:
        archive = intraday_feed.refresh(ARCHIVE, period="60d")
    except Exception as exc:
        archive = {"error": str(exc)}
    extra, source = None, "stored daily CSV"
    try:
        extra, source = live.latest_daily(include_today), "stored CSV + Yahoo public daily bars"
    except Exception as exc:
        source = f"stored CSV only (live fetch failed: {exc})"
    f = features.load(extra)
    result = {"generated_at": datetime.now(live.ZONE).isoformat(), "data": source, **live.plan(f)}
    if "live fetch failed" in source and "position" not in result and result["action"] != "STAND_ASIDE":
        result.update(action="STAND_ASIDE", reason="live data unavailable; no new entry on stale data")
    tail = f.iloc[-250:]
    CHART.write_text(json.dumps([{"d": str(i.date()), "c": round(float(r.Close), 2), "e50": round(float(r.ema50), 2),
                                  "e200": round(float(r.ema200), 2), "g": r.regime} for i, r in tail.iterrows()]))
    if news_snapshot is None:
        try:
            news_snapshot = news.NewsDesk().refresh()
        except Exception as exc:
            news_snapshot = {"risk": {"level": "unknown", "score": None}, "errors": {"all": str(exc)}}
    result["news_risk"] = news_snapshot.get("risk")
    if result["action"] == "BUY_AT_NEXT_OPEN" and (result["news_risk"] or {}).get("level") == NEWS_VETO_LEVEL:
        result.update(action="STAND_ASIDE", vetoed_signal=result.get("strategy"),
                      reason="entry signal vetoed: high-impact negative market news in the last 3 hours")
    ledger = update_ledger(result, f)
    options = update_options_ledger(result, f)
    result["paper_account"] = {k: ledger[k] for k in ("equity", "return_pct", "invested", "pending") if k in ledger}
    result["options_account"] = {k: options.get(k) for k in ("equity", "return_pct", "open_pnl_rs", "pending")}
    result["intraday_archive"] = archive
    live.PLAN.write_text(json.dumps(result, indent=2, default=str))
    with live.LOG.open("a") as fh:
        fh.write(json.dumps(result, default=str) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-today", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.include_today), indent=2, default=str))


if __name__ == "__main__":
    main()
