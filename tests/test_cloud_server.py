import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import cloud_server as C
from cloud_bootstrap import seed_storage

ORIGIN = 'https://nifty-research-terminal.nearbydrape.chatgpt.site'
KEY = 'test-only-access-key-not-a-real-secret-123456'


def settings():
    return C.Settings({name: {'sha256': hashlib.sha256(KEY.encode()).hexdigest(), 'role': role}
                       for name, role in [('owner', 'trader'), ('friend', 'viewer')]}, {ORIGIN})


@pytest.fixture
def app(tmp_path):
    runtime = SimpleNamespace(trader=SimpleNamespace(status={'enabled': False, 'state': 'stopped'},
                              start=Mock(return_value={'enabled': True}), pause=Mock(return_value={'enabled': False})),
                              jobs={}, backtest=Mock(return_value={'id': 'test-job', 'status': 'running'}))
    return C.create_app(settings(), runtime, tmp_path/'control.json')


def request(app, path='/api/health', method='GET', name='owner', key=KEY, origin=ORIGIN, **extra):
    env={'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ORIGIN': origin,
         'HTTP_AUTHORIZATION': f'Bearer {name}.{key}', 'CONTENT_TYPE':'application/json',
         'CONTENT_LENGTH':'2', 'wsgi.input':io.BytesIO(b'{}'), **extra}
    result={}
    def start(status, headers):
        result.update(status=int(status.split()[0]), headers=dict(headers))
    body=b''.join(app(env,start))
    result['body']=json.loads(body) if body else None
    return result


@pytest.mark.parametrize('name,key', [('owner','wrong'),('absent',KEY),('',KEY)])
def test_private_paper_data_requires_valid_user_key(app,name,key):
    assert request(app,name=name,key=key)['status']==401
    app.runtime.trader.start.assert_not_called()


def test_health_returns_permissions_without_credentials(app):
    result=request(app)
    assert result['body']['execution']=='cloud'
    assert result['body']['permissions']['control']
    assert KEY not in json.dumps(result)
    assert 'sha256' not in json.dumps(result)
    assert result['headers']['Access-Control-Allow-Origin']==ORIGIN
    assert result['headers']['Cache-Control']=='no-store'


def test_viewer_cannot_start_pause_or_backtest(app):
    assert not request(app,name='friend')['body']['permissions']['control']
    for path in ['/api/automation/start','/api/automation/pause','/api/backtest/run']:
        assert request(app,path,method='POST',name='friend')['status']==403
    app.runtime.trader.start.assert_not_called()
    app.runtime.trader.pause.assert_not_called()
    app.runtime.backtest.assert_not_called()
    assert not app.control_path.exists()


def test_authorised_controls_persist_enable_state(app):
    assert request(app,'/api/automation/start','POST')['body']['enabled']
    app.runtime.trader.start.assert_called_once()
    assert json.loads(app.control_path.read_text())=={'enabled':True}
    assert not request(app,'/api/automation/pause','POST')['body']['enabled']
    assert json.loads(app.control_path.read_text())=={'enabled':False}
    assert request(app,'/api/backtest/run','POST')['status']==202


def test_cross_origin_and_preflight_policy(app):
    assert request(app,origin='https://untrusted.example')['status']==403
    assert 'Access-Control-Allow-Origin' not in request(app,origin='https://untrusted.example')['headers']
    result=request(app,method='OPTIONS',key='invalid')
    assert result['status']==204
    assert result['headers']['Access-Control-Allow-Headers']=='Authorization, Content-Type, Idempotency-Key'
    assert request(app,origin='')['status']==200 # Authenticated non-browser API use is allowed.


def test_no_unprotected_data_or_real_order_endpoint(app,monkeypatch):
    assert request(app,'/healthz',key='bad')['body']=={'status':'ok','mode':'paper'}
    assert request(app,'/api/orders/real','POST')['status']==404
    monkeypatch.setattr(C,'build_snapshot',Mock(return_value={'paper':{'trades':[]}}))
    assert request(app,'/api/dashboard')['body']=={'paper':{'trades':[]}}
    assert request(app,'/api/automation/start','POST',CONTENT_LENGTH='2000')['status']==413


def test_server_errors_do_not_expose_secrets(app,monkeypatch):
    monkeypatch.setattr(C,'build_snapshot',Mock(side_effect=ValueError('private details')))
    result=request(app,'/api/dashboard')
    assert result['status']==500
    assert 'private details' not in json.dumps(result)


def test_missing_or_unsafe_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv('LEAGUE_USERS_JSON',raising=False)
    monkeypatch.delenv('LEAGUE_ORIGINS',raising=False)
    with pytest.raises(ValueError,match='Configure'): C.Settings.from_env()
    monkeypatch.setenv('LEAGUE_USERS_JSON',json.dumps(settings().users))
    monkeypatch.setenv('LEAGUE_ORIGINS','*')
    with pytest.raises(ValueError,match='HTTPS'): C.Settings.from_env()


def test_duplicate_engine_process_rejected_and_paused_state_restored(tmp_path,monkeypatch):
    runtime=SimpleNamespace(trader=SimpleNamespace(start=Mock(),pause=Mock()),close=Mock())
    monkeypatch.setattr(C,'TerminalRuntime',Mock(return_value=runtime))
    path=tmp_path/'control.json';path.write_text('{"enabled":false}')
    config=settings();config.auto_start=True
    first=C.create_app(config,control_path=path)
    try:
        runtime.trader.pause.assert_called_once()
        runtime.trader.start.assert_not_called()
        with pytest.raises(RuntimeError,match='one hosted paper engine'):
            C.create_app(config,control_path=path)
    finally:
        first.engine_lock.close()


def test_volume_seeding_preserves_existing_account_and_data(tmp_path):
    root=tmp_path/'image';seed=root/'seed-data';seed.mkdir(parents=True)
    (seed/'market.csv').write_text('seed market')
    state=tmp_path/'state';(state/'data').mkdir(parents=True)
    (state/'data'/'market.csv').write_text('newer market')
    (state/'paper').mkdir();ledger=state/'paper'/'account.sqlite3';ledger.write_bytes(b'preserved account')
    seed_storage(state,root)
    assert (state/'data'/'market.csv').read_text()=='newer market'
    assert ledger.read_bytes()==b'preserved account'
