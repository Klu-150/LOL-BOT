from datetime import date
import json

import numpy as np
import pandas as pd
import pytest

import algorithm
import backtest as B
import config as C
from data import load_market
from live_signal import latest_signal, record_signal
import regime
import risk
import strategies as ST


def market_row(**overrides):
    row = dict(Close=25000, VIX=20, ivr=55, adx=30, ema_fast=24900,
               ema_slow=24800, realized_vol=15, iv_rv_ratio=20 / 15,
               trend="strong_up", iv="high", shock=False, vix_observed=True)
    return {**row, **overrides}


@pytest.mark.parametrize("updates,event,expected", [
    ({}, False, "bull_put_spread"),
    ({"Close": 24500, "ema_fast": 24600}, False, "bear_call_spread"),
    ({"adx": 15}, False, "iron_condor"),
    ({"ivr": 15}, False, None),
    ({"iv_rv_ratio": 1.05}, False, None),
    ({"shock": True}, False, None),
    ({}, True, None),
    ({"ema_fast": 25100}, False, None),
    ({"realized_vol": np.nan}, False, None),
    ({"vix_observed": False}, False, None),
])
def test_policy_regimes_and_vetoes(updates, event, expected):
    assert algorithm.select(market_row(**updates), event).strategy == expected


def test_legacy_remains_available():
    row = market_row(iv="low")
    assert algorithm.select(row, profile="legacy").strategy == "bull_call_spread"
    with pytest.raises(ValueError):
        algorithm.select(row, profile="unrecognised")


@pytest.mark.parametrize("name", ["bull_put_spread", "bear_call_spread", "iron_condor"])
def test_hedges_bound_expiry_payoff_and_reserve_costs(name):
    quote = risk.entry_quote(name, 25000, 7 / 365, 0.20)
    import pricing
    payoffs = [sum(l.qty * pricing.intrinsic(s, l.K, l.cp) for l in quote["legs"])
               - quote["entry_net_pts"] for s in np.linspace(20000, 30000, 1001)]
    assert -min(payoffs) * C.LOT_SIZE == pytest.approx(quote["payoff_max_loss_rs"])
    assert quote["risk_estimate_rs"] > quote["payoff_max_loss_rs"]
    assert all(l.expiry == "front" for l in quote["legs"])


def test_minimum_credit_gate():
    assert risk.entry_filter("bull_put_spread", {"entry_net_pts": -1}) == "insufficient_credit"
    assert risk.entry_filter("bull_put_spread", {"entry_net_pts": 5}) == "invalid_credit"
    assert risk.entry_filter("bull_put_spread", {"entry_net_pts": -300}) == "invalid_credit"


def test_sizing_never_rounds_up_and_caps_lots():
    assert risk.size_position(20000, 20000, 10000) == (0, "one_lot_exceeds_risk_budget")
    lots, _ = risk.size_position(1000000, 1000000, 9000)
    assert lots == 2 and lots * 9000 <= 1000000 * C.RISK_PER_TRADE
    assert risk.size_position(10000000, 10000000, 1000)[0] == C.MAX_LOTS
    assert risk.size_position(84000, 100000, 100)[1] == "drawdown_halt"
    assert risk.size_position(100000, 100000, 100, halted=True)[0] == 0
    assert risk.size_position(100000, 100000, np.nan)[0] == 0


def test_account_halts_without_reinvesting_after_breach(monkeypatch):
    monkeypatch.setattr(C, "MAX_ACCOUNT_DRAWDOWN", .01)
    entries = [date(2024, 1, 2), date(2024, 1, 9)]
    weeks = pd.DataFrame([dict(entry=e, pick="bull_put_spread", pick_reason="uptrend_credit") for e in entries])
    trades = pd.DataFrame([dict(entry=e, exit=e, strategy="bull_put_spread", risk_estimate_rs=1500,
                               pnl_rs=-1500) for e in entries])
    account = B.account_simulation(weeks, trades, capital=100000)
    assert account["lots"].tolist() == [1, 0]
    assert account["reason"].tolist() == ["sized", "drawdown_halt"]
    assert account["equity_rs"].tolist() == [98500, 98500]
    assert (account["reserved_risk_rs"] <= account["risk_budget_rs"]).all()
    trades.loc[0, "pnl_rs"] = 1500
    assert B.account_simulation(weeks, trades, capital=100000).iloc[0]["lots"] == 1


def test_features_do_not_read_future_closes():
    mkt = load_market().iloc[:400]
    full = regime.add_features(mkt)
    prefix = regime.add_features(mkt.iloc[:300])
    pd.testing.assert_frame_equal(full.iloc[:300], prefix)


def test_first_loss_is_included_in_drawdown():
    assert B.stats(pd.Series([-100, -50, 20]))["max_drawdown_rs"] == -150


def test_split_excludes_development_trade_crossing_boundary():
    entries = pd.to_datetime(["2022-12-22", "2022-12-29", "2023-01-05"])
    weeks = pd.DataFrame(dict(entry=entries, front=pd.to_datetime(["2022-12-29", "2023-01-05", "2023-01-12"]),
                              pick=["bull_put_spread"] * 3, legacy_pick=["bull_call_spread"] * 3))
    wide = pd.DataFrame({"REGIME_BOT": [1, 10000, -2], "LEGACY_BOT": [2, 20000, -3]}, index=entries)
    evaluation = B.period_evaluation(weeks, wide)
    bot = evaluation[evaluation["algorithm"] == "REGIME_BOT"].set_index("period")
    assert bot.loc["development", "total_rs"] == 1
    assert bot.loc["later_period", "total_rs"] == -2


def test_preview_vetoes_timing_stale_data_and_small_capital(tmp_path):
    mkt = pd.DataFrame(index=pd.to_datetime(["2026-11-13"]))
    feat = pd.DataFrame([market_row()], index=mkt.index)
    small = latest_signal(mkt, feat, capital=20000, as_of=date(2026, 11, 14))
    assert small["strategy"] == "no trade"
    assert small["reason"] == "one_lot_exceeds_risk_budget"
    rich = latest_signal(mkt, feat, capital=1000000, as_of=date(2026, 11, 14))
    assert rich["reason"] == "waiting_for_weekly_entry"
    assert rich["orders_submitted"] is False
    stale = latest_signal(mkt, feat, capital=1000000, as_of=date(2026, 11, 18))
    assert stale["reason"] == "stale_data" and stale["preview_lots"] == 0
    future = latest_signal(mkt, feat, as_of=date(2026, 11, 12))
    assert future["reason"] == "future_data"
    journal = tmp_path / "signals.jsonl"
    assert record_signal(small, journal)
    assert not record_signal(small, journal)
    assert json.loads(journal.read_text())["record_type"] == "model_signal_preview"


def test_scheduled_preview_uses_same_policy_and_entry_quote():
    mkt = pd.DataFrame(index=pd.to_datetime(["2026-11-17"]))
    row = market_row()
    feat = pd.DataFrame([row], index=mkt.index)
    signal = latest_signal(mkt, feat, capital=1000000, as_of=date(2026, 11, 17))
    assert signal["strategy"] == algorithm.select(row).strategy
    quote = risk.entry_quote(signal["strategy"], 25000, 7 / 365, .20)
    assert signal["estimated_risk_per_lot_rs"] == round(quote["risk_estimate_rs"], 2)
    assert signal["preview_lots"] > 0


def test_exit_rules_take_profit_stop_and_expiry(monkeypatch):
    assert ST.exit_signal("bull_put_spread", 25, -50) == "take_profit"
    assert ST.exit_signal("bull_put_spread", -100, -50) == "stop_loss"
    monkeypatch.setattr(C, "MANAGE_EXITS", False)
    assert ST.exit_signal("bull_put_spread", -100, -50) is None
