"""Which option structure best expresses the adaptive engine's swing signals?

python -m pro.options_research
Every structure trades the same entry/exit dates chosen by the engine, one lot,
priced with the configured Black-Scholes + skew model on India VIX, with
per-leg slippage and statutory charges. Option prices are modelled, not quotes.
"""
import math

import pandas as pd

import config as C
import costs
import pricing
from pro import engine, features

STRUCTURES = {
    # name: (description, builder(S, T, iv) -> [(cp, K, qty)], dte_days)
    "atm_call_debit_28d": "Buy ATM call / sell +300 call, 28 DTE",
    "itm_call_debit_56d": "Buy 0.70-delta call / sell 0.30-delta call, 56 DTE",
    "deep_itm_call_56d": "Buy 0.80-delta call, 56 DTE (futures-like, defined risk)",
    "bull_put_credit_35d": "Sell 0.30-delta put / buy put 300 lower, 35 DTE",
    "futures": "Nifty futures, one lot (benchmark, undefined risk)",
}
DTE = {"atm_call_debit_28d": 28, "itm_call_debit_56d": 56, "deep_itm_call_56d": 56, "bull_put_credit_35d": 35}


def legs(name, S, T, iv):
    if name == "atm_call_debit_28d":
        k = pricing.round_strike(S)
        return [("C", k, 1), ("C", k + 300, -1)]
    if name == "itm_call_debit_56d":
        return [("C", pricing.strike_for_delta(S, T, iv, "C", 0.70), 1),
                ("C", pricing.strike_for_delta(S, T, iv, "C", 0.30), -1)]
    if name == "deep_itm_call_56d":
        return [("C", _itm_call(S, T, iv, 0.80), 1)]
    if name == "bull_put_credit_35d":
        k = pricing.strike_for_delta(S, T, iv, "P", 0.30)
        return [("P", k, -1), ("P", k - 300, 1)]
    raise ValueError(name)


def _itm_call(S, T, iv, target):
    k = pricing.round_strike(S)
    while pricing.delta(S, k, T, iv, "C") < target and k > S * 0.7:
        k -= C.STRIKE_STEP
    return k


def _trade(ls, S, T, iv, opening):
    """Cash flow per unit (+ received) and rupee charges per lot."""
    cash, fees = 0.0, 0.0
    for cp, k, q in ls:
        mid = pricing.price(S, k, T, iv, cp)
        buy = (q > 0) == opening
        px = mid + costs.slippage(mid) if buy else max(0.0, mid - costs.slippage(mid))
        cash += -px if buy else px
        fees += costs.order_charges(px, "buy" if buy else "sell")
    return cash, fees


ROLL_DAYS_LEFT = 7


def _held_with_rolls(f, t, name, dte):
    """Open at entry; roll to a fresh contract (same rules) with 7 days left; close at exit."""
    total, start_px, start_date = 0.0, t.entry_px, t.entry_date
    vix_open = f.loc[t.signal_date].VIX / 100
    while True:
        expiry_hold = dte - ROLL_DAYS_LEFT
        roll_date = start_date + pd.Timedelta(days=expiry_hold)
        ls = legs(name, start_px, dte / 365, vix_open)
        open_cash, f0 = _trade(ls, start_px, dte / 365, vix_open, True)
        if roll_date >= t.exit_date:
            x = f.loc[t.exit_date]
            left = max(dte - (t.exit_date - start_date).days, 1) / 365
            close_cash, f1 = _trade(ls, t.exit_px, left, x.VIX / 100, False)
            return total + (open_cash + close_cash) * C.LOT_SIZE - f0 - f1
        d = f.index[f.index.searchsorted(roll_date)]  # first session on/after the roll date
        r = f.loc[d]
        left = max(dte - (d - start_date).days, 1) / 365
        close_cash, f1 = _trade(ls, r.Close, left, r.VIX / 100, False)
        total += (open_cash + close_cash) * C.LOT_SIZE - f0 - f1
        start_px, start_date, vix_open = float(r.Close), d, r.VIX / 100


def evaluate(f, chosen):
    rows = []
    for t in chosen:
        if t.exit_date is None or t.side < 0:
            continue
        e, x = f.loc[t.signal_date], f.loc[t.exit_date]
        days = (t.exit_date - t.entry_date).days
        rec = {"entry": t.entry_date, "exit": t.exit_date, "strategy": t.strategy, "days": days,
               "futures": (t.exit_px - t.entry_px - 2 * engine.COST_PTS) * C.LOT_SIZE}
        for name, dte in DTE.items():
            rec[name] = _held_with_rolls(f, t, name, dte)
        rows.append(rec)
    return pd.DataFrame(rows)


def summary(df):
    out = {}
    for name in ["futures", *DTE]:
        x = df[name].dropna()
        wins, losses = x[x > 0].sum(), -x[x < 0].sum()
        early = x[df.entry.loc[x.index] < "2023-01-01"].sum()
        late = x[df.entry.loc[x.index] >= "2023-01-01"].sum()
        curve = x.cumsum()
        out[name] = {"structure": STRUCTURES[name], "trades": len(x), "win_%": round(100 * (x > 0).mean(), 1),
                     "total_rs_per_lot": round(x.sum()), "2016-22": round(early), "2023-26": round(late),
                     "profit_factor": round(wins / losses, 2) if losses else math.inf,
                     "worst_trade_rs": round(x.min()), "max_dd_rs": round((curve - curve.cummax()).min())}
    return pd.DataFrame(out).T


def run(start="2016-01-01"):
    f = features.load()
    trades = engine.all_trades(f)
    chosen, _ = engine.select(f, trades)
    chosen = [t for t in chosen if t.entry_date >= pd.Timestamp(start)]
    return summary(evaluate(f, chosen))


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    print(run().to_string())
