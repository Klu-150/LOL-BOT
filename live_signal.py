"""Daily research preview and optional signal journal. Never submits orders."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import config as C
import algorithm
import pricing
import regime
import risk
import strategies as ST
from data import ROOT, first_event_in, load_events, load_market


def _next_expiry(today):
    d = today + timedelta(days=1)
    while d.weekday() != (3 if d < C.EXPIRY_SWITCH_DATE else 1):
        d += timedelta(days=1)
    return d  # nominal only; a real exchange calendar is needed before execution


def _rounded(value, digits=1):
    return round(float(value), digits) if math.isfinite(float(value)) else None


def latest_signal(mkt=None, feat=None, capital=None, profile=None, as_of=None) -> dict:
    capital = float(C.START_CAPITAL if capital is None else capital)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Capital must be finite and positive")
    profile = profile or C.ALGORITHM
    if mkt is None:
        mkt = load_market()
    if feat is None:
        feat = regime.classify(regime.add_features(mkt))
    r = feat.iloc[-1]
    today = feat.index[-1].date()
    as_of = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    expiry = _next_expiry(today)
    event = first_event_in(load_events(), today, expiry)
    decision = algorithm.select(r, event is not None, profile)
    pick, reason = decision.strategy, decision.reason
    spot, iv = float(r["Close"]), float(r["VIX"]) / 100
    years = max((expiry - today).days, 1) / 365
    age = (as_of - today).days
    scheduled = today.weekday() == (3 if today < C.EXPIRY_SWITCH_DATE else 1)
    out = {
        "mode": "research_preview", "algorithm": profile, "date": str(today),
        "as_of": str(as_of), "data_age_days": age,
        "nifty_close": _rounded(spot, 2), "india_vix": _rounded(r["VIX"], 2),
        "iv_rank": _rounded(r["ivr"]), "adx": _rounded(r["adx"]),
        "realized_vol_pct": _rounded(r["realized_vol"]),
        "iv_rv_ratio": _rounded(r["iv_rv_ratio"], 2),
        "ema20": _rounded(r["ema_fast"]), "ema50": _rounded(r["ema_slow"]),
        "trend": r["trend"], "iv_level": r["iv"], "shock": bool(r["shock"]),
        "event_this_week": str(event) if event else None,
        "next_expiry": str(expiry), "expiry_calendar": "nominal; holidays unverified",
        "entry_schedule": "weekly at previous expiry close; daily signals are previews",
        "scheduled_entry_day": scheduled,
        "expected_move_pts": _rounded(pricing.expected_move(spot, iv, years), 0),
        "candidate_strategy": pick, "capital_rs": capital,
        "market_condition": decision.condition, "volatility_condition": decision.volatility,
        "bot_name": C.BOT_NAME, "spread_width": C.SPREAD_WIDTH,
        "risk_budget_rs": round(capital * C.RISK_PER_TRADE, 2),
        "risk_context": "fresh account snapshot; no open positions or historical drawdown supplied",
        "preview_lots": 0,
    }
    if pick:
        quote = risk.entry_quote(pick, spot, years, iv)
        rejection = risk.entry_filter(pick, quote, profile)
        lots, size_reason = risk.size_position(capital, capital, quote["risk_estimate_rs"])
        reason = rejection or size_reason
        from strategies import KIND
        out.update({
            "structure": KIND[pick],
            "entry_credit_pts": round(-quote["entry_net_pts"], 2),
            "payoff_max_loss_per_lot_rs": round(quote["payoff_max_loss_rs"], 2),
            "estimated_risk_per_lot_rs": round(quote["risk_estimate_rs"], 2),
            "minimum_capital_for_one_lot_rs": round(quote["risk_estimate_rs"] / C.RISK_PER_TRADE, 2),
            "preview_lots": lots if not rejection else 0,
            "legs": [f"{'BUY' if leg.qty > 0 else 'SELL'} {int(leg.K)} "
                     f"{'CE' if leg.cp == 'C' else 'PE'} "
                     f"({'front' if leg.expiry == 'front' else 'back'} expiry), model fill ~{fill:.2f}"
                     for leg, fill in zip(quote["legs"], quote["fills"])],
            "description": ST.DESCRIPTION[pick],
        })
        if rejection or not lots:
            pick = None
    if age < 0 or age > 3:
        pick, reason = None, "future_data" if age < 0 else "stale_data"
        out["preview_lots"] = 0
    if not scheduled and pick:
        pick, reason = None, "waiting_for_weekly_entry"
    out["strategy"] = pick or "no trade"
    out["reason"] = reason
    out["orders_submitted"] = False
    return out


def record_signal(signal, path):
    """Idempotent daily preview journal, not an executed-trade/fill ledger."""
    path = Path(path)
    key = (signal["date"], signal["algorithm"], signal["capital_rs"], signal["as_of"])
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if tuple(row["key"]) == key:
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"key": key, "recorded_at": datetime.now(timezone.utc).isoformat(),
           "record_type": "model_signal_preview", "signal": signal}
    with path.open("a") as f:
        f.write(json.dumps(row, allow_nan=False) + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capital", type=float, default=C.PAPER_CAPITAL)
    parser.add_argument("--profile", choices=algorithm.PROFILES, default=C.ALGORITHM)
    parser.add_argument("--explain", action="store_true", help="include condition-to-strategy rules")
    parser.add_argument("--record", action="store_true", help="append one preview per date/profile/capital/as-of")
    parser.add_argument("--journal", type=Path, default=ROOT / "paper" / "signals.jsonl")
    args = parser.parse_args()
    if not math.isfinite(args.capital) or args.capital <= 0:
        parser.error("--capital must be finite and positive")
    sig = latest_signal(capital=args.capital, profile=args.profile)
    if args.explain:
        sig["playbook"] = algorithm.playbook()
    print(json.dumps(sig, indent=2, allow_nan=False))
    if args.record:
        print("Journal: " + ("recorded" if record_signal(sig, args.journal) else "already recorded"))


if __name__ == "__main__":
    main()
