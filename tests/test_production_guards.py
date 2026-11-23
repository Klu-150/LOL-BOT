from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import threading
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import auto_trader as A
import dashboard as D
import intraday_feed as F
from operations import WorkerWatchdog


def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'STATUS_FILE', tmp_path/'runtime.json')
    monkeypatch.setattr(A, 'MIGRATION_FILE', tmp_path/'missing-migration.json')
    monkeypatch.setattr(A, 'ROOT', tmp_path)
    feed_path=tmp_path/A.C.INTRADAY_CSV
    feed_path.parent.mkdir(parents=True,exist_ok=True);feed_path.touch()
    r=A.AutoTrader(db=tmp_path/'account.sqlite3');r.entries_enabled=True
    r._thread=SimpleNamespace(is_alive=lambda: True)  # Do not launch an actual paper worker.
    return r


def test_pause_waits_for_inflight_entry_transaction_and_blocks_next(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch);began=threading.Event();release=threading.Event();seen=[]
    def process(*args,**kwargs):
        seen.append(kwargs['entries_enabled']);began.set();assert release.wait(3)
        return {'status':'watching'}
    monkeypatch.setattr(A.paper,'process',process)
    now=datetime(2026,11,16,10,tzinfo=ZoneInfo('Asia/Kolkata'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        cycle=pool.submit(r.cycle,False,now);assert began.wait(2)
        pause=pool.submit(r.pause)
        assert not pause.done()
        release.set();cycle.result(timeout=3)
        assert pause.result(timeout=3)['enabled'] is False
    r.cycle(False,now);assert seen==[True,False]


def test_pause_during_network_fetch_blocks_entry_without_waiting_for_fetch(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch);began=threading.Event();release=threading.Event()
    def refresh(**kwargs):began.set();assert release.wait(3);return {}
    monkeypatch.setattr(A.feed,'refresh',refresh)
    process=Mock(return_value={'status':'watching'});monkeypatch.setattr(A.paper,'process',process)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(r.cycle,True,datetime(2026,11,16,10,tzinfo=ZoneInfo('Asia/Kolkata')))
        assert began.wait(2);assert not r.pause()['enabled'];release.set();future.result(timeout=3)
    assert process.call_args.kwargs['entries_enabled'] is False


def test_low_disk_blocks_entries_but_processes_exits(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch)
    monkeypatch.setattr(A.shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    process=Mock(return_value={'status':'watching'});monkeypatch.setattr(A.paper,'process',process)
    result=r.cycle(False,datetime(2026,11,16,10,tzinfo=ZoneInfo('Asia/Kolkata')))
    assert result['state']=='storage_guard'
    assert process.call_args.kwargs['entries_enabled'] is False


def test_failed_start_status_persistence_does_not_enable_entries(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch);r.entries_enabled=False
    monkeypatch.setattr(r,'_write',Mock(side_effect=OSError('read-only storage')))
    with pytest.raises(OSError):r.start()
    assert r.entries_enabled is False


@pytest.mark.parametrize('prices',[(100,99,98,100),(100,102,101,100),(100,99,101,100)])
def test_reject_ohlc_ranges_that_cannot_be_valid_bars(tmp_path,prices):
    p=tmp_path/'bad.csv';p.write_text('timestamp,Open,High,Low,Close\n2026-11-16T10:00:00+05:30,'+','.join(map(str,prices))+'\n')
    with pytest.raises(ValueError,match='high/low'):F.load(p)


def test_provider_invalid_bar_is_rejected_before_persisting(monkeypatch):
    body={'chart':{'error':None,'result':[{'meta':{'symbol':'^NSEI'},'timestamp':[1794803400],
          'indicators':{'quote':[{'open':[100.],'high':[90.],'low':[80.],'close':[100.]}]}}]}}
    monkeypatch.setattr(F.transport,'fetch',lambda *args:body)
    with pytest.raises(ValueError,match='high/low'):F.chart('^NSEI')


def test_watchdog_recycles_failed_worker_once_but_not_closed_market():
    clock=[0.];now=datetime.now(timezone.utc)
    trader=SimpleNamespace(_thread=SimpleNamespace(is_alive=lambda:True),status={'state':'market_closed','checked_at':now.isoformat()})
    restart=Mock();watchdog=WorkerWatchdog(trader,restart,clock=lambda:clock[0])
    clock[0]=121;assert watchdog.check(now) is None
    for state in ['entries_paused_managing_exits','data_error','storage_guard']:
        trader.status['state']=state;assert watchdog.check(now) is None
    trader.status['checked_at']=(now-timedelta(seconds=301)).isoformat()
    assert watchdog.check(now)=='heartbeat_stale';watchdog.check(now);restart.assert_called_once()
    dead=WorkerWatchdog(SimpleNamespace(_thread=None,status={}),restart,grace=0)
    dead.close();assert dead.check(now) is None


def test_runtime_state_directory_also_isolates_the_trading_database(tmp_path,monkeypatch):
    factory=Mock();monkeypatch.setattr(D,'AutoTrader',factory)
    runtime=D.TerminalRuntime(state_dir=tmp_path)
    factory.assert_called_once_with(db=tmp_path/'intraday_500k.sqlite3')
    runtime.close()


def test_worker_survives_status_write_failure_with_entries_disabled(tmp_path,monkeypatch):
    r=runner(tmp_path,monkeypatch);calls=[]
    def cycle():
        calls.append(r.entries_enabled)
        if len(calls)==1:raise OSError('status storage unavailable')
        r._stop.set()
    monkeypatch.setattr(r,'cycle',cycle)
    monkeypatch.setattr(r._wake,'wait',lambda _:None)
    r._loop()
    assert calls==[True,False]
