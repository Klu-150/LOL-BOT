"""Measure synthetic history, transactions and HTTP load without live accounts.

Runs one Gunicorn worker/four threads on loopback, matching production worker
counts. Hardware, TLS, WAN, broker fills and exchange throughput are not tested.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import intraday_paper as P
import ledger_store as L
from operations import backup_database
from tools.capacity_fixture import TEST_KEY, synthetic_closed_trade


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trades',type=int,default=100000)
    parser.add_argument('--clients',type=int,default=16,choices=range(1,33))
    parser.add_argument('--requests',type=int,default=50,choices=range(1,151))
    parser.add_argument('--output',type=Path,default=ROOT/'results/capacity.json')
    args=parser.parse_args()
    if not 1<=args.trades<=1000000:parser.error('Use 1..1,000,000 synthetic trades')
    with tempfile.TemporaryDirectory(prefix='league-capacity-') as temporary:
        root=Path(temporary);(root/'BENCHMARK_ONLY').touch();(root/'paper').mkdir()
        # Only public price inputs and a fresh synthetic report enter the fixture.
        (root/'data').mkdir();(root/'results').mkdir()
        for name in (P.C.NIFTY_CSV,P.C.VIX_CSV,P.C.INTRADAY_CSV):
            source=ROOT/name
            if source.is_file():shutil.copy2(source,root/'data'/source.name)
        (root/'results/results.json').write_text(json.dumps({'label':'Synthetic capacity fixture',
            'summary':[{'strategy':'FIXTURE','total_rs':0,'trades':0}],
            'equity':{'FIXTURE':[['2026-11-16',0]]}}))
        shutil.copy2(ROOT/'TRADING_PLAN.md',root/'TRADING_PLAN.md')
        db=root/'paper/intraday_500k.sqlite3';P.initialise(db,now=datetime.now(timezone.utc))
        sample=synthetic_closed_trade()
        base=datetime(2020,1,1,tzinfo=timezone.utc)
        def rows():
            for number in range(args.trades):
                entry=(base+timedelta(minutes=5*number)).isoformat();body={**sample,'entry':entry,'exit':entry,'net_pnl_rs':1.}
                yield entry,json.dumps(body,separators=(',',':'))
        started=time.perf_counter()
        with sqlite3.connect(db) as conn:
            conn.executemany('INSERT INTO trades(entry,body) VALUES(?,?)',rows())
            conn.executemany('INSERT INTO events(timestamp,body) VALUES(?,?)',
                             (((base+timedelta(minutes=5*i)).isoformat(),json.dumps({'timestamp':(base+timedelta(minutes=5*i)).isoformat(),'action':'skip','equity_rs':500000})) for i in range(args.trades)))
        seed_seconds=time.perf_counter()-started
        started=time.perf_counter();L.migrate(db);migration_seconds=time.perf_counter()-started
        # Exercise original single-writer transaction shape with aggregate triggers.
        transactions=500;started=time.perf_counter()
        with sqlite3.connect(db) as conn:
            for number in range(transactions):
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    entry=(base+timedelta(minutes=5*(args.trades+number))).isoformat()
                    body={**sample,'entry':entry,'exit':entry,'net_pnl_rs':1.}
                    conn.execute('INSERT INTO trades(entry,body) VALUES(?,?)',(entry,json.dumps(body)))
                    state=json.loads(conn.execute('SELECT body FROM account WHERE id=1').fetchone()[0])
                    state['equity']=500000+args.trades+number+1
                    conn.execute('UPDATE account SET body=? WHERE id=1',(json.dumps(state),))
        transaction_seconds=time.perf_counter()-started
        snapshot=L.snapshot(db);assert snapshot['closed_trades']==args.trades+transactions
        assert len(snapshot['trades'])==min(200,args.trades+transactions)
        assert len(snapshot['decisions'])==min(1000,args.trades)
        backup=backup_database(db,root/'restore.sqlite3');assert L.snapshot(root/'restore.sqlite3')==snapshot
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'LEAGUE_BENCH_ROOT':str(root),'PYTHONPATH':str(ROOT),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MPLCONFIGDIR':str(root/'mpl')}
        log=(root/'gunicorn.log').open('w+')
        process=subprocess.Popen([sys.executable,'-m','gunicorn','--workers','1','--threads','4','--bind',f'127.0.0.1:{port}','--timeout','60','tools.capacity_fixture:create_app()'],cwd=ROOT,env=env,stdout=log,stderr=log)
        origin=f'http://127.0.0.1:{port}'
        try:
            for _ in range(150):
                if process.poll() is not None:
                    log.seek(0);raise RuntimeError(log.read()[-4000:])
                try:
                    with urllib.request.urlopen(origin+'/healthz',timeout=1) as response:assert response.status==200
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Capacity fixture failed to start')
            def worker(client):
                results=[]
                for number in range(args.requests):
                    path='/api/v1/history/trades?limit=50' if number%5==0 else '/api/dashboard'
                    request=urllib.request.Request(origin+path,headers={'Authorization':f'Bearer client{client}.{TEST_KEY}',
                                                                         'X-League-Client-IP':f'192.0.2.{client+1}'})
                    start=time.perf_counter()
                    with urllib.request.urlopen(request,timeout=15) as response:
                        body=response.read();code=response.status
                    results.append((time.perf_counter()-start,code,len(body)))
                return results
            started=time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.clients) as pool:
                observations=[row for batch in pool.map(worker,range(args.clients)) for row in batch]
            elapsed=time.perf_counter()-started
            burst_codes=[]
            for _ in range(200):
                request=urllib.request.Request(origin+'/api/health',headers={'Authorization':f'Bearer client31.{TEST_KEY}',
                                                                            'X-League-Client-IP':'192.0.2.250'})
                try:
                    with urllib.request.urlopen(request,timeout=15) as response:response.read();burst_codes.append(response.status)
                except urllib.error.HTTPError as error:
                    burst_codes.append(error.code);error.close()
            assert 429 in burst_codes and all(code in (200,429) for code in burst_codes)
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close()
        latencies=sorted(row[0]*1000 for row in observations)
        result={'test_kind':'synthetic local HTTP and storage capacity; not strategy or live-trading validation',
                'at':datetime.now(timezone.utc).isoformat(),'hardware':os.uname().machine,'python':sys.version.split()[0],
                'deployed_server_tested':False,'tls_or_wan_tested':False,'live_account_modified':False,
                'stored_closed_trade_records':snapshot['closed_trades'],'stored_event_records':args.trades,
                'synthetic_seed_seconds':round(seed_seconds,3),'additive_migration_seconds':round(migration_seconds,3),
                'single_writer_transactions':transactions,'transaction_seconds':round(transaction_seconds,3),
                'transactions_per_second':round(transactions/transaction_seconds,1),
                'backup_restore_verified':True,'restored_database_bytes':backup['bytes'],
                'workers':1,'threads':4,'concurrent_clients':args.clients,'http_requests':len(observations),
                'http_errors':sum(row[1]!=200 for row in observations),'elapsed_seconds':round(elapsed,3),
                'separate_overload_burst':{'requests':len(burst_codes),'accepted':burst_codes.count(200),'rate_limited':burst_codes.count(429)},
                'client_addresses':'16 simulated proxy addresses in an isolated trusted-proxy fixture',
                'http_requests_per_second':round(len(observations)/elapsed,1),
                'latency_ms':{'p50':round(latencies[int(len(latencies)*.50)],2),'p95':round(latencies[min(len(latencies)-1,int(len(latencies)*.95))],2),'max':round(max(latencies),2)},
                'response_bytes_total':sum(row[2] for row in observations),'dashboard_trade_window':len(snapshot['trades']),
                'dashboard_event_window':len(snapshot['decisions']),
                'risk_policy_changed':False,'simultaneous_positions_supported':1,'daily_entry_limit_unchanged':3}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
