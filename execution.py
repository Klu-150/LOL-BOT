"""Shared daily mark and model exit fills for historical and paper positions."""
import costs
import pricing
import strategies as ST
import algorithm


def evaluate_position(name, legs, fills, entry_net, spot, iv, day, expiries, event_day=None,
                      market_row=None, profile=None):
    front = expiries["front"]
    if day > front:
        raise ValueError(f"Missing expiry close for {front}; cannot settle using a later spot")
    is_expiry = day == front
    mids = [pricing.price(spot, leg.K, max((expiries[leg.expiry] - day).days, 0) / 365, iv, leg.cp)
            for leg in legs]
    mid_pnl = sum(leg.qty * (mid - fill) for leg, mid, fill in zip(legs, mids, fills))
    reason = "expiry" if is_expiry else ST.exit_signal(name, mid_pnl, entry_net)
    if not reason and market_row is not None:
        reason = algorithm.invalidation(name, market_row, profile)
    if not reason and event_day and ST.KIND[name] == "straddle" and day >= event_day:
        reason = "event_passed"
    exit_fills, charges = [], 0.0
    for leg, mid in zip(legs, mids):
        if leg.expiry == "front" and is_expiry:
            price = mid
            if leg.qty > 0 and mid > 0:
                charges += costs.exercise_stt(mid)
        else:
            slip = costs.slippage(mid)
            price = max(0.0, mid - slip) if leg.qty > 0 else mid + slip
            charges += costs.order_charges(price, "sell" if leg.qty > 0 else "buy")
        exit_fills.append(price)
    return {
        "exit_reason": reason, "mid_pnl_pts": mid_pnl,
        "exit_fills": exit_fills, "exit_charges_rs": charges,
        "pnl_pts": sum(leg.qty * (px - fill) for leg, px, fill in zip(legs, exit_fills, fills)),
    }
