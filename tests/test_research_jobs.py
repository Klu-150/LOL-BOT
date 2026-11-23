from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import threading
from unittest.mock import Mock

import pytest

import dashboard as D
import operations
from tests.test_reliability import seed_ledger


def test_research_job_deduplicates_and_persists_without_replay(tmp_path,monkeypatch):
    began=threading.Event();release=threading.Event()
    class Process:
        returncode=0
        def communicate(self,timeout=None):
            began.set();assert release.wait(5);return '{"ok":true}',''
        def poll(self):return 0
        def terminate(self):release.set()
    popen=Mock(return_value=Process())
    monkeypatch.setattr('subprocess.Popen',popen)
    monkeypatch.setattr(D,'AutoTrader',Mock())
    runtime=D.TerminalRuntime(state_dir=tmp_path)
    first=runtime.backtest();assert began.wait(5)
    with ThreadPoolExecutor(max_workers=8) as pool:duplicates=list(pool.map(lambda _:runtime.backtest(),range(20)))
    assert all(job['id']==first['id'] for job in duplicates)
    assert popen.call_count==1
    release.set();runtime.pool.shutdown(wait=True)
    persisted=json.loads(runtime.jobs_path.read_text())
    assert persisted[first['id']]['status']=='completed'
    persisted[first['id']]['status']='running'
    runtime.jobs_path.write_text(json.dumps(persisted))
    restarted=D.TerminalRuntime(state_dir=tmp_path)
    assert restarted.jobs_snapshot()[0]['status']=='interrupted'
    assert popen.call_count==1
    runtime.close();restarted.close()


def test_research_history_is_bounded(tmp_path,monkeypatch):
    monkeypatch.setattr(D,'AutoTrader',Mock())
    runtime=D.TerminalRuntime(state_dir=tmp_path)
    runtime.jobs={str(i):{'id':str(i),'status':'completed'} for i in range(100)}
    runtime._persist_jobs()
    assert len(runtime.jobs_snapshot())==20
    assert list(json.loads(runtime.jobs_path.read_text()))==[str(i) for i in range(80,100)]
    runtime.close()


def test_backup_does_not_fill_the_trading_disk(tmp_path,monkeypatch):
    db=tmp_path/'account.sqlite3';seed_ledger(db,1)
    before=db.read_bytes()
    monkeypatch.setattr(operations.shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    manager=operations.BackupManager(db,tmp_path/'backups')
    with pytest.raises(OSError,match='headroom'):manager.run_once()
    assert db.read_bytes()==before
    assert not list((tmp_path/'backups').iterdir())
