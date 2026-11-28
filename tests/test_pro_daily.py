import pandas as pd
import pytest

from pro import daily


def _bars(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame({"Open": [r[1] for r in rows], "Close": [r[2] for r in rows]}, index=idx)


def _result(day, action):
    return {"as_of_bar": day, "action": action, "generated_at": day}


def test_orders_fill_at_next_open_and_cash_accrues(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "LEDGER", tmp_path / "ledger.json")
    f = _bars([("2026-01-01", 100, 100)])
    led = daily.update_ledger(_result("2026-01-01", "BUY_AT_NEXT_OPEN"), f)
    assert led["pending"] == "BUY" and led["units"] == 0

    f = _bars([("2026-01-01", 100, 100), ("2026-01-02", 110, 120)])
    led = daily.update_ledger(_result("2026-01-02", "HOLD"), f)
    px = 110 * (1 + daily.COST_PCT)
    assert led["fills"][-1]["side"] == "BUY" and led["units"] == pytest.approx(daily.CAPITAL * (1 + daily.CASH_YIELD) ** (1 / 365) / px)
    assert led["equity"] == pytest.approx(led["units"] * 120, rel=1e-6)

    led = daily.update_ledger(_result("2026-01-02", "SELL_AT_NEXT_OPEN"), f)
    f = _bars([("2026-01-01", 100, 100), ("2026-01-02", 110, 120), ("2026-01-05", 130, 90)])
    led = daily.update_ledger(_result("2026-01-05", "STAND_ASIDE"), f)
    assert led["units"] == 0 and led["fills"][-1]["side"] == "SELL"
    assert led["cash"] == pytest.approx(led["fills"][-2]["units"] * 130 * (1 - daily.COST_PCT), rel=1e-4)


def test_rerun_same_day_does_not_double_fill(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "LEDGER", tmp_path / "ledger.json")
    f = _bars([("2026-01-01", 100, 100)])
    daily.update_ledger(_result("2026-01-01", "BUY_AT_NEXT_OPEN"), f)
    f = _bars([("2026-01-01", 100, 100), ("2026-01-02", 110, 120)])
    daily.update_ledger(_result("2026-01-02", "HOLD"), f)
    led = daily.update_ledger(_result("2026-01-02", "HOLD"), f)
    assert len(led["fills"]) == 1
