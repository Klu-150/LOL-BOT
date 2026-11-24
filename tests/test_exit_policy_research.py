import pytest

from research.exit_policy_comparison import BasketExit, mtm_reason, worker


def test_percentage_stop_scales_with_credit_and_allows_overshoot():
    p = BasketExit('basket_percentage')
    assert p.reason(-5.99, 20) is None
    assert p.reason(-6, 20) == 'research_percentage_basket_stop'
    assert p.reason(-25, 20) == 'research_percentage_basket_stop'


def test_trailing_requires_profit_and_resets_between_positions():
    p = BasketExit('basket_trailing')
    assert p.reason(-4, 20) is None
    assert p.reason(8, 20) is None
    assert p.reason(5, 20) == 'research_basket_trail'
    p.reset()
    assert p.reason(1, 20) is None


def test_fixed_basket_stop_and_baseline_are_distinct():
    assert BasketExit('basket_fixed_points').reason(-30, 20) == 'research_fixed_basket_stop'
    assert BasketExit('baseline').reason(-30, 20) is None


def test_mtm_boundaries_are_based_on_session_equity():
    assert mtm_reason(495001, 500000) is None
    assert mtm_reason(495000, 500000) == 'research_daily_mtm_loss'
    assert mtm_reason(505000, 500000) == 'research_daily_mtm_target'
    assert mtm_reason(247500, 250000) == 'research_daily_mtm_loss'


def test_invalid_policy_inputs_fail_closed():
    with pytest.raises(ValueError):
        BasketExit('short_strangle')
    with pytest.raises(ValueError):
        BasketExit('basket_percentage').reason(float('nan'), 20)
    with pytest.raises(ValueError):
        BasketExit('basket_trailing').reason(5, 0)
    with pytest.raises(ValueError):
        mtm_reason(500000, 0)


def test_replay_retains_hedges_and_restores_module_callback():
    import strategies as ST
    original = ST.exit_signal
    row = dict(Open=25000., High=25010., Low=24990., Close=25000., VIX=20.,
               ema_fast=24900., ema_slow=24800., adx=15., realized_vol=15.,
               ivr=55., iv_rv_ratio=1.33, bias_age_minutes=0., trigger_fast=24980.,
               trigger_slow=24900., event=False, vix_observed=True, shock=False)
    bars = [{**row, 'timestamp': '2026-11-24T09:45:00+05:30'},
            {**row, 'timestamp': '2026-11-24T15:15:00+05:30'}]
    result = worker({'bars': bars}, 'basket_percentage', ['2026-11-24'])
    assert ST.exit_signal is original
    assert result['all_same_day_exits']
    assert result['trades_count'] == 1
    legs = result['trades'][0]['legs']
    assert len(legs) == 4
    assert sum(leg['qty'] > 0 for leg in legs) == 2
    assert result['trades'][0]['exit_reason'] == 'session_square_off'


def test_incomplete_session_is_rejected_and_callback_restored():
    import strategies as ST
    original = ST.exit_signal
    with pytest.raises(ValueError, match='incomplete'):
        worker({'bars': [{'timestamp': '2026-11-24T10:00:00+05:30'}]}, 'baseline', ['2026-11-24'])
    assert ST.exit_signal is original
