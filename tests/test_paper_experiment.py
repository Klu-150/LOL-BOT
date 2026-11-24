import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import config as C
from experiment_manager import ExperimentManager
from paper_experiment import POLICY
from tests.test_cloud_server import request


def test_experiment_policy_and_replacement_are_isolated_in_a_child():
    code='''
import json
import config as C, intraday_engine as E
from tests.test_intraday import bar
from paper_experiment import install_policy
install_policy()
state=E.new_state(500000)
event,_=E.step(state,bar()[1],bar()[0])
assert event['action']=='open'
assert state['position']['lots']>5
assert state['position']['lots']*state['position']['risk_estimate_rs']<=125000
lots=state['position']['lots']
ts,row=bar('2026-11-16 10:05',ivr=10,iv_rv_ratio=.8)
event,closed=E.step(state,row,ts)
assert closed is None and event['action']=='hold'
ts,row=bar('2026-11-16 10:10',ivr=10,iv_rv_ratio=.8)
event,closed=E.step(state,row,ts)
assert closed and closed['exit_reason']=='confirmed_structure_change'
ts,row=bar('2026-11-16 10:15',ivr=10,iv_rv_ratio=.8)
event,_=E.step(state,row,ts)
assert event['action']=='open' and state['position']['strategy']=='bull_call_spread'
ts,row=bar('2026-11-16 15:15',ivr=10,iv_rv_ratio=.8)
_,last=E.step(state,row,ts)
assert state['equity']==500000+closed['net_pnl_rs']+last['net_pnl_rs'] or abs(state['equity']-500000-closed['net_pnl_rs']-last['net_pnl_rs'])<1e-6
print(json.dumps({'lots':lots,'switch':closed['exit_reason'],'accounting_reconciled':True}))
'''
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['lots']>5
    assert C.RISK_PER_TRADE==.02 and C.MAX_LOTS==5,'Parent/baseline settings must remain unchanged'


def test_supervisor_routes_controls_only_to_its_own_files(tmp_path):
    manager=ExperimentManager(tmp_path)
    manager.ensure=Mock()
    assert not manager.status()['configured']
    manager.start()
    assert manager.enabled() and not (tmp_path/'cloud_control.json').exists()
    manager.pause()
    assert not manager.enabled()
    assert POLICY['risk_fraction']==.25
    manager.control.write_text('{broken')
    assert manager.status()['state']=='error' and not manager.status()['enabled']


def test_experiment_actions_require_trader_and_use_idempotency(app):
    app.experiment.start=Mock(return_value={'enabled':True,'profile':POLICY})
    app.experiment.pause=Mock(return_value={'enabled':False,'profile':POLICY})
    assert request(app,'/api/experiment/start',method='POST',name='friend')['status']==403
    key='experiment-key-12345678'
    first=request(app,'/api/experiment/start',method='POST',HTTP_IDEMPOTENCY_KEY=key)
    second=request(app,'/api/experiment/start',method='POST',HTTP_IDEMPOTENCY_KEY=key)
    assert first['status']==second['status']==200
    app.experiment.start.assert_called_once()
    app.runtime.trader.start.assert_not_called()
    assert request(app,'/api/experiment/pause',method='POST')['status']==200
    app.runtime.trader.pause.assert_not_called()


def test_experiment_snapshot_does_not_fall_back_to_baseline_account(app,monkeypatch):
    import cloud_server as S
    seen=[]
    def snapshot(**kwargs):seen.append(kwargs);return {'paper':{'available':False},'reports':[{}]}
    monkeypatch.setattr(S,'build_snapshot',snapshot)
    assert request(app,'/api/experiment/dashboard')['status']==200
    assert seen[0]['account_path']==app.experiment.db
    assert seen[0]['policy']['id']=='adaptive25'


from tests.test_cloud_server import app  # shared isolated API fixture


def test_pause_acknowledgement_waits_for_inflight_worker_lock(tmp_path):
    import fcntl
    import threading
    manager=ExperimentManager(tmp_path);manager.ensure=Mock();manager.start()
    done=threading.Event()
    with (tmp_path/'experiment25-control.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        thread=threading.Thread(target=lambda:(manager.pause(),done.set()));thread.start()
        assert not done.wait(.1)
        assert manager.enabled()
        fcntl.flock(handle,fcntl.LOCK_UN)
    thread.join(timeout=2)
    assert done.is_set() and not manager.enabled()


def test_actual_worker_initializes_only_experiment_and_stops_cleanly(tmp_path):
    import time
    from paper_experiment import DB_NAME,STATUS_NAME
    manager=ExperimentManager(tmp_path)
    try:
        manager.start()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if (tmp_path/STATUS_NAME).exists():break
            assert manager.process.poll() is None,'Worker exited before reporting readiness'
            time.sleep(.05)
        value=manager.status()
        assert value['worker_alive'] and value['enabled'] and value['checked_at']
        import intraday_paper as P
        account=P.snapshot(tmp_path/DB_NAME)
        assert account['initial_capital']==500000 and not account['position']
        assert not (tmp_path/'intraday_500k.sqlite3').exists()
    finally:
        manager.close()
    assert manager.process.poll() == 0


def test_monitor_rejects_experimental_feed_failure_and_future_heartbeat(app):
    from datetime import datetime,timedelta,timezone
    import cloud_server as C
    stamp=datetime.now(timezone.utc)
    for state,checked in [('awaiting_fresh_market_data',stamp),('storage_guard',stamp),('market_closed',stamp+timedelta(minutes=3))]:
        app.experiment.status=Mock(return_value={'configured':True,'worker_alive':True,'state':state,'checked_at':checked.isoformat()})
        assert 'paper_experiment_needs_attention' in app.monitor()['alerts']


def test_alive_but_stale_experiment_is_recycled_without_restarting_feed_errors(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    import experiment_manager as M
    manager=M.ExperimentManager(tmp_path);old=Mock();old.poll.return_value=None
    manager.process=old;manager.last_launch=1
    monkeypatch.setattr(M.time,'monotonic',lambda:1000)
    spawn=Mock();monkeypatch.setattr(M.subprocess,'Popen',spawn)
    manager.status=Mock(return_value={'checked_at':datetime.now(timezone.utc).isoformat(),'state':'data_error'})
    manager.ensure();old.terminate.assert_not_called();spawn.assert_not_called()
    manager.status.return_value={'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()}
    manager.ensure();old.terminate.assert_called_once();spawn.assert_called_once()


def test_supervisor_rejects_well_formed_but_wrong_state_types(tmp_path):
    from paper_experiment import STATUS_NAME
    manager=ExperimentManager(tmp_path)
    manager.control.write_text('[]')
    assert manager.status()['state']=='error' and not manager.status()['enabled']
    manager.control.write_text('{"enabled":false}')
    (tmp_path/STATUS_NAME).write_text('[]')
    assert manager.status()['state']=='error'
