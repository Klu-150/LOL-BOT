"""Low-rate read-only HTTPS readiness observations; no trading credentials/actions."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

URL='https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com/readyz'


def probe():
    start=time.monotonic();code=None;error=None
    try:
        with urllib.request.urlopen(URL,timeout=15,context=ssl.create_default_context()) as response:
            code=response.status;data=json.loads(response.read(1024))
            ok=code==200 and data=={'status':'ready','mode':'paper'}
    except urllib.error.HTTPError as exc:
        code=exc.code;exc.close();ok=False;error='http_error'
    except (OSError,ValueError):
        ok=False;error='connection_or_invalid_response'
    return {'at':datetime.now(timezone.utc).isoformat(),'ready':ok,'http_status':code,
            'latency_ms':round((time.monotonic()-start)*1000,2),'error':error}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes',type=int,default=10)
    parser.add_argument('--output',type=Path,default=Path('results/readiness-soak.jsonl'))
    args=parser.parse_args()
    if not 1<=args.minutes<=10080:parser.error('Use 1..10080 minutes')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for number in range(args.minutes):
        row=probe()
        with args.output.open('a') as file:file.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
        if number+1<args.minutes:time.sleep(60)


if __name__=='__main__':main()
