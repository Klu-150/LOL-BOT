import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import config as C
import intraday_paper as P
import strategy_workshop as S

NODE=shutil.which('node') or '/Applications/Codex.app/Contents/Resources/cua_node/bin/node'
ROOT=Path(__file__).resolve().parents[1]


def definition(kind='adaptive'):
    rules=[('rising','rich','bull_put_spread'),('rising','cheap','bull_call_spread'),
           ('falling','rich','bear_call_spread'),('falling','cheap','bear_put_spread'),('range','rich','iron_condor')]
    return {'schema_version':1,'name':'Test '+kind,'parameters':dict(S.DEFAULTS),
            'rules':[dict(market=m,volatility=v,strategy=s) for m,v,s in rules if kind!='range' or m=='range']}


@pytest.mark.parametrize('change',[{'schema_version':2},{'code':'arbitrary()'},{'rules':[]},
 {'parameters':{'risk_pct':50}},{'parameters':{'spread_width':101}},{'parameters':{'max_lots':True}},
 {'parameters':{'entry_start':'09:47'}},{'parameters':{'rsi_min':80,'rsi_max':20}}])
def test_definition_rejects_unsafe_or_invalid_settings(change):
    value=definition();value.update(change)
    with pytest.raises(ValueError):S.validate(value)


@pytest.mark.parametrize('kind',['adaptive','range','custom'])
def test_browser_model_matches_isolated_python_and_does_not_change_account(tmp_path,kind):
    value=definition('range' if kind=='range' else 'adaptive')
    if kind=='custom':value['parameters'].update(spread_width=150,risk_pct=1,rsi_min=30,rsi_max=70,entry_start='10:00',entry_end='13:30')
    policy=P.fingerprint();risk_before=C.RISK_PER_TRADE
    account_before=P.DEFAULT_DB.read_bytes() if P.DEFAULT_DB.exists() else None
    reference=S.backtest(value)
    script="""import fs from 'node:fs';import {backtestStrategy} from './dashboard/dist/strategy-engine.js';
const d=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(backtestStrategy(d,JSON.parse(fs.readFileSync('dashboard/dist/strategy-data.json','utf8')))));
"""
    browser=json.loads(subprocess.run([NODE,'--input-type=module','-e',script],cwd=ROOT,input=json.dumps(value),text=True,capture_output=True,check=True).stdout)
    assert len(browser['trades'])==len(reference['trades'])
    assert browser['equity_rs']==pytest.approx(reference['equity'],abs=.01)
    assert [(t['entry'],t['exit'],t['strategy']) for t in browser['trades']]==[(t['entry'],t['exit'],t['strategy']) for t in reference['trades']]
    assert C.RISK_PER_TRADE==risk_before and P.fingerprint()==policy
    if account_before is not None:assert P.DEFAULT_DB.read_bytes()==account_before
