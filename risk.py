"""Shared entry estimates and account sizing for backtests and signal previews."""
import math

import config as C
import costs
import pricing
import strategies as ST


def entry_quote(name, spot, years, iv, back_years=None):
    legs = ST.build(name, spot, years, iv)
    fills, charges, close_reserve = [], 0.0, 0.0
    for leg in legs:
        t = years if leg.expiry == "front" else (back_years or years + 7 / 365)
        mid = pricing.price(spot, leg.K, t, iv, leg.cp)
        fill = mid + costs.slippage(mid) if leg.qty > 0 else max(0.05, mid - costs.slippage(mid))
        fills.append(fill)
        charges += costs.order_charges(fill, "buy" if leg.qty > 0 else "sell")
        close_reserve += costs.order_charges(mid, "sell" if leg.qty > 0 else "buy")
        close_reserve += costs.slippage(mid) * C.LOT_SIZE
    net = sum(leg.qty * fill for leg, fill in zip(legs, fills))
    payoff_loss = ST.max_loss_points(name, net) * C.LOT_SIZE
    return {
        "legs": legs, "fills": fills, "entry_net_pts": net,
        "entry_charges_rs": charges,
        "cost_reserve_rs": charges + close_reserve + C.RISK_COST_BUFFER_RS,
        "payoff_max_loss_rs": payoff_loss,
        "risk_estimate_rs": payoff_loss + charges + close_reserve + C.RISK_COST_BUFFER_RS,
    }


def entry_filter(name, quote, profile=None):
    if (profile or C.ALGORITHM) == "legacy":
        return None
    if ST.KIND[name] == "debit_vertical":
        debit = quote["entry_net_pts"]
        if not math.isfinite(debit) or not 0 < debit < C.SPREAD_WIDTH:
            return "invalid_debit"
        reward = (C.SPREAD_WIDTH - debit) * C.LOT_SIZE - quote["cost_reserve_rs"]
        if reward / quote["risk_estimate_rs"] < C.MIN_DEBIT_REWARD_RISK:
            return "insufficient_debit_reward"
        return None
    credit = -quote["entry_net_pts"]
    if not math.isfinite(credit) or not 0 < credit < C.SPREAD_WIDTH:
        return "invalid_credit"
    if credit / C.SPREAD_WIDTH < C.MIN_CREDIT_WIDTH_RATIO:
        return "insufficient_credit"
    return None


def size_position(equity, peak_equity, risk_per_lot, halted=False):
    """Size using estimated full spread loss plus costs, never a stop-loss amount."""
    if not all(math.isfinite(v) for v in (equity, peak_equity, risk_per_lot)):
        return 0, "invalid_risk_inputs"
    if halted or equity <= 0 or peak_equity <= 0 or equity <= peak_equity * (1 - C.MAX_ACCOUNT_DRAWDOWN):
        return 0, "drawdown_halt"
    if risk_per_lot <= 0:
        return 0, "invalid_risk_inputs"
    if not 0 < C.RISK_PER_TRADE <= 1 or C.MAX_LOTS < 1:
        raise ValueError("RISK_PER_TRADE must be in (0, 1] and MAX_LOTS must be positive")
    lots = min(C.MAX_LOTS, math.floor(equity * C.RISK_PER_TRADE / risk_per_lot))
    return lots, "sized" if lots else "one_lot_exceeds_risk_budget"
