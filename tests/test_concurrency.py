from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading

import pandas as pd

import intraday_paper as P
import ledger_store as L
from operations import backup_database
from tests.test_intraday import bar
from tests.test_reliability import seed_ledger


def test_concurrent_replayed_bars_cannot_duplicate_entries_or_exits(tmp_path):
    db=tmp_path/'account.sqlite3'
    initial_ts,initial=bar('2026-11-16 09:55')
    bars=pd.DataFrame([initial],index=[initial_ts]);P.initialise(db,bars=bars,now=initial_ts);L.migrate(db)
    ts,row=bar();bars=pd.concat([bars,pd.DataFrame([row],index=[ts])])
    def process(_):return P.process(db,bars,now=ts,prepared=bars)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(process,range(16)))
    state=P.snapshot(db)
    assert state['open_trades']==1 and state['closed_trades']==0
    assert len([e for e in state['decisions'] if e['action']=='open'])==1
    ts,row=bar('2026-11-16 15:15');bars=pd.concat([bars,pd.DataFrame([row],index=[ts])])
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(process,range(16)))
    state=P.snapshot(db)
    assert state['open_trades']==0 and state['closed_trades']==1
    assert len([e for e in state['decisions'] if e['action']=='close'])==1


def test_online_backup_stays_consistent_during_concurrent_writes(tmp_path):
    db=tmp_path/'account.sqlite3';seed_ledger(db,0);L.migrate(db)
    began=threading.Event()
    def write():
        with sqlite3.connect(db,timeout=10) as conn:
            for number in range(150):
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    state=json.loads(conn.execute('SELECT body FROM account WHERE id=1').fetchone()[0])
                    state['test_sequence']=number+1
                    conn.execute('INSERT INTO trades(entry,body) VALUES(?,?)',(str(number),'{"net_pnl_rs":1}'))
                    conn.execute('UPDATE account SET body=? WHERE id=1',(json.dumps(state),))
                began.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(write);assert began.wait(5)
        for number in range(5):
            target=tmp_path/f'backup-{number}.sqlite3';backup_database(db,target)
            with sqlite3.connect(target) as conn:
                state=json.loads(conn.execute('SELECT body FROM account WHERE id=1').fetchone()[0])
                assert conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]==state['test_sequence']
                assert conn.execute('SELECT trades FROM ledger_totals').fetchone()[0]==state['test_sequence']
        future.result(timeout=10)
