"""
Weekly options backtest engine.

Each week:
  1. At the close of the previous expiry day, classify the regime.
  2. Simulate EVERY strategy for that week (so we can compare them),
     priced with Black-Scholes using that day's India VIX + skew.
  3. Walk forward day by day: re-price at each close, apply exit rules,
     otherwise settle at expiry (cash, intrinsic value).
  4. The "regime bot" takes whichever strategy the playbook picks.
"""
from datetime import date

import numpy as np
import pandas as pd

import config as C
from execution import evaluate_position
import regime
import strategies as ST
import algorithm
import risk
from data import first_event_in, load_events, load_market, weekly_expiries


def _years(d_from: date, d_to: date) -> float:
    return max((d_to - d_from).days, 0) / 365.0


def simulate_trade(name, mkt, entry_day, front, back, event_day=None, profile=None, features=None):
    """Simulate one strategy for one week. Returns a dict (per 1 lot)."""
    S0 = float(mkt.at[pd.Timestamp(entry_day), "Close"])
    iv0 = float(mkt.at[pd.Timestamp(entry_day), "VIX"]) / 100.0
    exp_of = {"front": front, "back": back}
    if back is None and name == "calendar":
        return None

    quote = risk.entry_quote(name, S0, _years(entry_day, front), iv0,
                             _years(entry_day, back) if back else None)
    legs, fills = quote["legs"], quote["fills"]
    charges = quote["entry_charges_rs"]
    entry_net = quote["entry_net_pts"]
    if profile == "adaptive_regime" and features is None:
        features = regime.add_features(mkt)

    # ---- walk forward
    path = mkt.loc[pd.Timestamp(entry_day):pd.Timestamp(front)].iloc[1:]
    exit_day, reason, pnl_pts = None, None, 0.0
    for ts, row in path.iterrows():
        d = ts.date()
        S, iv = float(row["Close"]), float(row["VIX"]) / 100.0
        daily_features = features.loc[ts] if features is not None else None
        mark = evaluate_position(name, legs, fills, entry_net, S, iv, d, exp_of, event_day,
                                 market_row=daily_features, profile=profile)
        if mark["exit_reason"] is None:
            continue
        pnl_pts = mark["pnl_pts"]
        charges += mark["exit_charges_rs"]
        exit_day, reason = d, mark["exit_reason"]
        break

    if exit_day is None:  # data ended before expiry
        return None

    pnl_rs = pnl_pts * C.LOT_SIZE - charges
    return {
        "strategy": name,
        "policy": profile or "always_on",
        "entry": entry_day,
        "exit": exit_day,
        "exit_reason": reason,
        "spot_entry": S0,
        "vix_entry": iv0 * 100,
        "legs": "; ".join(f"{'+' if l.qty > 0 else '-'}{int(l.K)}{l.cp}({l.expiry[0]})" for l in legs),
        "entry_net_pts": entry_net,
        "max_loss_rs": ST.max_loss_points(name, entry_net) * C.LOT_SIZE,
        "risk_estimate_rs": quote["risk_estimate_rs"],
        "pnl_pts": pnl_pts,
        "charges_rs": charges,
        "pnl_rs": pnl_rs,
    }


def run():
    mkt = load_market()
    feat = regime.classify(regime.add_features(mkt))
    events = load_events()
    expiries = weekly_expiries(mkt.index)
    start = C.BACKTEST_START
    end = C.BACKTEST_END or mkt.index[-1].date()

    trades, weeks = [], []
    for i in range(1, len(expiries)):
        entry, front = expiries[i - 1], expiries[i]
        back = expiries[i + 1] if i + 1 < len(expiries) else None
        if entry < start or front > end:
            continue
        r = feat.loc[pd.Timestamp(entry)]
        if pd.isna(r["ivr"]) or pd.isna(r["adx"]):
            continue
        ev = first_event_in(events, entry, front)
        decision = algorithm.select(r, ev is not None)
        pick, pick_reason = decision.strategy, decision.reason
        if pick:
            quote = risk.entry_quote(pick, float(r["Close"]), _years(entry, front), float(r["VIX"]) / 100)
            rejection = risk.entry_filter(pick, quote)
            if rejection:
                pick, pick_reason = None, rejection
        legacy = algorithm.select(r, ev is not None, "legacy").strategy
        credit_decision = algorithm.select(r, ev is not None, "credit_regime")
        credit_pick = credit_decision.strategy
        if credit_pick and risk.entry_filter(credit_pick, risk.entry_quote(
                credit_pick, float(r["Close"]), _years(entry, front), float(r["VIX"]) / 100), "credit_regime"):
            credit_pick = None
        weeks.append({
            "entry": entry, "front": front, "trend": r["trend"], "iv": r["iv"],
            "shock": r["shock"], "event": ev, "vix": r["VIX"], "ivr": r["ivr"],
            "adx": r["adx"], "spot": r["Close"], "pick": pick,
            "pick_reason": pick_reason, "legacy_pick": legacy,
            "profile": C.ALGORITHM, "credit_pick": credit_pick,
            "condition": decision.condition, "volatility": decision.volatility,
            "realized_vol": r["realized_vol"], "iv_rv_ratio": r["iv_rv_ratio"],
        })
        for name in ST.ALL_STRATEGIES:
            t = simulate_trade(name, mkt, entry, front, back, event_day=ev)
            if t:
                t.update(trend=r["trend"], iv=r["iv"], shock=r["shock"], event=ev is not None)
                trades.append(t)
        if pick and C.ALGORITHM == "adaptive_regime":
            trade = simulate_trade(pick, mkt, entry, front, back, event_day=ev,
                                   profile=C.ALGORITHM, features=feat)
            if trade:
                trade.update(trend=r["trend"], iv=r["iv"], shock=r["shock"], event=ev is not None,
                             condition=decision.condition, volatility=decision.volatility)
                trades.append(trade)

    trades = pd.DataFrame(trades)
    weeks = pd.DataFrame(weeks)
    return mkt, feat, weeks, trades


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
def weekly_pnl(weeks: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """One P&L column per strategy (always-on) + the regime bot, per lot, Rs."""
    benchmark = trades[trades["policy"] == "always_on"]
    wide = benchmark.pivot_table(index="entry", columns="strategy", values="pnl_rs", aggfunc="sum")
    wide = wide.reindex(weeks["entry"]).fillna(0.0)
    for column, key in (("REGIME_BOT", "pick"), ("LEGACY_BOT", "legacy_pick"), ("CREDIT_BOT", "credit_pick")):
        wide[column] = [wide.at[w["entry"], w[key]] if isinstance(w[key], str) and w[key] in wide.columns
                        else 0.0 for _, w in weeks.iterrows()]
    selected = trades[trades["policy"] == "adaptive_regime"].set_index("entry")["pnl_rs"]
    adaptive_mask = weeks["profile"].eq("adaptive_regime").to_numpy()
    if adaptive_mask.any():
        wide.loc[adaptive_mask, "REGIME_BOT"] = selected.reindex(wide.index[adaptive_mask]).fillna(0).to_numpy()
    wide.index = pd.to_datetime(wide.index)
    return wide


def stats(series: pd.Series, traded_mask: pd.Series = None) -> dict:
    s = series.astype(float)
    t = s[traded_mask] if traded_mask is not None else s
    eq = s.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    wins, losses = t[t > 0], t[t < 0]
    pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() != 0 else np.nan
    sd = s.std()
    return {
        "trades": int(len(t)),
        "win_rate_%": 100 * len(wins) / len(t) if len(t) else np.nan,
        "avg_per_trade_rs": t.mean() if len(t) else np.nan,
        "total_rs": s.sum(),
        "worst_trade_rs": t.min() if len(t) else np.nan,
        "best_trade_rs": t.max() if len(t) else np.nan,
        "max_drawdown_rs": dd,
        "profit_factor": pf,
        "sharpe_weekly_ann": (s.mean() / sd) * np.sqrt(52) if sd > 0 else np.nan,
    }


def summary_table(weeks, trades, wide) -> pd.DataFrame:
    rows = {}
    for name in ST.ALL_STRATEGIES:
        available = pd.to_datetime(trades.loc[(trades["strategy"] == name) & (trades["policy"] == "always_on"), "entry"])
        rows[name] = stats(wide[name], wide.index.isin(available))
    traded = weeks.set_index(pd.to_datetime(weeks["entry"]))["pick"].apply(lambda p: isinstance(p, str))
    rows["REGIME_BOT"] = stats(wide["REGIME_BOT"], traded)
    legacy_traded = weeks.set_index(pd.to_datetime(weeks["entry"]))["legacy_pick"].apply(lambda p: isinstance(p, str))
    rows["LEGACY_BOT"] = stats(wide["LEGACY_BOT"], legacy_traded)
    credit_traded = weeks.set_index(pd.to_datetime(weeks["entry"]))["credit_pick"].apply(lambda p: isinstance(p, str))
    rows["CREDIT_BOT"] = stats(wide["CREDIT_BOT"], credit_traded)
    return pd.DataFrame(rows).T


def account_simulation(weeks, trades, capital=None):
    """Non-overlapping weekly positions; risk is decided before future P&L is read.

    Per-lot charges are multiplied with lots (conservative brokerage estimate).
    Equity and drawdown are realised at exits; this is not an intraday risk engine.
    """
    equity = float(C.START_CAPITAL if capital is None else capital)
    if not np.isfinite(equity) or equity <= 0:
        raise ValueError("Starting capital must be finite and positive")
    peak, halted, records = equity, False, []
    lookup = {(t["entry"], t["strategy"], t.get("policy", "always_on")): t for _, t in trades.iterrows()}
    for _, week in weeks.sort_values("entry").iterrows():
        before = equity
        policy = "adaptive_regime" if week.get("profile") == "adaptive_regime" else "always_on"
        trade = lookup.get((week["entry"], week["pick"], policy))
        lots, reason, reserve = 0, week["pick_reason"], 0.0
        if trade is not None:
            reserve = float(trade["risk_estimate_rs"])
            lots, reason = risk.size_position(equity, peak, reserve, halted)
        pnl = float(trade["pnl_rs"]) * lots if lots else 0.0
        equity += pnl
        peak = max(peak, equity)
        halted = halted or equity <= peak * (1 - C.MAX_ACCOUNT_DRAWDOWN)
        records.append({"entry": week["entry"], "exit": trade["exit"] if lots else None,
                        "strategy": week["pick"], "lots": lots, "reason": reason,
                        "risk_budget_rs": before * C.RISK_PER_TRADE,
                        "reserved_risk_rs": reserve * lots, "pnl_rs": pnl,
                        "equity_rs": equity, "drawdown_pct": 100 * (1 - equity / peak),
                        "halted": halted})
    return pd.DataFrame(records)


def period_evaluation(weeks, wide):
    """Fixed chronological split, no optimisation or automatic winner selection."""
    split = pd.Timestamp(C.EVALUATION_SPLIT)
    masks = {"development": wide.index < split, "later_period": wide.index >= split}
    # Exclude positions crossing the split from development to avoid outcome leakage.
    settled_before = pd.to_datetime(weeks["front"]).to_numpy() < split.to_datetime64()
    masks["development"] &= settled_before
    picks = weeks.set_index(pd.to_datetime(weeks["entry"]))
    rows = []
    for period, mask in masks.items():
        for name, key in (("REGIME_BOT", "pick"), ("LEGACY_BOT", "legacy_pick")):
            values = wide.loc[mask, name]
            traded = picks.loc[values.index, key].apply(lambda p: isinstance(p, str))
            rows.append({"period": period, "algorithm": name, "weeks": len(values),
                         **stats(values, traded)})
    return pd.DataFrame(rows)


def regime_matrix(trades: pd.DataFrame) -> pd.DataFrame:
    """Average Rs per lot for each strategy inside each regime (no events/shock)."""
    t = trades[(~trades["event"]) & (~trades["shock"])].copy()
    t = t[t["policy"] == "always_on"]
    t["regime"] = t["trend"] + " | " + t["iv"]
    avg = t.pivot_table(index="regime", columns="strategy", values="pnl_rs", aggfunc="mean")
    n = t[t["strategy"] == ST.ALL_STRATEGIES[0]].groupby("regime").size().rename("weeks")
    return avg.join(n)


def by_year(series: pd.Series) -> pd.Series:
    return series.groupby(series.index.year).sum()
