import json
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import auto_trader as A


def test_migrated_account_cannot_start_or_process_locally(tmp_path,monkeypatch):
    db=tmp_path/'account.sqlite3';marker=tmp_path/'cloud_migration.json'
    marker.write_text(json.dumps({'cloud_origin':'https://engine.example'}))
    monkeypatch.setattr(A,'MIGRATION_FILE',marker)
    monkeypatch.setattr(A,'STATUS_FILE',tmp_path/'runtime.json')
    monkeypatch.setattr(A.paper,'DEFAULT_DB',db)
    monkeypatch.setattr(A.feed,'refresh',Mock())
    monkeypatch.setattr(A.paper,'process',Mock())
    runner=A.AutoTrader(db=db);runner.entries_enabled=True
    assert runner.start()['state']=='migrated_to_cloud'
    assert runner.cycle()['state']=='migrated_to_cloud'
    assert not runner.entries_enabled
    A.feed.refresh.assert_not_called();A.paper.process.assert_not_called()


def test_migration_guard_does_not_block_separate_research_account(tmp_path,monkeypatch):
    marker=tmp_path/'cloud_migration.json';marker.write_text('{"cloud_origin":"https://engine.example"}')
    monkeypatch.setattr(A,'MIGRATION_FILE',marker)
    monkeypatch.setattr(A,'STATUS_FILE',tmp_path/'runtime.json')
    monkeypatch.setattr(A.paper,'DEFAULT_DB',tmp_path/'migrated.sqlite3')
    monkeypatch.setattr(A,'ROOT',tmp_path)
    source=tmp_path/A.C.INTRADAY_CSV;source.parent.mkdir(parents=True);source.touch()
    process=Mock(return_value={'status':'watching'})
    monkeypatch.setattr(A.paper,'process',process)
    runner=A.AutoTrader(db=tmp_path/'separate.sqlite3')
    runner.cycle(refresh=False,now=datetime(2026,11,16,10,tzinfo=ZoneInfo('Asia/Kolkata')))
    process.assert_called_once()
