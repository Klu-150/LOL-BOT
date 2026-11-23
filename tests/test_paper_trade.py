from datetime import date, datetime
import json
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import backtest as B
import config as C
from paper_trade import add_note, completed_through, initialise, process, review


def market(dates, spots=None):
    spots = spots or [25000] * len(dates)
    frame = pd.DataFrame({"Close": spots, "Open": spots, "High": spots, "Low": spots,
                          "VIX": 20.0, "vix_observed": True}, index=pd.to_datetime(dates))
    features = frame.assign(ivr=55., adx=30., ema_fast=frame.Close - 100, ema_slow=frame.Close - 200,
                            realized_vol=15., iv_rv_ratio=20 / 15, trend="strong_up", iv="high", shock=False)
    return frame, features


def start(tmp_path, capital=1000000):
    path = tmp_path / "account.sqlite3"
    mkt, _ = market(["2026-11-16"])
    initialise(path, capital, mkt, as_of=date(2026, 11, 16), cutoff=date(2026, 11, 16))
    return path


def advance(path, dates, spots=None):
    mkt, features = market(dates, spots)
    today = mkt.index[-1].date()
    return process(path, mkt, as_of=today, cutoff=today, features=features)


def test_start_is_forward_only_and_never_overwrites_account(tmp_path):
    path = start(tmp_path)
    assert review(path)["closed_trades"] == 0
    assert review(path)["last_processed"] == "2026-11-16"
    mkt, _ = market(["2026-11-16"])
    with pytest.raises(ValueError, match="already exists"):
        initialise(path, 20, mkt, as_of=date(2026, 11, 16), cutoff=date(2026, 11, 16))
    assert review(path)["initial_capital_rs"] == 1000000


def test_persistent_fill_exit_and_equity_match_backtest(tmp_path):
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    opened = review(path)
    assert opened["open_trades"] == 1 and opened["closed_trades"] == 0
    assert opened["marked_equity_rs"] < 1000000  # fees and spread on immediate liquidation
    again = advance(path, ["2026-11-16", "2026-11-17"])
    assert again["bars_processed"] == 0
    assert review(path) == opened
    dates, spots = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-24"], [25000, 25000, 26000, 26000]
    advance(path, dates[:3], spots[:3])
    closed = review(path, tmp_path / "export")
    assert closed["open_trades"] == 0 and closed["closed_trades"] == 1
    mkt, _ = market(dates, spots)
    expected = B.simulate_trade("bull_put_spread", mkt, date(2026, 11, 17), date(2026, 11, 24), None)
    trades = pd.read_csv(tmp_path / "export" / "trades.csv")
    lots = trades.iloc[0].lots
    assert trades.iloc[0].net_pnl_rs == pytest.approx(expected["pnl_rs"] * lots)
    assert closed["realised_equity_rs"] == pytest.approx(1000000 + expected["pnl_rs"] * lots)
    assert closed["by_setup"]["uptrend_credit"]["closed_trades"] == 1
    assert closed["sample_status"] == "insufficient_sample"
    assert trades.iloc[0].exit_reason == "take_profit"
    assert trades.iloc[0].stop_loss_pnl_pts < 0 < trades.iloc[0].take_profit_pnl_pts


def test_small_account_never_forces_one_lot_and_logs_skip(tmp_path):
    path = start(tmp_path, capital=20000)
    advance(path, ["2026-11-16", "2026-11-17"])
    result = review(path)
    assert result["open_trades"] == 0
    assert result["realised_equity_rs"] == 20000
    assert result["skip_reasons"] == {"one_lot_exceeds_risk_budget": 1}


def test_missed_entry_days_are_not_backfilled(tmp_path):
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17", "2026-11-24", "2026-11-25"])
    result = review(path)
    assert result["open_trades"] == 0 and result["closed_trades"] == 0
    assert result["skip_reasons"]["missed_entry_not_backfilled"] == 2


def test_incomplete_or_future_bars_are_not_processed(tmp_path):
    path = start(tmp_path)
    mkt, features = market(["2026-11-16", "2026-11-17", "2026-11-18"])
    result = process(path, mkt, as_of=date(2026, 11, 17), cutoff=date(2026, 11, 16), features=features)
    assert result["bars_processed"] == 0
    result = process(path, mkt, as_of=date(2026, 11, 17), cutoff=date(2026, 11, 17), features=features)
    assert result["last_processed"] == "2026-11-17"
    assert review(path)["open_trades"] == 1


def test_missing_expiry_bar_rolls_back_and_does_not_settle_at_later_spot(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "MANAGE_EXITS", False)
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    before = review(path)
    with pytest.raises(ValueError, match="Missing expiry close"):
        advance(path, ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-25"])
    assert review(path) == before
    advance(path, ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-24", "2026-11-25"])
    assert review(path)["closed_trades"] == 1


def test_config_changes_cannot_silently_alter_open_trade(tmp_path, monkeypatch):
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    before = review(path)
    monkeypatch.setattr(C, "CREDIT_STOP_MULT", 4)
    with pytest.raises(ValueError, match="changed"):
        advance(path, ["2026-11-16", "2026-11-17", "2026-11-18"])
    assert review(path) == before


def test_drawdown_halt_survives_later_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "MAX_ACCOUNT_DRAWDOWN", .001)
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    advance(path, ["2026-11-16", "2026-11-17", "2026-11-18"], [25000, 25000, 20000])
    assert review(path)["halted"] is True
    advance(path, ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-24"], [25000, 25000, 20000, 25000])
    assert review(path)["closed_trades"] == 1
    assert review(path)["open_trades"] == 0
    assert review(path)["skip_reasons"]["drawdown_halt"] == 1


def test_missing_same_day_vix_cannot_create_a_fake_exit(tmp_path):
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    before = review(path)
    mkt, features = market(["2026-11-16", "2026-11-17", "2026-11-18"])
    mkt.loc[pd.Timestamp("2026-11-18"), "vix_observed"] = False
    with pytest.raises(ValueError, match="same-day VIX"):
        process(path, mkt, as_of=date(2026, 11, 18), cutoff=date(2026, 11, 18), features=features)
    assert review(path) == before


def test_notes_record_user_supplied_emotions_separately(tmp_path):
    path = start(tmp_path)
    advance(path, ["2026-11-16", "2026-11-17"])
    add_note(path, 1, "Followed the written setup", "calm")
    with pytest.raises(ValueError, match="does not exist"):
        add_note(path, 99, "Missing trade")
    review(path, tmp_path / "export")
    notes = pd.read_csv(tmp_path / "export" / "notes.csv")
    assert notes.iloc[0].emotion == "calm"
    assert notes.iloc[0].note == "Followed the written setup"
    payload = json.loads((tmp_path / "export" / "review.json").read_text())
    assert payload["orders_submitted"] is False


def test_completed_bar_cutoff_uses_india_time():
    zone = ZoneInfo("Asia/Kolkata")
    assert completed_through(datetime(2026, 11, 17, 15, 29, tzinfo=zone)) == date(2026, 11, 16)
    assert completed_through(datetime(2026, 11, 17, 15, 30, tzinfo=zone)) == date(2026, 11, 17)
