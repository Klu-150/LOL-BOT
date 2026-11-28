"""Multi-day iron condor for sideways markets (modelled option prices).

Textbook parameters fixed before testing: 16-delta shorts, 200-pt wings,
~14 calendar days to expiry, take profit at 50% of credit, stop at 2x credit,
exit with 3 days left, or when the market turns to stress / a strong trend.
Signal at day t close -> open at t+1 open priced with day t's VIX.
"""
import math

import pandas as pd

import config as C
import costs
import pricing

DTE = 14
WIDTH = 200
SHORT_DELTA = 0.16
TAKE_PROFIT = 0.50
STOP_MULT = 2.0
EXIT_DTE = 3
MIN_VIX_RANK = 50


def _legs(S, T, iv):
    kp = pricing.strike_for_delta(S, T, iv, "P", SHORT_DELTA)
    kc = pricing.strike_for_delta(S, T, iv, "C", SHORT_DELTA)
    return [("P", kp, -1), ("P", kp - WIDTH, 1), ("C", kc, -1), ("C", kc + WIDTH, 1)]


def _fill(legs, S, T, iv, opening):
    """Net premium received (+) when opening, paid (-) when closing; plus rupee fees per lot."""
    net, fees = 0.0, 0.0
    for cp, k, q in legs:
        mid = pricing.price(S, k, T, iv, cp)
        buying = (q > 0) == opening
        px = mid + costs.slippage(mid) if buying else max(0.0, mid - costs.slippage(mid))
        net += -px if buying else px
        fees += costs.order_charges(px, "buy" if buying else "sell")
    return net, fees


def signal(r, min_vix_rank=MIN_VIX_RANK):
    return r.regime == "range" and r.vix_rank >= min_vix_rank and not r.event_next


def simulate(f, min_vix_rank=MIN_VIX_RANK):
    rows, idx, trades, pos, pending = list(f.itertuples()), f.index, [], None, False
    for i, r in enumerate(rows):
        d = idx[i]
        if pending and pos is None:
            prev = rows[i - 1]
            iv, T = prev.VIX / 100, DTE / 365
            legs = _legs(r.Open, T, iv)
            credit, fees = _fill(legs, r.Open, T, iv, True)
            pos = {"entry_date": d, "spot": r.Open, "legs": legs, "credit": credit, "fees": fees,
                   "expiry": d + pd.Timedelta(days=DTE), "regime": prev.regime, "vix_rank": prev.vix_rank}
        pending = False
        if pos:
            left = (pos["expiry"] - d).days
            T = max(left, 0.5) / 365
            close_net, close_fees = _fill(pos["legs"], r.Close, T, r.VIX / 100, False)
            pnl = pos["credit"] + close_net
            reason = None
            if pnl >= TAKE_PROFIT * pos["credit"]:
                reason = "take_profit"
            elif pnl <= -STOP_MULT * pos["credit"]:
                reason = "stop"
            elif left <= EXIT_DTE:
                reason = "time"
            elif r.regime == "stress" or r.adx >= 30:
                reason = "regime_change"
            if reason:
                max_loss = WIDTH - pos["credit"]
                pnl_rs = pnl * C.LOT_SIZE - pos["fees"] - close_fees
                trades.append({**{k: v for k, v in pos.items() if k != "legs"}, "exit_date": d, "exit_reason": reason,
                               "pnl_pts": pnl, "pnl_rs_per_lot": pnl_rs, "max_loss_rs_per_lot": max_loss * C.LOT_SIZE,
                               "r": pnl_rs / (max_loss * C.LOT_SIZE),
                               "strikes": "/".join(str(int(k)) for _, k, _ in pos["legs"])})
                pos = None
                continue
        if pos is None and i + 1 < len(rows) and math.isfinite(r.vix_rank) and signal(r, min_vix_rank):
            pending = True
    return pd.DataFrame(trades)
