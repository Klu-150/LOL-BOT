import pandas as pd

from pro import engine, features
from pro.strategies import LIBRARY


def _frame():
    return features.load()


def test_features_are_causal():
    f = _frame()
    cut = f.index[-200]
    truncated = features.add_features(f.loc[:cut, ["Open", "High", "Low", "Close", "VIX", "vix_observed"]])
    cols = ["ema50", "ema200", "adx", "rsi2", "atr", "hi55", "vix_rank", "regime"]
    pd.testing.assert_frame_equal(truncated[cols].iloc[-50:], f.loc[:cut, cols].iloc[-50:], check_exact=False)


def test_trades_fill_after_signal_and_respect_stop():
    f = _frame()
    for s in LIBRARY:
        for t in engine.simulate(f, s):
            assert t.entry_date > t.signal_date
            if t.exit_date is not None:
                assert t.exit_date >= t.entry_date
                if t.exit_reason == "stop" and not s.trail:
                    # A fixed stop never loses more than its distance unless the market gapped through it.
                    gap = abs(f.loc[t.exit_date, "Open"] - t.exit_px) < 1e-9
                    assert t.r >= -1.01 - 2 * engine.COST_PTS / t.stop_pts or gap


def test_selector_uses_only_trades_closed_before_decision():
    f = _frame()
    trades = engine.all_trades(f)
    asof = f.index[-300]
    board = engine.scoreboard(trades, "uptrend", asof, f.index)
    later = [t for t in trades if t.exit_date is not None and t.exit_date >= asof]
    future_only = engine.scoreboard(later, "uptrend", asof, f.index)
    assert future_only == {}
    assert all(v["trades"] > 0 for v in board.values())


def test_future_bars_do_not_change_past_choices():
    f = _frame()
    cut = f.index[-250]
    past = f.loc[:cut]
    chosen_past, _ = engine.select(past, engine.all_trades(past))
    chosen_full, _ = engine.select(f, engine.all_trades(f))
    closed_past = [(t.strategy, t.entry_date, t.exit_date) for t in chosen_past if t.exit_date is not None]
    full = {(t.strategy, t.entry_date, t.exit_date) for t in chosen_full}
    assert set(closed_past) <= full


def test_playbook_stands_aside_in_downtrend_and_stress():
    assert engine.PLAYBOOK["downtrend"] == [] and engine.PLAYBOOK["stress"] == []
