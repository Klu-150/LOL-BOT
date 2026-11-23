from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dashboard import DashboardHandler
from auto_trader import AutoTrader
import auto_trader


def handler(origin='http://127.0.0.1:8765', token='good', host='127.0.0.1:8765', path='/api/automation/start'):
    h=DashboardHandler.__new__(DashboardHandler)
    h.headers={'Host':host,'Origin':origin,'X-Terminal-Token':token}
    h.path=path
    h.server=SimpleNamespace(runtime=SimpleNamespace(token='good',trader=SimpleNamespace(start=Mock(return_value={'enabled':True}),pause=Mock(return_value={'enabled':False})),backtest=Mock(return_value={'id':'job','status':'running'})))
    h._json=Mock()
    return h


@pytest.mark.parametrize('origin,token,host',[
    ('http://evil.example','good','127.0.0.1:8765'),
    ('http://127.0.0.1:8765','wrong','127.0.0.1:8765'),
    ('http://evil.example','good','evil.example'),
])
def test_paper_controls_reject_other_origins_and_missing_session_tokens(origin,token,host):
    h=handler(origin,token,host);h.do_POST()
    assert h._json.call_args.args[1]==403
    h.server.runtime.trader.start.assert_not_called()


def test_local_paper_start_and_pause_are_real_backend_actions():
    h=handler();h.do_POST();h.server.runtime.trader.start.assert_called_once()
    h=handler(path='/api/automation/pause');h.do_POST();h.server.runtime.trader.pause.assert_called_once()
    h=handler(path='/api/backtest/run');h.do_POST();h.server.runtime.backtest.assert_called_once()
    assert h._json.call_args.args[1]==202


def test_feed_failure_never_enables_new_paper_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_trader,'STATUS_FILE',tmp_path/'runtime.json')
    monkeypatch.setattr(auto_trader.feed,'refresh',Mock(side_effect=ValueError('feed unavailable')))
    process=Mock(return_value={})
    monkeypatch.setattr(auto_trader.paper,'process',process)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    runner=AutoTrader(db=tmp_path/'account.sqlite3');runner.entries_enabled=True
    result=runner.cycle(now=datetime(2026,11,16,10,0,tzinfo=ZoneInfo('Asia/Kolkata')))
    assert result['state']=='data_error'
    assert process.call_args.kwargs['entries_enabled'] is False


def test_start_wakes_running_worker_instead_of_waiting_a_full_poll(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(auto_trader,'STATUS_FILE',tmp_path/'runtime.json')
    monkeypatch.setattr(auto_trader,'MIGRATION_FILE',tmp_path/'absent.json')
    runner=AutoTrader(interval=600,db=tmp_path/'account.sqlite3')
    seen=[];second=threading.Event()
    def cycle(*a,**k):
        seen.append(runner.entries_enabled)
        if len(seen)>=2: second.set()
        return runner.status
    runner.cycle=cycle
    runner.pause()
    for _ in range(100):
        if seen: break
        threading.Event().wait(0.01)
    runner.start()
    assert second.wait(2), 'start() must trigger an immediate cycle'
    assert seen[-1] is True
    runner.shutdown()
    assert not runner._thread.is_alive()
