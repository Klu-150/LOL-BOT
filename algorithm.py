"""Deterministic research policy. No parameter fitting and no broker access."""
from dataclasses import dataclass
import math

import config as C
import regime


@dataclass(frozen=True)
class Decision:
    strategy: str | None
    reason: str
    condition: str = "unclear"
    volatility: str = "unclear"


PROFILES = ("adaptive_regime", "credit_regime", "legacy")
PAPER_PROFILES = ("adaptive_regime", "credit_regime")


def market_condition(row):
    if row["adx"] < C.ADX_RANGE:
        return "range"
    if row["Close"] > row["ema_fast"] > row["ema_slow"]:
        return "rising"
    if row["Close"] < row["ema_fast"] < row["ema_slow"]:
        return "falling"
    return "unclear"


def volatility_condition(row):
    if row["ivr"] >= C.MIN_IV_RANK and row["iv_rv_ratio"] >= C.MIN_IV_RV_RATIO:
        return "rich"
    if row["ivr"] < C.MIN_IV_RANK and row["iv_rv_ratio"] <= C.MAX_CHEAP_IV_RV_RATIO:
        return "cheap"
    return "mixed"


def playbook():
    return [
        {"condition": "Rising + cheap volatility", "strategy": "bull_call_spread", "reason": "uptrend_debit"},
        {"condition": "Rising + rich volatility", "strategy": "bull_put_spread", "reason": "uptrend_credit"},
        {"condition": "Falling + cheap volatility", "strategy": "bear_put_spread", "reason": "downtrend_debit"},
        {"condition": "Falling + rich volatility", "strategy": "bear_call_spread", "reason": "downtrend_credit"},
        {"condition": "Range + rich volatility", "strategy": "iron_condor", "reason": "range_credit"},
        {"condition": "Range + cheap/mixed volatility", "strategy": None, "reason": "range_without_premium"},
        {"condition": "Unclear trend or mixed directional volatility", "strategy": None, "reason": "no_clear_setup"},
        {"condition": "Event, VIX shock or missing data", "strategy": None, "reason": "risk_veto"},
    ]


def select(row, event=False, profile=None):
    profile = profile or C.ALGORITHM
    if profile not in PROFILES:
        raise ValueError(f"Unknown algorithm: {profile}")
    required = ["Close", "VIX", "ivr", "adx", "ema_fast", "ema_slow"]
    if profile != "legacy":
        required += ["realized_vol", "iv_rv_ratio"]
    if any(not math.isfinite(float(row.get(k, float("nan")))) for k in required):
        return Decision(None, "insufficient_features")
    if row["Close"] <= 0 or row["VIX"] <= 0:
        return Decision(None, "invalid_market_data")
    if profile == "legacy":
        pick = regime.choose_strategy(row["trend"], row["iv"], row["shock"], event)
        return Decision(pick, "legacy_playbook" if pick else "legacy_no_trade")
    if not row.get("vix_observed", True):
        return Decision(None, "missing_same_day_vix")
    if row["shock"] or row["VIX"] >= C.VIX_SHOCK:
        return Decision(None, "volatility_shock")
    if event:
        return Decision(None, "scheduled_event")
    condition, volatility = market_condition(row), volatility_condition(row)
    if profile == "adaptive_regime":
        routing = {
            ("rising", "cheap"): ("bull_call_spread", "uptrend_debit"),
            ("rising", "rich"): ("bull_put_spread", "uptrend_credit"),
            ("falling", "cheap"): ("bear_put_spread", "downtrend_debit"),
            ("falling", "rich"): ("bear_call_spread", "downtrend_credit"),
            ("range", "rich"): ("iron_condor", "range_credit"),
        }
        name, reason = routing.get((condition, volatility),
                                  (None, "range_without_premium" if condition == "range" else "no_clear_setup"))
        return Decision(name, reason, condition, volatility)
    if row["ivr"] < C.MIN_IV_RANK:
        return Decision(None, "low_iv_rank")
    if row["iv_rv_ratio"] < C.MIN_IV_RV_RATIO:
        return Decision(None, "insufficient_volatility_premium")
    if row["Close"] > row["ema_fast"] > row["ema_slow"] and row["adx"] >= C.ADX_RANGE:
        return Decision("bull_put_spread", "uptrend_credit")
    if row["Close"] < row["ema_fast"] < row["ema_slow"] and row["adx"] >= C.ADX_RANGE:
        return Decision("bear_call_spread", "downtrend_credit")
    if row["adx"] < C.ADX_RANGE:
        return Decision("iron_condor", "range_credit")
    return Decision(None, "conflicting_trend")


def invalidation(name, row, profile):
    """Daily close invalidation; never open a replacement on the same close."""
    if profile != "adaptive_regime" or not C.MANAGE_EXITS:
        return None
    keys = ("Close", "VIX", "adx", "ema_fast", "ema_slow")
    if any(not math.isfinite(float(row.get(k, float("nan")))) for k in keys):
        return None
    if row["VIX"] >= C.VIX_SHOCK:
        return "volatility_shock"
    condition = market_condition(row)
    if name in ("bull_call_spread", "bull_put_spread") and condition == "falling":
        return "regime_reversal"
    if name in ("bear_put_spread", "bear_call_spread") and condition == "rising":
        return "regime_reversal"
    if name == "iron_condor" and condition in ("rising", "falling") and row["adx"] >= C.ADX_TREND:
        return "range_breakout"
    return None
