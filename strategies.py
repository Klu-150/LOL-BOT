"""
Strategy definitions: which legs to open, and how to manage the exit.

A leg is (cp, strike, qty, expiry) where qty = +1 long / -1 short (per lot)
and expiry is "front" (this week) or "back" (next week).
"""
from dataclasses import dataclass

import config as C
from pricing import round_strike, strike_for_delta


@dataclass
class Leg:
    cp: str        # "C" or "P"
    K: float
    qty: int       # +1 long, -1 short
    expiry: str    # "front" or "back"


# kind decides which exit rule applies
KIND = {
    "bull_call_spread": "debit_vertical",
    "bear_put_spread": "debit_vertical",
    "bull_put_spread": "credit",
    "bear_call_spread": "credit",
    "iron_condor": "credit",
    "long_straddle": "straddle",
    "calendar": "calendar",
}

DESCRIPTION = {
    "bull_call_spread": f"Buy ATM call, sell call {C.SPREAD_WIDTH} pts higher (debit)",
    "bear_put_spread": f"Buy ATM put, sell put {C.SPREAD_WIDTH} pts lower (debit)",
    "bull_put_spread": f"Sell 0.25-delta put, buy put {C.SPREAD_WIDTH} pts lower (credit)",
    "bear_call_spread": f"Sell 0.25-delta call, buy call {C.SPREAD_WIDTH} pts higher (credit)",
    "iron_condor": f"Sell 0.16-delta put + call, buy wings {C.SPREAD_WIDTH} pts out (credit)",
    "long_straddle": "Buy ATM call + ATM put (debit)",
    "calendar": "Sell this week's ATM call, buy next week's ATM call (debit)",
}

ALL_STRATEGIES = list(KIND.keys())


def build(name: str, S: float, T: float, iv: float) -> list:
    W = C.SPREAD_WIDTH
    atm = round_strike(S)
    if name == "bull_call_spread":
        return [Leg("C", atm, +1, "front"), Leg("C", atm + W, -1, "front")]
    if name == "bear_put_spread":
        return [Leg("P", atm, +1, "front"), Leg("P", atm - W, -1, "front")]
    if name == "bull_put_spread":
        k = strike_for_delta(S, T, iv, "P", C.CREDIT_SHORT_DELTA)
        return [Leg("P", k, -1, "front"), Leg("P", k - W, +1, "front")]
    if name == "bear_call_spread":
        k = strike_for_delta(S, T, iv, "C", C.CREDIT_SHORT_DELTA)
        return [Leg("C", k, -1, "front"), Leg("C", k + W, +1, "front")]
    if name == "iron_condor":
        kp = strike_for_delta(S, T, iv, "P", C.CONDOR_SHORT_DELTA)
        kc = strike_for_delta(S, T, iv, "C", C.CONDOR_SHORT_DELTA)
        return [
            Leg("P", kp, -1, "front"), Leg("P", kp - W, +1, "front"),
            Leg("C", kc, -1, "front"), Leg("C", kc + W, +1, "front"),
        ]
    if name == "long_straddle":
        return [Leg("C", atm, +1, "front"), Leg("P", atm, +1, "front")]
    if name == "calendar":
        return [Leg("C", atm, -1, "front"), Leg("C", atm, +1, "back")]
    raise ValueError(name)


def max_loss_points(name: str, entry_net: float) -> float:
    """Worst-case loss per unit, in points (entry_net > 0 = debit paid)."""
    kind = KIND[name]
    if kind == "credit":
        return C.SPREAD_WIDTH - (-entry_net)
    return entry_net  # debit structures: lose at most what you paid (approx. for calendar)


def exit_signal(name: str, pnl: float, entry_net: float):
    """Return an exit reason if a managed-exit rule fires, else None."""
    if not C.MANAGE_EXITS:
        return None
    kind = KIND[name]
    if kind == "credit":
        credit = -entry_net
        if pnl >= C.CREDIT_TAKE_PROFIT * credit:
            return "take_profit"
        if pnl <= -C.CREDIT_STOP_MULT * credit:
            return "stop_loss"
    elif kind == "debit_vertical":
        debit = entry_net
        max_profit = C.SPREAD_WIDTH - debit
        if pnl >= C.DEBIT_TAKE_PROFIT * max_profit:
            return "take_profit"
        if pnl <= -C.DEBIT_STOP * debit:
            return "stop_loss"
    elif kind == "straddle":
        if pnl >= C.STRADDLE_TAKE_PROFIT * entry_net:
            return "take_profit"
        if pnl <= -C.STRADDLE_STOP * entry_net:
            return "stop_loss"
    elif kind == "calendar":
        if pnl >= C.CALENDAR_TAKE_PROFIT * entry_net:
            return "take_profit"
        if pnl <= -C.CALENDAR_STOP * entry_net:
            return "stop_loss"
    return None
