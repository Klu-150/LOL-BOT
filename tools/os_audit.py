"""Compare installed Debian source-package versions with OSV's public database.

Fails on advisories with an available Debian fix. Unfixed advisories remain
explicit review items: a passing gate is not a clean bill of health. Sends only
public package names/versions to a fixed HTTPS endpoint; never reads app state.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import re
from pathlib import Path
import subprocess
import sys
import urllib.request

ENDPOINT='https://api.osv.dev/v1/'


def compare(installed,fixed):
    if any(not isinstance(value,str) or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,150}',value) for value in (installed,fixed)):
        raise ValueError('Invalid Debian version')
    code=subprocess.run(['dpkg','--compare-versions',installed,'lt',fixed],check=False).returncode
    if code not in (0,1):raise ValueError('Debian version comparison failed')
    return code==0


def fixes_for(record,package,version,ecosystem,older=compare):
    if record.get('withdrawn'):return []
    fixes=set()
    for affected in record.get('affected',[]):
        identity=affected.get('package',{})
        if identity.get('name')!=package or identity.get('ecosystem')!=ecosystem:continue
        for interval in affected.get('ranges',[]):
            for event in interval.get('events',[]):
                fixed=event.get('fixed')
                if isinstance(fixed,str) and fixed and older(version,fixed):fixes.add(fixed)
    return sorted(fixes)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Vulnerability endpoint redirect refused')


def request(path,payload=None):
    opener=urllib.request.build_opener(NoRedirect())
    req=urllib.request.Request(ENDPOINT+path,data=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Content-Type':'application/json'},method='POST' if payload is not None else 'GET')
    with opener.open(req,timeout=30) as response:
        raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Oversized vulnerability response')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Invalid vulnerability response')
    return value


def audit():
    release={}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1);release[key]=value.strip('"')
    if release.get('ID')!='debian' or not release.get('VERSION_ID','').isdigit():raise ValueError('Debian source-package audit requires a Debian runtime')
    ecosystem='Debian:'+release['VERSION_ID']
    inventory=subprocess.check_output(['dpkg-query','-W','-f','${source:Package} ${source:Version}\n'],text=True,timeout=15)
    pairs=sorted({tuple(line.split()) for line in inventory.splitlines() if len(line.split())==2})
    if not 1<=len(pairs)<=1000:raise ValueError('Unexpected package inventory size')
    queries=[{'package':{'ecosystem':ecosystem,'name':name},'version':version} for name,version in pairs]
    result=request('querybatch',{'queries':queries})
    if not isinstance(result.get('results'),list) or len(result['results'])!=len(queries):raise ValueError('Incomplete vulnerability scan')
    ids=sorted({v['id'] for row in result['results'] for v in row.get('vulns',[])})
    if len(ids)>2000 or any(not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',key) for key in ids):raise ValueError('Invalid advisory identifiers')
    with ThreadPoolExecutor(max_workers=4) as pool:records=dict(zip(ids,pool.map(lambda key:request('vulns/'+key),ids)))
    findings=[]
    for (package,version),row in zip(pairs,result['results']):
        for match in row.get('vulns',[]):
            key=match['id'];record=records[key]
            if record.get('id')!=key:raise ValueError('Advisory mismatch')
            if record.get('withdrawn'):continue
            fixed=fixes_for(record,package,version,ecosystem)
            findings.append({'advisory':key,'package':package,'installed':version,'available_fixes':fixed,'blocking':bool(fixed)})
    return {'at':datetime.now(timezone.utc).isoformat(),'source':ENDPOINT,'ecosystem':ecosystem,
        'source_packages':len(pairs),'advisory_matches':len(findings),'with_available_fixes':sum(r['blocking'] for r in findings),
        'unfixed_review_items':sum(not r['blocking'] for r in findings),'findings':findings,
        'scope':'OS package advisories; Python locks scanned separately. Does not assess reachability or certify security.'}


if __name__=='__main__':
    try:
        result=audit();print(json.dumps(result,indent=2));raise SystemExit(bool(result['with_available_fixes']))
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({'scan_complete':False,'error_type':type(error).__name__}));raise SystemExit(2)
