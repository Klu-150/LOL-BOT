from datetime import datetime,timezone
import json
import sqlite3
import pytest
from offhost_backup import package_snapshot
from operations import BackupManager
from tools.recovery_drill import extract_verified,account_bodies
import intraday_engine as E


def archive(tmp_path,position=None):
    source=tmp_path/'original';source.mkdir();db=source/'intraday_500k.sqlite3'
    state=E.new_state(500000);state['position']=position
    with sqlite3.connect(db) as conn:
        conn.execute('create table account(id integer primary key,body text)')
        conn.execute('insert into account values(1,?)',(json.dumps(state),))
    manager=BackupManager(db,source/'backups');manager.run_once()
    output=tmp_path/'verified.gz';package_snapshot(source/'backups',output)
    return output.read_bytes(),db


def test_drill_restores_to_new_directory_only_and_forces_entries_off(tmp_path):
    payload,original=archive(tmp_path);before=original.read_bytes()
    destination=tmp_path/'drill'
    bodies=extract_verified(payload,destination)
    assert len(bodies)==1 and bodies['intraday_500k.sqlite3']['equity']==500000
    assert account_bodies(destination/'state/paper')==bodies
    for name in ('cloud_control.json','experiment25-control.json'):
        assert json.loads((destination/'state/paper'/name).read_text())['enabled'] is False
    assert original.read_bytes()==before
    with pytest.raises(ValueError,match='new'):extract_verified(payload,destination)
    assert not (destination/'state/paper/private-access.json').exists()


def test_drill_refuses_open_positions_and_corrupt_archives(tmp_path):
    payload,_=archive(tmp_path,{'strategy':'example'})
    with pytest.raises(ValueError,match='flat'):extract_verified(payload,tmp_path/'drill')
    with pytest.raises(Exception):extract_verified(b'corrupt',tmp_path/'bad')
