"""Standalone strategy simulation, walk-forward selector and options account.

Timing (no look-ahead): signal on day t close -> fill at day t+1 open.
Stops are checked against each held day's low/high and fill at the worse of the
stop and that day's open (gap-through). Exit signals at close fill next open.
"""
from dataclasses import dataclass, asdict
import math

import numpy as np
import pandas as pd

import config as C
import costs
import pricing
from pro.strategies import LIBRARY

COST_PTS = 1.5          # per side, index points (slippage + charges proxy)
LOOKBACK_DAYS = 756     # ~3 years of completed trades feed the selector
MIN_TRADES = 5          # minimum regime-specific evidence before trusting a strategy
MIN_EXPECTANCY_R = 0.05  # average result per trade, in units of initial risk
RISK_PER_TRADE = 0.02
MAX_LOTS = 5
SPREAD_DTE = 28         # calendar days to expiry of the spread bought at entry
SPREAD_WIDTH = 300


@dataclass
class Trade:
    strategy: str
    side: int
    regime: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_px: float
    stop_pts: float
    exit_date: pd.Timestamp | None = None
    exit_px: float | None = None
    exit_reason: str | None = None
    pts: float | None = None
    r: float | None = None


def simulate(f: pd.DataFrame, strat, cost=COST_PTS):
    """All trades a strategy takes when run on its own. Last trade may be open."""
    rows, idx, trades = list(f.itertuples()), f.index, []
    pos, pending_entry, pending_exit = None, None, None
    for i, r in enumerate(rows):
        if pending_exit and pos:
            _close(pos, idx[i], r.Open, pending_exit, cost)
            trades.append(pos)
            pos, pending_exit = None, None
        if pending_entry and pos is None:
            side, reg, sig = pending_entry
            stop_pts = strat.stop_atr * rows[i - 1].atr
            pos = Trade(strat.name, side, reg, sig, idx[i], r.Open, stop_pts)
            pos._stop = r.Open - side * stop_pts
            pos._best = r.Open
            pos._held = 0
        pending_entry = None
        if pos:
            pos._held += 1
            hit = (r.Low <= pos._stop) if pos.side > 0 else (r.High >= pos._stop)
            if hit:
                px = min(r.Open, pos._stop) if pos.side > 0 else max(r.Open, pos._stop)
                _close(pos, idx[i], px, "stop", cost)
                trades.append(pos)
                pos = None
            else:
                if strat.trail:
                    pos._best = max(pos._best, r.Close) if pos.side > 0 else min(pos._best, r.Close)
                    trail = pos._best - pos.side * strat.stop_atr * r.atr
                    pos._stop = max(pos._stop, trail) if pos.side > 0 else min(pos._stop, trail)
                if strat.exit(r, pos.side, pos._held):
                    pending_exit = "signal"
                elif pos._held >= strat.max_hold:
                    pending_exit = "time"
        if pos is None and i + 1 < len(rows) and _tradeable(r):
            side = strat.entry(r)
            if side:
                pending_entry = (side, r.regime, idx[i])
    if pos:
        trades.append(pos)  # still open at the last bar
    return trades


def _tradeable(r):
    return r.regime != "warmup" and math.isfinite(r.atr) and not np.isnan(r.vix_rank)


def _close(t, date, px, reason, cost):
    t.exit_date, t.exit_px, t.exit_reason = date, float(px), reason
    t.pts = t.side * (t.exit_px - t.entry_px) - 2 * cost
    t.r = t.pts / t.stop_pts


def all_trades(f):
    out = []
    for s in LIBRARY:
        out += simulate(f, s)
    return out


def scoreboard(closed, regime, asof, idx):
    """Rank strategies on trades in `regime` that had fully closed before `asof`."""
    start = idx[max(0, idx.get_loc(asof) - LOOKBACK_DAYS)]
    rows = {}
    for t in closed:
        if t.exit_date is None or t.exit_date >= asof or t.signal_date < start or t.regime != regime:
            continue
        rows.setdefault(t.strategy, []).append(t.r)
    board = {}
    for name, rs in rows.items():
        rs = np.array(rs)
        wins, losses = rs[rs > 0].sum(), -rs[rs < 0].sum()
        board[name] = {"trades": len(rs), "expectancy_r": float(rs.mean()),
                       "win_rate": float((rs > 0).mean()),
                       "profit_factor": float(wins / losses) if losses else float("inf"),
                       "score": float(rs.mean() * math.sqrt(len(rs)) / (rs.std() + 0.25))}
    return board


# Regime playbook (design rule, not fitted): trade WITH the trend, stand aside otherwise.
# Shorts, range fading and panic buying were tested and rejected (see STRATEGY_GUIDE.md).
PLAYBOOK = {
    "uptrend": [("trend_pullback", 1), ("channel_breakout", 1), ("trend_rider", 1)],
    # Price has reclaimed EMA200 but EMA50 still lags: only a confirmed 55-day breakout.
    "transition": [("channel_breakout", 1)],
    "range": [], "downtrend": [], "stress": [], "warmup": [],
}
KILL_MIN_TRADES = 8
KILL_EXPECTANCY_R = -0.10


def eligible(board, allowed):
    """Allowed strategies, minus any whose recent regime record is clearly broken."""
    out = {}
    for rank, (name, side) in enumerate(allowed):
        ev = board.get(name)
        if ev and ev["trades"] >= KILL_MIN_TRADES and ev["expectancy_r"] <= KILL_EXPECTANCY_R:
            continue  # kill switch: this edge has stopped working lately
        enough = ev and ev["trades"] >= MIN_TRADES
        out[(name, side)] = {**(ev or {"trades": 0}), "priority": rank,
                             "rank_key": (ev["score"] if enough else 0.0, -rank)}
    return out


def select(f, trades):
    """Adaptive meta-strategy: one position at a time, chosen by regime + walk-forward evidence."""
    by_signal = {}
    for t in trades:
        by_signal.setdefault(t.signal_date, []).append(t)
    chosen, decisions, busy_until = [], [], None
    for d, r in f.iterrows():
        if busy_until is not None and (pd.isna(busy_until) or d < busy_until):
            continue
        busy_until = None
        fired = by_signal.get(d, [])
        if not fired:
            continue
        if r.event_next:
            decisions.append({"date": d, "regime": r.regime, "action": "veto_event"})
            continue
        board = eligible(scoreboard(trades, r.regime, d, f.index), PLAYBOOK.get(r.regime, []))
        ranked = sorted((t for t in fired if (t.strategy, t.side) in board),
                        key=lambda t: board[(t.strategy, t.side)]["rank_key"], reverse=True)
        if not ranked:
            decisions.append({"date": d, "regime": r.regime, "action": "stand_aside",
                              "fired": [t.strategy for t in fired]})
            continue
        pick = ranked[0]
        chosen.append(pick)
        ev = board[(pick.strategy, pick.side)]
        decisions.append({"date": d, "regime": r.regime, "action": "take", "strategy": pick.strategy,
                          "side": pick.side, **{f"evidence_{k}": v for k, v in ev.items() if k != "rank_key"}})
        busy_until = pick.exit_date if pick.exit_date is not None else pd.NaT
    return chosen, decisions


# ----------------------------------------------------------------------------
# Options account: express each chosen signal as a defined-risk debit spread.
# ----------------------------------------------------------------------------
def spread_value(S, K_long, K_short, cp, T, vix):
    iv = vix / 100
    return pricing.price(S, K_long, T, iv, cp) - pricing.price(S, K_short, T, iv, cp)


def option_account(f, chosen, capital=C.PAPER_CAPITAL):
    equity, rows = float(capital), []
    for t in chosen:
        if t.exit_date is None:
            continue
        cp = "C" if t.side > 0 else "P"
        e, x = f.loc[t.entry_date], f.loc[t.exit_date]
        k_long = pricing.round_strike(t.entry_px)
        k_short = k_long + t.side * SPREAD_WIDTH
        T0 = SPREAD_DTE / 365
        T1 = max(SPREAD_DTE - (t.exit_date - t.entry_date).days, 1) / 365
        legs0 = [pricing.price(t.entry_px, k, T0, e.VIX / 100, cp) for k in (k_long, k_short)]
        legs1 = [pricing.price(t.exit_px, k, T1, x.VIX / 100, cp) for k in (k_long, k_short)]
        buy_long, sell_short = legs0[0] + costs.slippage(legs0[0]), max(0, legs0[1] - costs.slippage(legs0[1]))
        sell_long, buy_short = max(0, legs1[0] - costs.slippage(legs1[0])), legs1[1] + costs.slippage(legs1[1])
        debit = buy_long - sell_short
        fees = (costs.order_charges(buy_long, "buy") + costs.order_charges(sell_short, "sell")
                + costs.order_charges(sell_long, "sell") + costs.order_charges(buy_short, "buy"))
        lots = min(MAX_LOTS, math.floor(equity * RISK_PER_TRADE / (debit * C.LOT_SIZE + fees)))
        if lots < 1:
            continue
        pnl_pts = (sell_long - buy_short) - debit
        pnl = (pnl_pts * C.LOT_SIZE - fees) * lots
        equity += pnl
        rows.append({"strategy": t.strategy, "side": t.side, "entry": t.entry_date.date(), "exit": t.exit_date.date(),
                     "strikes": f"{int(k_long)}/{int(k_short)}{cp}", "lots": lots, "debit_pts": round(debit, 1),
                     "pnl_rs": round(pnl, 0), "equity_rs": round(equity, 0)})
    return pd.DataFrame(rows), equity


ETF_COST_PCT = 0.0010   # per side: brokerage/STT/impact proxy for an index ETF
ETF_RISK = 0.01          # risk 1% of equity to the stop; never more than 100% invested


def index_account(f, chosen, capital=C.PAPER_CAPITAL):
    """Unleveraged index-ETF account (e.g. NIFTYBEES) sized by stop distance."""
    equity, rows = float(capital), []
    for t in chosen:
        if t.exit_date is None:
            continue
        units = min(equity * ETF_RISK / t.stop_pts, equity / t.entry_px)
        gross = units * t.side * (t.exit_px - t.entry_px)
        fees = ETF_COST_PCT * units * (t.entry_px + t.exit_px)
        equity += gross - fees
        rows.append({"strategy": t.strategy, "entry": t.entry_date.date(), "exit": t.exit_date.date(),
                     "exposure_%": round(100 * units * t.entry_px / (equity - gross + fees), 0),
                     "pnl_rs": round(gross - fees, 0), "equity_rs": round(equity, 0), "reason": t.exit_reason})
    return pd.DataFrame(rows), equity


def trades_frame(trades):
    rows = []
    for t in trades:
        d = asdict(t)
        rows.append(d)
    return pd.DataFrame(rows)
