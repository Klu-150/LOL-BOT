"""Paper-trial scorecard: is the bot ready for a small real-money start?

Built from the forward options ledger, the decision log and alerts. Conservative
by design: a swing system trades a few times a year, so one month rarely proves edge.
"""
from datetime import date
import json

from data import ROOT

TARGET_DAYS = 30
MIN_SESSIONS = 18          # trading sessions processed during the trial
MAX_DRAWDOWN_PCT = 5.0
MIN_TRADES_FOR_EVIDENCE = 3


def _decision_days(since):
    log = ROOT / "paper" / "pro_engine_decisions.jsonl"
    days = set()
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("as_of_bar", "") >= since:
                days.add(d["as_of_bar"])
    return days


def scorecard(options, alerts, today=None):
    today = today or date.today()
    if not options or not options.get("started"):
        return {"status": "not_started", "message": "Run the daily job once to start the paper trial."}
    start = options["started"]
    elapsed = (today - date.fromisoformat(start)).days
    hist = options.get("history", [])
    eq = [h["equity"] for h in hist] or [options.get("capital", 500000)]
    peak, dd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        dd = min(dd, 100 * (e / peak - 1))
    nifty = [h["nifty"] for h in hist if h.get("nifty")]
    nifty_ret = round(100 * (nifty[-1] / nifty[0] - 1), 2) if len(nifty) > 1 else None
    trades = options.get("trades", [])
    closed = [t for t in trades if t.get("reason") != "roll"]
    wins = sum(1 for t in trades if t["pnl_rs"] > 0)
    sessions = len(_decision_days(start))
    serious = [a for a in alerts if a["level"] in ("error", "critical") and a["time"][:10] >= start]
    open_serious = [a for a in serious if not a.get("resolved")]
    checks = [
        {"name": f"Ran for {TARGET_DAYS} calendar days", "ok": elapsed >= TARGET_DAYS, "value": f"{elapsed} days"},
        {"name": f"Processed at least {MIN_SESSIONS} trading sessions", "ok": sessions >= MIN_SESSIONS, "value": f"{sessions} sessions"},
        {"name": "No unresolved errors or critical alerts", "ok": not open_serious, "value": f"{len(open_serious)} open"},
        {"name": f"Drawdown within {MAX_DRAWDOWN_PCT}%", "ok": dd >= -MAX_DRAWDOWN_PCT, "value": f"{dd:.1f}%"},
        {"name": f"At least {MIN_TRADES_FOR_EVIDENCE} completed trades observed", "ok": len(closed) >= MIN_TRADES_FOR_EVIDENCE,
         "value": f"{len(closed)} trades"},
    ]
    pros, cons = [], []
    ret = options.get("return_pct", 0.0)
    if ret > 0:
        pros.append(f"Paper options account is up {ret:.2f}% since {start}.")
    elif ret < 0:
        cons.append(f"Paper options account is down {abs(ret):.2f}% since {start}.")
    if nifty_ret is not None:
        (pros if ret >= nifty_ret else cons).append(f"Nifty moved {nifty_ret:+.2f}% over the same period (account {ret:+.2f}%).")
    if dd >= -MAX_DRAWDOWN_PCT:
        pros.append(f"Worst drawdown so far {dd:.1f}%, inside the {MAX_DRAWDOWN_PCT}% limit.")
    else:
        cons.append(f"Drawdown reached {dd:.1f}%, beyond the {MAX_DRAWDOWN_PCT}% limit.")
    if serious:
        cons.append(f"{len(serious)} error/critical alert(s) during the trial ({len(open_serious)} unresolved).")
    else:
        pros.append("No errors or critical alerts during the trial.")
    if len(closed) < MIN_TRADES_FOR_EVIDENCE:
        cons.append(f"Only {len(closed)} completed trade(s): too few to judge the strategy from the paper trial alone; "
                    "rely on the 10-year research and keep testing.")
    if trades:
        pros.append(f"{wins}/{len(trades)} closed legs (including rolls) were profitable.") if wins * 2 >= len(trades) else \
            cons.append(f"Only {wins}/{len(trades)} closed legs (including rolls) were profitable.")
    cons.append("Option prices and fills are modelled from India VIX, not real bid/ask quotes; real fills will differ.")
    ready = all(c["ok"] for c in checks)
    verdict = ("Checks passed. If you go live, start with 1 lot, keep the same rules, and compare real fills with "
               "the paper book for another month." if ready else
               "Not ready for real money yet: see the failed checks below.")
    return {"status": "ready" if ready else "in_progress", "started": start, "elapsed_days": elapsed,
            "target_days": TARGET_DAYS, "sessions": sessions, "return_pct": ret, "nifty_return_pct": nifty_ret,
            "max_drawdown_pct": round(dd, 2), "trades": len(closed), "checks": checks, "pros": pros,
            "cons": cons, "verdict": verdict}
