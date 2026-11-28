"""Daily unattended paper run.  python -m pro.daily [--include-today]

1. Archives public 5-minute bars (Yahoo keeps only ~60 days) so intraday ideas
   such as an opening-range breakout can be validated once enough history exists.
2. Builds the daily plan from stored + latest public daily bars (pro.live).
3. Updates a forward PAPER account that holds an index ETF (e.g. NIFTYBEES)
   fully while the engine is long and earns a liquid-fund yield in cash.
No broker, no real orders. Ledger: paper/pro_engine_ledger.json
"""
import argparse
import json
from datetime import datetime

import pandas as pd

import intraday_feed
from data import ROOT
from pro import features, live

LEDGER = ROOT / "paper" / "pro_engine_ledger.json"
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-today", action="store_true")
    a = p.parse_args()
    try:
        archive = intraday_feed.refresh(ARCHIVE, period="60d")
    except Exception as exc:
        archive = {"error": str(exc)}
    extra, source = None, "stored daily CSV"
    try:
        extra, source = live.latest_daily(a.include_today), "stored CSV + Yahoo public daily bars"
    except Exception as exc:
        source = f"stored CSV only (live fetch failed: {exc})"
    f = features.load(extra)
    result = {"generated_at": datetime.now(live.ZONE).isoformat(), "data": source, **live.plan(f)}
    if "live fetch failed" in source and "position" not in result and result["action"] != "STAND_ASIDE":
        result.update(action="STAND_ASIDE", reason="live data unavailable; no new entry on stale data")
    ledger = update_ledger(result, f)
    result["paper_account"] = {k: ledger[k] for k in ("equity", "return_pct", "invested", "pending") if k in ledger}
    result["intraday_archive"] = archive
    live.PLAN.write_text(json.dumps(result, indent=2, default=str))
    with live.LOG.open("a") as fh:
        fh.write(json.dumps(result, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
