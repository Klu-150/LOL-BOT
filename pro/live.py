"""Daily live decision from history + latest public bars.  python -m pro.live

Paper only: prints and records the plan; it never contacts a broker. Run it
after 15:10 IST (decide near the close, act at next open) or any time to see
the plan based on the last *completed* daily bar.
"""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from data import ROOT
import intraday_feed
from pro import engine, features
from pro.strategies import BY_NAME, LIBRARY

ZONE = ZoneInfo("Asia/Kolkata")
PLAN = ROOT / "paper" / "pro_engine_plan.json"
LOG = ROOT / "paper" / "pro_engine_decisions.jsonl"


def latest_daily(include_today=False, now=None):
    """Recent daily Nifty + VIX bars from the public feed (dates after the CSV are appended)."""
    now = now or datetime.now(ZONE)
    frames = {}
    for sym, col in (("^NSEI", None), ("^INDIAVIX", "VIX")):
        bars = intraday_feed.chart(sym, "1d", "6mo")
        bars.index = pd.to_datetime(bars.index.tz_convert(ZONE).date)
        frames[sym] = bars
    n = frames["^NSEI"][["Open", "High", "Low", "Close"]].copy()
    n["VIX"] = frames["^INDIAVIX"]["Close"].reindex(n.index).ffill()
    n["vix_observed"] = n.VIX.notna()
    today = pd.Timestamp(now.date())
    complete = now.hour * 60 + now.minute >= 15 * 60 + 10
    if today in n.index and not (include_today and complete):
        n = n.drop(today)  # an unfinished session is not a completed bar
    return n.dropna(subset=["VIX"])


def plan(f):
    trades = []
    for s in LIBRARY:
        trades += engine.simulate(f, s)
    chosen, _ = engine.select(f, trades)
    last, asof = f.iloc[-1], f.index[-1]
    out = {"as_of_bar": str(asof.date()), "regime": last.regime, "close": round(float(last.Close), 2),
           "vix": round(float(last.VIX), 2), "adx": round(float(last.adx), 1), "rsi2": round(float(last.rsi2), 1),
           "ema50": round(float(last.ema50), 1), "ema200": round(float(last.ema200), 1),
           "mode": "paper", "orders_submitted": False}
    open_pos = next((t for t in chosen if t.exit_date is None), None)
    if open_pos:
        s = BY_NAME[open_pos.strategy]
        exit_now = s.exit(last, open_pos.side, open_pos._held) or open_pos._held >= s.max_hold
        out.update(position={"strategy": open_pos.strategy, "side": open_pos.side,
                             "entry_date": str(open_pos.entry_date.date()), "entry_px": round(open_pos.entry_px, 2),
                             "stop": round(float(open_pos._stop), 2), "days_held": open_pos._held},
                   action="SELL_AT_NEXT_OPEN" if exit_now else "HOLD",
                   reason=("exit rule fired" if exit_now else f"trend intact; protective stop {open_pos._stop:.0f}"))
        return out
    if last.event_next:
        out.update(action="STAND_ASIDE", reason="scheduled market event next session (news veto)")
        return out
    allowed = engine.PLAYBOOK.get(last.regime, [])
    board = engine.eligible(engine.scoreboard(trades, last.regime, asof, f.index), allowed)
    fired = [(n, side) for (n, side) in board if BY_NAME[n].entry(last) == side]
    if not fired:
        why = (f"regime '{last.regime}' has no approved playbook; cash earns a liquid-fund yield"
               if not allowed else "no entry trigger today; waiting for a pullback or breakout")
        out.update(action="STAND_ASIDE", reason=why)
        return out
    name, side = max(fired, key=lambda k: board[k]["rank_key"])
    s = BY_NAME[name]
    out.update(action="BUY_AT_NEXT_OPEN" if side > 0 else "SELL_SHORT_AT_NEXT_OPEN", strategy=name, idea=s.idea,
               stop_estimate=round(float(last.Close - side * s.stop_atr * last.atr), 2),
               evidence={k: v for k, v in board[(name, side)].items() if k != "rank_key"})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true", help="use stored CSV history only")
    p.add_argument("--include-today", action="store_true", help="after 15:10 IST, treat today's bar as complete")
    a = p.parse_args()
    extra, source = None, "stored daily CSV"
    if not a.offline:
        try:
            extra, source = latest_daily(a.include_today), "stored CSV + Yahoo public daily bars"
        except Exception as exc:  # stale data never authorises a new entry
            source = f"stored CSV only (live fetch failed: {exc})"
    f = features.load(extra)
    result = {"generated_at": datetime.now(ZONE).isoformat(), "data": source, **plan(f)}
    if "live fetch failed" in source and result["action"].endswith("NEXT_OPEN") and "position" not in result:
        result.update(action="STAND_ASIDE", reason="live data unavailable; no new entry on stale data")
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(result, indent=2, default=str))
    with LOG.open("a") as fh:
        fh.write(json.dumps(result, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
