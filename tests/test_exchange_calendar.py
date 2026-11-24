from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import auto_trader as A
from exchange_calendar import session_status, deployment_allowed
from tests.test_production_guards import runner

ZONE=ZoneInfo('Asia/Kolkata')


def at(day, hour=10, minute=0):
    return datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=ZONE)


def test_verified_holiday_does_not_expect_live_prices_or_authorise_entries():
    status=session_status(at('2026-11-24'))
    assert status['verified'] and status['reason']=='holiday'
    assert status['holiday']=='Guru Nanak Jayanti'
    assert not status['feed_window'] and not status['entries_allowed']
    assert status['next_entry_at_or_after']=='2026-11-25T09:45:00+05:30'
    assert deployment_allowed(at('2026-11-24'))
    assert session_status(at('2026-01-15'))['reason']=='holiday'


def test_weekends_special_sessions_unknown_year_and_naive_time_fail_closed():
    for day, reason in [('2026-11-22','weekend'),('2026-11-08','special_session_unsupported'),('2027-01-04','calendar_unverified')]:
        status=session_status(at(day))
        assert status['reason']==reason
        assert not status['entries_allowed'] and not status['feed_window']
    assert not deployment_allowed(at('2027-01-04',20))
    with pytest.raises(ValueError):session_status(datetime(2026,11,24,10))


def test_session_boundaries_and_timezone_conversion():
    assert not session_status(at('2026-11-25',9,44))['entries_allowed']
    assert session_status(at('2026-11-25',9,45))['entries_allowed']
    assert session_status(at('2026-11-25',14,30))['entries_allowed']
    assert session_status(at('2026-11-25',14,30).replace(second=59))['entries_allowed']
    assert not session_status(at('2026-11-25',14,31))['entries_allowed']
    assert not deployment_allowed(at('2026-11-25',10))
    assert deployment_allowed(at('2026-11-25',16))
    assert session_status(at('2026-11-25').astimezone(ZoneInfo('UTC')))==session_status(at('2026-11-25'))


def test_holiday_cycle_skips_provider_and_entries_but_keeps_exit_processing(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch)
    refresh=Mock();monkeypatch.setattr(A.feed,'refresh',refresh)
    process=Mock(return_value={'status':'awaiting_fresh_market_data','position_open':False})
    monkeypatch.setattr(A.paper,'process',process)
    status=r.cycle(now=at('2026-11-24'))
    refresh.assert_not_called()
    assert process.call_args.kwargs['entries_enabled'] is False
    assert status['state']=='market_closed' and status['calendar']['reason']=='holiday'


def test_unknown_calendar_blocks_entries_and_unresolved_closed_session_position_stays_unhealthy(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch)
    process=Mock(return_value={'status':'awaiting_fresh_market_data','position_open':True})
    monkeypatch.setattr(A.paper,'process',process)
    assert r.cycle(False,at('2026-11-24'))['state']=='square_off_waiting_for_data'
    process.return_value={'status':'awaiting_fresh_market_data','position_open':False}
    assert r.cycle(False,at('2027-01-04'))['state']=='calendar_unverified'
    assert process.call_args.kwargs['entries_enabled'] is False
