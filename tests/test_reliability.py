from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error

import pytest

import cloud_server as C
import intraday_paper as P
import ledger_store as L
from operations import BackupManager, OperationsStore, RateLimiter, SnapshotCache, backup_database
from feed_transport import CircuitOpen, FeedTransport, ProviderRedirects
from tests.test_cloud_server import KEY, ORIGIN, request, settings


@pytest.fixture
def app(tmp_path):
    runtime = SimpleNamespace(trader=SimpleNamespace(status={'enabled':True,'state':'watching',
                               'checked_at':datetime.now(timezone.utc).isoformat()},
                               start=Mock(return_value={'enabled':True}),pause=Mock(return_value={'enabled':False})),
                               jobs={},backtest=Mock(return_value={'id':'research-job','status':'running'}))
    return C.create_app(settings(),runtime,tmp_path/'control.json')


def test_limiter_recovers_and_memory_is_bounded():
    now=[0.];limiter=RateLimiter(max_keys=3,clock=lambda:now[0])
    assert limiter.allow('a',2)[0] and limiter.allow('a',2)[0]
    assert not limiter.allow('a',2)[0]
    now[0]=61
    assert limiter.allow('a',2)[0]
    for key in range(100):limiter.allow(key,2)
    assert len(limiter.entries)==3


def test_auth_throttling_does_not_lock_out_valid_user(app):
    for _ in range(15):assert request(app,key='invalid')['status']==401
    blocked=request(app,key='invalid')
    assert blocked['status']==429 and 'Retry-After' in blocked['headers']
    assert request(app)['status']==200
    assert app.client_ip({'REMOTE_ADDR':'192.0.2.1','HTTP_X_LEAGUE_CLIENT_IP':'1.2.3.4'})=='192.0.2.1'


@pytest.mark.parametrize('raw',[b'[]',b'{"enabled":true}',b'{broken',b'null',b'"command"',b''])
def test_action_body_is_validated_before_side_effects(app,raw):
    result=request(app,'/api/automation/start','POST',CONTENT_LENGTH=str(len(raw) or 2),**{'wsgi.input':io.BytesIO(raw)})
    assert result['status']==400
    app.runtime.trader.start.assert_not_called()
    assert not app.control_path.exists()


def test_idempotency_replays_without_repeating_action_and_survives_restart(app):
    args={'HTTP_IDEMPOTENCY_KEY':'owner-start-1234'}
    assert request(app,'/api/automation/start','POST',**args)['status']==200
    assert request(app,'/api/v1/automation/start','POST',**args)['status']==200
    app.runtime.trader.start.assert_called_once()
    restarted=C.create_app(app.settings,app.runtime,app.control_path)
    assert request(restarted,'/api/automation/start','POST',**args)['status']==200
    app.runtime.trader.start.assert_called_once()
    assert request(app,'/api/automation/pause','POST',**args)['status']==409
    app.runtime.trader.pause.assert_not_called()


def test_pending_action_is_never_blindly_replayed(app):
    app.store.claim('owner','pending-key-123','POST /api/automation/start')
    assert request(app,'/api/automation/start','POST',HTTP_IDEMPOTENCY_KEY='pending-key-123')['status']==409
    app.runtime.trader.start.assert_not_called()


def test_expired_and_disabled_keys_are_rejected(app):
    app.settings.users['owner']['expires_at']='2000-01-01T00:00:00+00:00'
    assert request(app)['status']==401
    del app.settings.users['owner']['expires_at']
    app.settings.users['owner']['disabled']=True
    assert request(app)['status']==401


def test_liveness_and_readiness_are_distinct_and_errors_are_visible(app):
    assert request(app,'/healthz',key='bad')['status']==200
    assert request(app,'/readyz',key='bad')['status']==200
    app.runtime.trader.status['state']='data_error'
    assert request(app,'/healthz',key='bad')['status']==200
    assert request(app,'/readyz',key='bad')['status']==503
    assert 'data_error' in request(app,'/api/operations')['body']['alerts']
    app.runtime.trader.status.update(state='market_closed',checked_at=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat())
    assert 'heartbeat_stale' in request(app,'/api/health')['body']['operations']['alerts']


def test_headers_audit_records_and_versioned_routes_do_not_leak_keys(app):
    response=request(app,'/api/v1/health')
    assert response['body']['version']==__import__('cloud_server').VERSION
    assert response['headers']['X-Frame-Options']=='DENY'
    assert "frame-ancestors 'none'" in response['headers']['Content-Security-Policy']
    request(app,'/api/automation/pause','POST')
    with sqlite3.connect(app.store.path) as conn:
        rows=conn.execute('SELECT actor,action,status,request_id FROM audit').fetchall()
    assert rows[-1][:3]==('owner','/api/automation/pause',200)
    assert KEY not in json.dumps(rows)


def test_concurrent_snapshot_requests_share_one_build_and_expire(app,monkeypatch):
    build=Mock(return_value={'paper':{'trades':[]}})
    monkeypatch.setattr(C,'build_snapshot',build)
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses=list(pool.map(lambda _:request(app,'/api/dashboard'),range(40)))
    assert all(r['status']==200 for r in responses)
    assert build.call_count==1
    app.cache.invalidate();request(app,'/api/dashboard');assert build.call_count==2
    now=[1.];cache=SnapshotCache(clock=lambda:now[0]);cache.get(build);now[0]=7.;cache.get(build)
    assert cache.builds==2


def seed_ledger(path, count=20):
    P.initialise(path,now=datetime(2026,11,16,tzinfo=timezone.utc))
    with sqlite3.connect(path) as conn:
        for number in range(count):
            stamp=f'2026-11-16T10:{number:02d}:00+05:30'
            conn.execute('INSERT INTO trades(entry,body) VALUES(?,?)',(stamp,json.dumps({'entry':stamp,'net_pnl_rs':1})))
            conn.execute('INSERT INTO events VALUES(?,?)',(stamp,json.dumps({'timestamp':stamp})))


def test_migration_is_repeatable_preserves_policy_and_totals_are_transactional(tmp_path):
    db=tmp_path/'paper.sqlite3';seed_ledger(db)
    with sqlite3.connect(db) as conn:before=conn.execute('SELECT body FROM account').fetchone()[0]
    L.migrate(db);L.migrate(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT body FROM account').fetchone()[0]==before
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert conn.execute('SELECT trades,pnl FROM ledger_totals').fetchone()==(20,20.)
        conn.execute('BEGIN IMMEDIATE');conn.execute('INSERT INTO trades(entry,body) VALUES(?,?)',('extra','{"net_pnl_rs":5}'));conn.rollback()
        assert conn.execute('SELECT trades,pnl FROM ledger_totals').fetchone()==(20,20.)
        conn.execute('UPDATE trades SET body=? WHERE id=1',('{"net_pnl_rs":10}',))
        assert conn.execute('SELECT trades,pnl FROM ledger_totals').fetchone()==(20,29.)
    snap=L.snapshot(db,trade_limit=5,event_limit=7)
    assert snap['closed_trades']==20 and len(snap['trades'])==5 and len(snap['decisions'])==7
    assert snap['net_closed_pnl_rs']==29 and 'fingerprint' not in snap


def test_cursor_paging_has_no_omissions_duplicates_or_sql_injection(tmp_path):
    db=tmp_path/'paper.sqlite3';seed_ledger(db)
    ids=[];cursor=None
    while True:
        page=L.history(db,'trades',limit=3,cursor=cursor)
        ids.extend(row['id'] for row in page['items']);cursor=page['next_cursor']
        if cursor is None:break
    assert ids==list(range(20,0,-1))
    with pytest.raises(ValueError):L.history(db,'trades',cursor="1; DROP TABLE trades")
    with pytest.raises(ValueError):L.history(db,'trades',limit=100000)
    assert L.history(db,'events',limit=2)['next_cursor'] is not None


def test_backup_restores_a_consistent_account_and_retention_is_bounded(tmp_path):
    db=tmp_path/'paper.sqlite3';seed_ledger(db);L.migrate(db)
    manager=BackupManager(db,tmp_path/'backups',keep=2)
    for _ in range(4):status=manager.run_once()
    assert len(list((tmp_path/'backups').glob('*.json')))==2
    copy=tmp_path/'backups'/status['files'][0]['file']
    restored=tmp_path/'restored.sqlite3';backup_database(copy,restored)
    assert L.snapshot(db)==L.snapshot(restored)
    assert not status['off_host']
    assert not list((tmp_path/'backups').glob('*.tmp'))


def test_feed_retries_transient_errors_opens_circuit_and_recovers():
    now=[0.];sleep=Mock();opener=Mock(side_effect=TimeoutError('offline'))
    transport=FeedTransport(opener,clock=lambda:now[0],sleep=sleep,jitter=lambda:0)
    url='https://query1.finance.yahoo.com/test'
    for _ in range(3):
        with pytest.raises(TimeoutError):transport.fetch(url,'NIFTY')
    assert opener.call_count==6 and sleep.call_count==3
    assert [call.args[0] for call in sleep.call_args_list]==[1,2,4]
    with pytest.raises(CircuitOpen):transport.fetch(url,'NIFTY')
    assert opener.call_count==6
    now[0]=61
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'{"ok":true}'
        def geturl(self):return url
    opener.side_effect=None;opener.return_value=Response()
    assert transport.fetch(url,'NIFTY')=={'ok':True}
    assert transport.status()['NIFTY']['failures']==0


def test_permanent_errors_are_not_retried_and_redirects_cannot_fetch_metadata():
    error=urllib.error.HTTPError('https://query1.finance.yahoo.com/test',403,'Forbidden',{},None)
    opener=Mock(side_effect=error);transport=FeedTransport(opener,sleep=Mock())
    with pytest.raises(urllib.error.HTTPError):transport.fetch('https://query1.finance.yahoo.com/test','NIFTY')
    assert opener.call_count==1
    with pytest.raises(ValueError):transport.fetch('http://169.254.169.254/latest','NIFTY')
    with pytest.raises(ValueError):ProviderRedirects().redirect_request(None,None,302,'',{},'https://169.254.169.254/private')
