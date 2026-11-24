from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest
from offhost_backup import package_snapshot,run,status,verify_restore,BlobStore
from operations import BackupManager


def snapshots(root):
    db=root/'intraday_500k.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE account(body TEXT)')
        conn.execute('INSERT INTO account VALUES(?)',('{"equity":500000}',))
    manager=BackupManager(db,root/'backups');manager.run_once()
    return root/'backups'


def test_round_trip_restores_only_database_snapshots(tmp_path):
    directory=snapshots(tmp_path)
    (tmp_path/'private-access.json').write_text('SECRET-NEVER-EXPORT')
    class Store:
        def upload(self,name,payload,digest):
            assert name.startswith('accounts/') and 'SECRET-NEVER-EXPORT' not in str(payload)
            assert hashlib.sha256(payload).hexdigest()==digest
            return payload
    path=tmp_path/'offhost-backup.json';result=run(directory,path,Store())
    assert result['restore_verified'] and status(path,True)['off_host']
    assert result['bytes']>0 and path.stat().st_mode & 0o777==0o600


def test_manifest_corruption_traversal_and_stale_inputs_fail(tmp_path):
    directory=snapshots(tmp_path);manifest=next(directory.glob('*.json'))
    original=json.loads(manifest.read_text());broken=json.loads(manifest.read_text())
    broken['files'][0]['file']='../private-access.json';manifest.write_text(json.dumps(broken))
    with pytest.raises(ValueError):package_snapshot(directory,tmp_path/'x.gz')
    manifest.write_text(json.dumps(original));next(directory.glob('*.sqlite3')).write_bytes(b'corrupt')
    with pytest.raises(ValueError):package_snapshot(directory,tmp_path/'x.gz')
    original['at']=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat();manifest.write_text(json.dumps(original))
    with pytest.raises(ValueError):package_snapshot(directory,tmp_path/'x.gz')


def test_status_never_claims_stale_or_failed_backup_is_off_host(tmp_path):
    path=tmp_path/'status.json'
    assert status(path,True)['state']=='missing'
    path.write_text(json.dumps({'state':'ok','last_success_at':(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()}))
    assert status(path,True)['state']=='stale'
    path.write_text(json.dumps({'state':'error','last_success_at':datetime.now(timezone.utc).isoformat()}))
    assert not status(path,True)['off_host']
    assert status(path,False)['state']=='not_configured'


def test_restore_rejects_unsafe_tar_members():
    blob=io.BytesIO()
    with tarfile.open(fileobj=blob,mode='w:gz') as archive:
        for name in ['../bad','metadata.json']:
            entry=tarfile.TarInfo(name);entry.size=2;archive.addfile(entry,io.BytesIO(b'{}'))
    with pytest.raises(ValueError):verify_restore(blob.getvalue())


@pytest.mark.parametrize('account',['https://evil.example','name/path','abc@evil','a'])
def test_destination_is_not_an_arbitrary_upload_url(account):
    with pytest.raises(ValueError):BlobStore(account,token='never-sent')


def test_failed_offhost_backup_degrades_readiness_when_required(tmp_path):
    from types import SimpleNamespace
    import cloud_server as C
    from tests.test_cloud_server import settings
    trader=SimpleNamespace(status={'enabled':True,'state':'market_closed','checked_at':datetime.now(timezone.utc).isoformat()})
    app=C.create_app(settings(),SimpleNamespace(trader=trader,jobs={}),tmp_path/'control.json')
    assert app.monitor()['offhost_backup']['state']=='not_configured'
    (tmp_path/'offhost-required').touch()
    assert 'offhost_backup_missing' in app.monitor()['alerts']
    (tmp_path/'offhost-backup.json').write_text(json.dumps({'state':'ok','last_success_at':datetime.now(timezone.utc).isoformat(),'restore_verified':True}))
    assert app.monitor()['offhost_backup']['off_host']
    assert not any('offhost' in item for item in app.monitor()['alerts'])


def test_experiment_and_baseline_both_restore_without_exporting_other_files(tmp_path):
    directory=snapshots(tmp_path)
    source=tmp_path/'intraday_experiment25.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('create table account(body text)')
        db.execute('insert into account values(?)',('{"equity":500000,"profile":"adaptive25"}',))
    BackupManager(tmp_path/'intraday_500k.sqlite3',directory).run_once()
    output=tmp_path/'roundtrip.gz'
    metadata,_=package_snapshot(directory,output)
    assert len(metadata['files'])==2
    assert any(x['file'].endswith('-intraday_experiment25.sqlite3') for x in metadata['files'])
    assert verify_restore(output.read_bytes())
    blob=io.BytesIO()
    with tarfile.open(output) as original,tarfile.open(fileobj=blob,mode='w:gz') as archive:
        for member in original.getmembers():archive.addfile(member,original.extractfile(member))
        member=tarfile.TarInfo('private-access.json');member.size=2;archive.addfile(member,io.BytesIO(b'{}'))
    with pytest.raises(ValueError):verify_restore(blob.getvalue())


def test_backup_and_restore_hashes_stream_database_files(tmp_path,monkeypatch):
    directory=snapshots(tmp_path);output=tmp_path/'streamed.tar.gz'
    def no_unbounded_reads(path):raise AssertionError('Whole-file read is forbidden for database hashing')
    monkeypatch.setattr(Path,'read_bytes',no_unbounded_reads)
    package_snapshot(directory,output)
    with output.open('rb') as stream:payload=stream.read()
    assert verify_restore(payload)
    import offhost_backup as B
    monkeypatch.setattr(B,'MAX_RESTORE_BYTES',1)
    with pytest.raises(ValueError):verify_restore(payload)
