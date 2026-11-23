"""Causal 15m/5m options paper engine. Option prices and fills are modelled."""
from dataclasses import asdict
from datetime import datetime, time, timedelta
import math

import numpy as np
import pandas as pd

import algorithm
import config as C
import costs
from data import ROOT, load_events
import pricing
import regime
import risk
import strategies as ST

ZONE = "Asia/Kolkata"


def features(bars, daily_vix=None):
    bars = bars.copy()
    if daily_vix is None:
        daily_vix = pd.read_csv(ROOT / C.VIX_CSV, parse_dates=["Date"]).set_index("Date")["Close"]
    # Only a full three-bar group becomes a 15-minute observation.
    grouped = bars.resample("15min", origin="start_day", offset="9h15min", closed="right", label="right")
    higher = grouped.agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
    higher = higher.loc[grouped["Close"].count().eq(3)].dropna()
    higher["ema_fast"] = higher.Close.ewm(span=20, adjust=False, min_periods=50).mean()
    higher["ema_slow"] = higher.Close.ewm(span=50, adjust=False, min_periods=50).mean()
    higher["adx"] = regime.adx(higher)
    higher["bias_timestamp"] = higher.index
    higher["bias_close"] = higher["Close"]
    out = bars.join(higher[["ema_fast", "ema_slow", "adx", "bias_timestamp", "bias_close"]].reindex(bars.index, method="ffill"))
    out["bias_age_minutes"] = (out.index.to_series() - out.bias_timestamp).dt.total_seconds() / 60
    out["trigger_fast"] = bars.Close.ewm(span=20, adjust=False, min_periods=20).mean()
    out["trigger_slow"] = bars.Close.ewm(span=50, adjust=False, min_periods=50).mean()
    returns = np.log(bars.Close / bars.Close.shift(1))
    same_session = bars.index.to_series().dt.date.eq(bars.index.to_series().shift(1).dt.date)
    out["realized_vol"] = returns.where(same_session).rolling(75, min_periods=50).std() * np.sqrt(252 * 75) * 100
    if "VIX" not in out:
        out["VIX"] = np.nan
    out["ivr"] = np.nan
    out["vix_source"] = "intraday observation"
    for session in sorted(set(bars.index.date)):
        prior = daily_vix.loc[daily_vix.index.date < session].dropna().iloc[-C.IVR_LOOKBACK:]
        mask = out.index.date == session
        if len(prior) < C.IVR_LOOKBACK // 2:
            continue
        missing = mask & out.VIX.isna()
        # A historical daily close is never borrowed from the current/future session.
        age = (session - prior.index[-1].date()).days
        if age <= 4:
            out.loc[missing, "VIX"] = float(prior.iloc[-1])
            out.loc[missing, "vix_source"] = f"prior-day proxy ({prior.index[-1].date()})"
        if prior.max() > prior.min():
            out.loc[mask, "ivr"] = ((out.loc[mask, "VIX"] - prior.min()) / (prior.max() - prior.min()) * 100).clip(0, 100)
    out["iv_rv_ratio"] = out.VIX / out.realized_vol.replace(0, np.nan)
    out["vix_observed"] = out.VIX.notna()
    out["shock"] = out.VIX >= C.VIX_SHOCK
    event_dates = set(load_events())
    out["event"] = [ts.date() in event_dates for ts in out.index]
    return out


def new_state(capital, started_at=None):
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Virtual capital must be finite and positive")
    return {"bot_name": C.BOT_NAME, "algorithm": "adaptive_intraday", "mode": "intraday_modelled_paper",
            "initial_capital": float(capital), "equity": float(capital), "peak_equity": float(capital),
            "halted": False, "position": None, "session": None, "session_equity": float(capital),
            "daily_entries": 0, "last_exit": None, "last_timestamp": None, "started_at": started_at}


def expiry_timestamp(ts):
    target = 3 if ts.date() < C.EXPIRY_SWITCH_DATE else 1
    day = ts.date()
    while day.weekday() != target:
        day += timedelta(days=1)
    return pd.Timestamp(datetime.combine(day, time(15, 30)), tz=ZONE)


def mark(position, row, ts):
    remaining = max((pd.Timestamp(position["expiry"]) - ts).total_seconds(), 60) / (365 * 86400)
    if not math.isfinite(float(row.VIX)) or row.VIX <= 0:
        raise ValueError("Cannot value a position without a current or explicitly labelled VIX proxy")
    pnl_pts, fees, fills = 0.0, 0.0, []
    for leg, initial in zip(position["legs"], position["fills"]):
        mid = pricing.price(float(row.Close), leg["K"], remaining, float(row.VIX) / 100, leg["cp"])
        fill = max(0, mid - costs.slippage(mid)) if leg["qty"] > 0 else mid + costs.slippage(mid)
        fees += costs.order_charges(fill, "sell" if leg["qty"] > 0 else "buy")
        pnl_pts += leg["qty"] * (fill - initial)
        fills.append(fill)
    lots = position["lots"]
    return {"pnl_pts": pnl_pts, "gross_rs": pnl_pts * C.LOT_SIZE * lots,
            "exit_charges_rs": fees * lots, "exit_fills": fills,
            "net_pnl_rs": (pnl_pts * C.LOT_SIZE - fees - position["entry_charges_rs"]) * lots}


def bias_row(row):
    higher = row.copy()
    if pd.notna(row.get("bias_close")):
        higher["Close"] = row["bias_close"]
    return higher


def decision(row):
    if row.get("bias_age_minutes", 999) > 20:
        return algorithm.Decision(None, "missing_completed_15m_bias")
    return algorithm.select(bias_row(row), bool(row.get("event", False)), "adaptive_regime")


def step(state, row, ts, allow_entry=True):
    """One closed 5-minute bar; one position; exits have priority over new entries."""
    session = str(ts.date())
    if state["session"] != session:
        if state["position"]:
            raise ValueError("Previous session has an unresolved position: restore its square-off bars before trading again")
        state.update(session=session, session_equity=state["equity"], daily_entries=0)
    pick = decision(row)
    event = {"timestamp": ts.isoformat(), "action": "skip", "reason": pick.reason,
             "condition": pick.condition, "volatility": pick.volatility, "candidate": pick.strategy,
             "spot": float(row.Close), "vix": float(row.VIX) if pd.notna(row.VIX) else None,
             "vix_source": str(row.get("vix_source", "unavailable"))}
    closed = None
    position = state["position"]
    if position:
        value = mark(position, row, ts)
        position["mark"] = value
        current = ts.strftime("%H:%M")
        reason = "session_square_off" if current >= C.INTRADAY_EXIT_TIME else ST.exit_signal(position["strategy"], value["pnl_pts"], position["entry_net_pts"])
        reason = reason or algorithm.invalidation(position["strategy"], bias_row(row), "adaptive_regime")
        if reason:
            state["equity"] += value["gross_rs"] - value["exit_charges_rs"]
            closed = {**position, "exit": ts.isoformat(), "exit_reason": reason, **value,
                      "pnl_rs": value["net_pnl_rs"] / position["lots"],
                      "charges_rs": (value["exit_charges_rs"] / position["lots"]) + position["entry_charges_rs"]}
            state.update(position=None, last_exit=ts.isoformat())
            event.update(action="close", reason=reason, net_pnl_rs=value["net_pnl_rs"])
        else:
            event.update(action="hold", reason="position_open")
    else:
        stamp = ts.strftime("%H:%M")
        reason = None
        if not C.INTRADAY_ENTRY_START <= stamp <= C.INTRADAY_ENTRY_END:
            reason = "outside_entry_window"
        elif not allow_entry:
            reason = "missed_or_stale_bar_no_entry"
        elif state["halted"]:
            reason = "drawdown_halt"
        elif state["daily_entries"] >= C.INTRADAY_MAX_TRADES:
            reason = "daily_trade_limit"
        elif state["last_exit"] and (ts - pd.Timestamp(state["last_exit"])).total_seconds() < C.INTRADAY_COOLDOWN_MINUTES * 60:
            reason = "cooldown"
        elif not pick.strategy:
            reason = pick.reason
        elif pick.strategy.startswith("bull_") and not row.Close > row.trigger_fast >= row.trigger_slow:
            reason = "waiting_for_5m_bullish_trigger"
        elif pick.strategy.startswith("bear_") and not row.Close < row.trigger_fast <= row.trigger_slow:
            reason = "waiting_for_5m_bearish_trigger"
        if reason is None:
            years = max((expiry_timestamp(ts) - ts).total_seconds(), 60) / (365 * 86400)
            quote = risk.entry_quote(pick.strategy, float(row.Close), years, float(row.VIX) / 100)
            reason = risk.entry_filter(pick.strategy, quote, "adaptive_regime")
            lots, sizing = risk.size_position(state["equity"], state["peak_equity"], quote["risk_estimate_rs"], state["halted"])
            daily_remaining = state["session_equity"] * C.INTRADAY_DAILY_LOSS_LIMIT + state["equity"] - state["session_equity"]
            lots = min(lots, max(0, math.floor(daily_remaining / quote["risk_estimate_rs"])))
            if not reason and not lots:
                reason = "daily_risk_budget" if daily_remaining < quote["risk_estimate_rs"] else sizing
            if not reason:
                quote["legs"] = [asdict(leg) for leg in quote["legs"]]
                state["position"] = {**quote, "strategy": pick.strategy, "entry": ts.isoformat(),
                                     "expiry": expiry_timestamp(ts).isoformat(), "lots": lots,
                                     "condition": pick.condition, "volatility": pick.volatility,
                                     "spot_entry": float(row.Close), "vix_entry": float(row.VIX),
                                     "vix_source": event["vix_source"], "policy": "adaptive_intraday"}
                state["equity"] -= quote["entry_charges_rs"] * lots
                state["daily_entries"] += 1
                state["position"]["mark"] = mark(state["position"], row, ts)
                event.update(action="open", reason=pick.reason, lots=lots, strategy=pick.strategy)
        if reason:
            event["reason"] = reason
    state["peak_equity"] = max(state["peak_equity"], state["equity"])
    state["halted"] = state["halted"] or state["equity"] <= state["peak_equity"] * (1 - C.MAX_ACCOUNT_DRAWDOWN)
    state["last_timestamp"] = ts.isoformat()
    event.update(equity_rs=state["equity"], halted=state["halted"])
    return event, closed
