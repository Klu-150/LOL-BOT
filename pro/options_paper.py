"""Positional options paper book: bull put credit spreads on the engine's long signals.

Chosen by pro/options_research.py (2016-2026): of the option structures tested on
the same signals, the 0.30-delta bull put spread was the only one profitable in
both eras with realistic slippage, with the smallest drawdown. It earns time decay
and benefits when VIX falls in rallies; the maximum loss is fixed at entry.

Prices are modelled (Black-Scholes + skew on India VIX) with per-leg slippage
and statutory charges. Paper only; no broker.
"""
from datetime import date, timedelta
import math

import config as C
import costs
import pricing

SHORT_DELTA = 0.30
WIDTH = 300
MIN_DTE = 28
ROLL_DTE = 7
RISK_PER_TRADE = 0.04   # of equity vs the spread maximum loss (one lot is ~3.1% of 5L)
MAX_LOTS = 5


def monthly_expiry(d: date) -> date:
    """Last Tuesday of d's month (NSE monthly Nifty expiry from Sep 2025; holidays not adjusted)."""
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - 1) % 7)


def pick_expiry(d: date) -> date:
    exp = monthly_expiry(d)
    while (exp - d).days < MIN_DTE:
        exp = monthly_expiry(exp + timedelta(days=7))
    return exp


def _years(d: date, expiry: date) -> float:
    return max((expiry - d).days, 0.5) / 365


def _legs(spot, d, expiry, vix):
    k = pricing.strike_for_delta(spot, _years(d, expiry), vix / 100, "P", SHORT_DELTA)
    return [{"cp": "P", "K": k, "qty": -1}, {"cp": "P", "K": k - WIDTH, "qty": 1}]


def _fills(legs, spot, d, expiry, vix, opening):
    """Per-unit cash (+received) and per-lot rupee charges, with slippage against us."""
    cash, fees, prices = 0.0, 0.0, []
    for leg in legs:
        mid = pricing.price(spot, leg["K"], _years(d, expiry), vix / 100, leg["cp"])
        buying = (leg["qty"] > 0) == opening
        px = mid + costs.slippage(mid) if buying else max(0.0, mid - costs.slippage(mid))
        cash += -px if buying else px
        fees += costs.order_charges(px, "buy" if buying else "sell")
        prices.append(round(px, 2))
    return cash, fees, prices


def open_spread(equity, spot, d: date, vix):
    expiry = pick_expiry(d)
    legs = _legs(spot, d, expiry, vix)
    credit, fees, prices = _fills(legs, spot, d, expiry, vix, True)
    max_loss_lot = (WIDTH - credit) * C.LOT_SIZE + 2 * fees
    lots = min(MAX_LOTS, math.floor(equity * RISK_PER_TRADE / max_loss_lot))
    if lots < 1 or credit <= 0:
        return None
    return {"structure": "bull_put_credit_spread", "opened": str(d), "expiry": str(expiry), "lots": lots,
            "legs": legs, "entry_prices": prices, "credit_pts": round(credit, 2), "entry_fees_rs": round(fees * lots, 2),
            "max_loss_rs": round(max_loss_lot * lots, 2), "spot_at_entry": round(spot, 2), "vix_at_entry": round(vix, 2),
            "label": f"Sell {int(legs[0]['K'])} PE / Buy {int(legs[1]['K'])} PE, {expiry:%d %b %Y}"}


def mark(pos, spot, d: date, vix):
    """Value if closed now: rupee P&L after entry and exit charges."""
    expiry = date.fromisoformat(pos["expiry"])
    close_cash, fees, prices = _fills(pos["legs"], spot, d, expiry, vix, False)
    pnl = ((pos["credit_pts"] + close_cash) * C.LOT_SIZE - fees) * pos["lots"] - pos["entry_fees_rs"]
    return {"pnl_rs": round(pnl, 2), "exit_prices": prices, "days_to_expiry": (expiry - d).days,
            "spot": round(spot, 2), "vix": round(vix, 2), "as_of": str(d)}


def needs_roll(pos, d: date) -> bool:
    return (date.fromisoformat(pos["expiry"]) - d).days <= ROLL_DTE
