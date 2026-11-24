"""Low-rate HTTPS readiness evidence. Missing observations are gaps, not uptime."""
import argparse
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from operations import atomic_json

URL='https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com/readyz'
MAX_ROWS=10080  # 35 days at a 5-minute cadence
MAX_BYTES=4*1024*1024


def probe():
    start=time.monotonic();code=None;error=None
    try:
        with urllib.request.urlopen(URL,timeout=15,context=ssl.create_default_context()) as response:
            code=response.status;data=json.loads(response.read(1024))
            ok=code==200 and data=={'status':'ready','mode':'paper'}
    except urllib.error.HTTPError as exc:
        code=exc.code;exc.close();ok=False;error='http_error'
    except (OSError,ValueError):ok=False;error='connection_or_invalid_response'
    return {'at':datetime.now(timezone.utc).isoformat(),'ready':ok,'http_status':code,
            'latency_ms':round((time.monotonic()-start)*1000,2),'error':error}


def summarize(rows,now=None):
    now=now or datetime.now(timezone.utc)
    times=[datetime.fromisoformat(row['at']) for row in rows]
    if any(stamp.tzinfo is None for stamp in times) or any(a>=b for a,b in zip(times,times[1:])):
        raise ValueError('Soak evidence must be timezone-aware and strictly chronological')
    if not times:return {'state':'not_started','qualified':False,'samples':0}
    # Assess the most recent continuous seven days, retaining older history for diagnosis.
    cutoff=times[-1].timestamp()-7*86400
    start=max(0,next((i for i,stamp in enumerate(times) if stamp.timestamp()>=cutoff),0)-1)
    rows=rows[start:];times=times[start:]
    span=(times[-1]-times[0]).total_seconds()
    age=(now-times[-1]).total_seconds()
    gaps=[(b-a).total_seconds() for a,b in zip(times,times[1:])]
    success=sum(row.get('ready') is True for row in rows)
    expected=max(1,int(span/300)+1)
    coverage=min(1,len(rows)/expected)
    qualified=span>=7*86400 and success==len(rows) and max(gaps,default=0)<=900 and coverage>=.99 and -60<=age<=900
    return {'state':'qualified_7_day_observation' if qualified else 'collecting_or_failed','qualified':qualified,
            'scope':'HTTPS sampled readiness, not strategy profitability or real fills; same-VM observer, external Azure probes are separate',
            'samples':len(rows),'successes':success,'failures':len(rows)-success,'coverage_fraction':round(coverage,4),
            'observed_seconds':span,'maximum_gap_seconds':max(gaps,default=0),'last_sample_age_seconds':round(age,1),
            'first_at':times[0].isoformat(),'last_at':times[-1].isoformat(),'target_days':7}


def record(path,row):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists() and path.stat().st_size>MAX_BYTES:raise ValueError('Oversized soak evidence')
        rows=[json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []
        rows=(rows+[row])[-MAX_ROWS:]
        result=summarize(rows)
        temporary=path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            os.chmod(temporary,0o600)
            for value in rows:stream.write(json.dumps(value,separators=(',',':'))+'\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        atomic_json(path.with_suffix('.summary.json'),result)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes',type=int,default=10)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('results/readiness-soak.jsonl'))
    args=parser.parse_args()
    if not 1<=args.minutes<=10080:parser.error('Use 1..10080 minutes')
    os.umask(0o077)
    for number in range(1 if args.once else args.minutes):
        row=probe();record(args.output,row);print(json.dumps(row),flush=True)
        if not args.once and number+1<args.minutes:time.sleep(60)


if __name__=='__main__':main()
