"""Off-host recovery rehearsal, only in a NEW marked directory/container.

Never restores over the live volume. The verifier has no network, production
credentials or published ports. Reports contain hashes/counts, not account bodies.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from operations import atomic_json
from offhost_backup import BlobStore,MAX_BYTES,verify_restore

ACCOUNTS=('intraday_500k.sqlite3','intraday_experiment25.sqlite3')
RESTORABLE=(*ACCOUNTS,'operations.sqlite3')


def account_bodies(paper):
    result={}
    for name in ACCOUNTS:
        path=paper/name
        if not path.exists():continue
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            assert db.execute('pragma integrity_check').fetchone()[0]=='ok','Corrupt recovery account'
            result[name]=json.loads(db.execute('select body from account where id=1').fetchone()[0])
    if 'intraday_500k.sqlite3' not in result:raise ValueError('Baseline recovery account missing')
    return result


def extract_verified(payload,destination):
    verify_restore(payload)
    destination=Path(destination)
    if destination.exists():raise ValueError('Recovery destination must be new')
    destination.mkdir(parents=True,mode=0o700)
    atomic_json(destination/'RECOVERY_DRILL_ONLY',{'mode':'isolated_rehearsal'})
    state=destination/'state';paper=state/'paper';paper.mkdir(parents=True,mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        manifests=[member for member in archive.getmembers() if member.name.endswith('.json')]
        metadata=json.load(archive.extractfile(manifests[0]))
        for item in metadata['files']:
            names=[name for name in RESTORABLE if item['file'].endswith('-'+name)]
            if len(names)!=1:raise ValueError('Unknown recovery database')
            path=paper/names[0]
            if path.exists():raise ValueError('Duplicate recovery target')
            with archive.extractfile(item['file']) as source,path.open('wb') as target:
                shutil.copyfileobj(source,target,length=1024*1024)
            path.chmod(0o600)
    accounts=account_bodies(paper)
    if any(body['position'] is not None for body in accounts.values()):
        raise ValueError('Use a flat snapshot for the no-trading boot rehearsal')
    for control in ('cloud_control.json','experiment25-control.json'):
        atomic_json(paper/control,{'enabled':False})
    atomic_json(destination/'manifest.json',{'snapshot_at':metadata['at'],'archive_sha256':hashlib.sha256(payload).hexdigest(),
        'accounts':list(accounts),'prepared_at':datetime.now(timezone.utc).isoformat()})
    return accounts


def prepare(account,destination):
    base=ROOT/'paper';destination=Path(destination).resolve()
    permitted=(base/'recovery-drills').resolve()
    if destination.parent!=permitted or not destination.name.startswith('drill-'):
        raise ValueError('Use paper/recovery-drills/drill-<stamp> only')
    status=json.loads((base/'offhost-backup.json').read_text())
    if status.get('state')!='ok' or not status.get('restore_verified'):raise ValueError('No verified off-host snapshot')
    matches=[]
    for path in (base/'backups').glob('*.json'):
        meta=json.loads(path.read_text())
        if meta.get('at')==status['snapshot_at']:matches.append((path,meta))
    if len(matches)!=1:raise ValueError('Remote snapshot manifest unavailable locally; operator recovery required')
    manifest,metadata=matches[0]
    stamp=datetime.fromisoformat(metadata['at'])
    name=stamp.strftime('accounts/%Y/%m/%d/')+manifest.stem+'.tar.gz'
    with BlobStore(account).request('GET',name) as response:payload=response.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES or hashlib.sha256(payload).hexdigest()!=status['sha256']:raise ValueError('Remote archive hash mismatch')
    accounts=extract_verified(payload,destination)
    import config as C
    cutoff=min(body['last_timestamp'] for body in accounts.values() if body.get('last_timestamp'))
    data=destination/'state/data';data.mkdir(mode=0o700)
    import pandas as pd
    for name in (C.NIFTY_CSV,C.VIX_CSV,C.INTRADAY_CSV):
        source=ROOT/name;target=data/source.name
        if name==C.INTRADAY_CSV:
            frame=pd.read_csv(source)
            frame=frame.loc[pd.to_datetime(frame['timestamp'],utc=True)<=pd.Timestamp(cutoff)]
            frame.to_csv(target,index=False)
        else:shutil.copy2(source,target)
    print(json.dumps({'prepared':True,'accounts':len(accounts),'remote_download_verified':True}))


def verify(state):
    state=Path(state).resolve()
    if state!=Path('/state') or not (state.parent/'RECOVERY_DRILL_ONLY').exists():
        # The isolated container mounts its marker explicitly at a fixed path.
        if state!=Path('/state') or not Path('/recovery-marker').is_file():raise ValueError('Recovery container marker missing')
    from cloud_bootstrap import seed_storage
    seed_storage(state)
    before=account_bodies(state/'paper')
    for body in before.values():
        assert body['position'] is None
        assert all((ROOT/name).is_file() and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in body['fingerprint'].items()),'Pinned strategy mismatch'
    import cloud_server as C
    key='recovery-fixture-only-not-a-production-access-key'
    settings=C.Settings({'rehearsal':{'role':'viewer','sha256':hashlib.sha256(key.encode()).hexdigest()}},{'https://recovery.invalid'})
    app=C.create_app(settings,control_path=state/'paper/cloud_control.json')
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if app.runtime.trader.status.get('checked_at') and (len(before)==1 or app.experiment.status().get('checked_at')):break
            time.sleep(.1)
        def request(path,method='GET',auth=True):
            env={'REQUEST_METHOD':method,'PATH_INFO':path,'HTTP_ORIGIN':'https://recovery.invalid',
                'CONTENT_TYPE':'application/json','CONTENT_LENGTH':'2','wsgi.input':io.BytesIO(b'{}')}
            if auth:env['HTTP_AUTHORIZATION']='Bearer rehearsal.'+key
            result={}
            body=b''.join(app(env,lambda status,headers:result.update(code=int(status.split()[0]),headers=dict(headers))))
            return result,json.loads(body)
        for path in ('/api/dashboard','/api/experiment/dashboard') if len(before)>1 else ('/api/dashboard',):
            response,body=request(path);assert response['code']==200 and body['paper']['available']
            assert response['headers']['Cache-Control']=='no-store'
        assert request('/api/dashboard',auth=False)[0]['code']==401
        assert request('/api/automation/start','POST')[0]['code']==403
        assert request('/api/experiment/start','POST')[0]['code']==403
        assert not app.runtime.trader.entries_enabled and not app.experiment.enabled()
    finally:
        app.watchdog.close();app.experiment.close();app.runtime.close();app.backups.close();app.engine_lock.close()
    assert before==account_bodies(state/'paper'),'Recovery boot changed account state'
    print(json.dumps({'boot_verified':True,'accounts_verified':len(before),'policy_hashes_verified':True,
        'entries_disabled':True,'authenticated_dashboard_verified':True,'viewer_control_rejected':True,
        'exact_account_preservation':True,'broker_execution':False,'version':C.VERSION}))


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--account',required=True);p.add_argument('--destination',type=Path,required=True)
    p=sub.add_parser('verify');p.add_argument('--state',type=Path,default=Path('/state'))
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.account,args.destination)
    else:verify(args.state)
