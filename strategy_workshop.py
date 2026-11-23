"""Research-only strategy definitions, public dataset export and isolated backtests.

This module never edits the live policy or opens a paper account. Configuration
changes and strategy routing occur only in a separate research subprocess.
"""
import json
import math
from pathlib import Path
import subprocess
import sys

import config as C
from data import ROOT

MARKETS=('rising','falling','range')
VOLATILITIES=('rich','cheap','mixed')
STRUCTURES=('bull_put_spread','bear_call_spread','bull_call_spread','bear_put_spread','iron_condor')
DEFAULTS={'adx_range':20,'min_iv_rank':30,'min_iv_rv_ratio':1.1,'max_cheap_iv_rv_ratio':1.,
          'spread_width':100,'risk_pct':2.,'max_lots':5,'rsi_min':0.,'rsi_max':100.,
          'entry_start':'09:45','entry_end':'14:30'}
BOUNDS={'adx_range':(10,40),'min_iv_rank':(0,100),'min_iv_rv_ratio':(.5,3),
        'max_cheap_iv_rv_ratio':(.1,2),'spread_width':(50,500),'risk_pct':(.1,2),
        'max_lots':(1,5),'rsi_min':(0,100),'rsi_max':(0,100)}
CONFIG_KEYS=['LOT_SIZE','STRIKE_STEP','RISK_FREE','DIV_YIELD','SKEW_SLOPE','SKEW_CURVE',
 'VIX_SHOCK','CREDIT_SHORT_DELTA','CONDOR_SHORT_DELTA','CREDIT_TAKE_PROFIT','CREDIT_STOP_MULT',
 'DEBIT_TAKE_PROFIT','DEBIT_STOP','BROKERAGE_PER_ORDER','STT_SELL_PREMIUM','EXCHANGE_TXN',
 'SEBI_FEE','GST','STAMP_BUY','SLIPPAGE_FIXED','SLIPPAGE_PCT','RISK_COST_BUFFER_RS',
 'MIN_CREDIT_WIDTH_RATIO','MIN_DEBIT_REWARD_RISK','MAX_ACCOUNT_DRAWDOWN','ADX_TREND',
 'INTRADAY_EXIT_TIME','INTRADAY_MAX_TRADES','INTRADAY_DAILY_LOSS_LIMIT','INTRADAY_COOLDOWN_MINUTES']


def validate(value):
    if not isinstance(value,dict) or set(value)-{'schema_version','name','description','parameters','rules'}:
        raise ValueError('Use a version 1 strategy definition, without executable code or extra fields')
    if type(value.get('schema_version')) is not int or value['schema_version']!=1:
        raise ValueError('Unsupported strategy schema version')
    name=value.get('name');description=value.get('description','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80 or not isinstance(description,str) or len(description)>600:
        raise ValueError('Name must contain 1–80 characters; description up to 600')
    supplied=value.get('parameters',{})
    if not isinstance(supplied,dict) or set(supplied)-set(DEFAULTS):raise ValueError('Unknown strategy parameters')
    params={**DEFAULTS,**supplied}
    for key,(low,high) in BOUNDS.items():
        number=params[key]
        if isinstance(number,bool) or not isinstance(number,(float,int)) or not math.isfinite(number) or not low<=number<=high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if params['max_lots']%1 or params['spread_width']%50:raise ValueError('Use whole lots and 50-point spread increments')
    if params['rsi_min']>params['rsi_max'] or params['max_cheap_iv_rv_ratio']>params['min_iv_rv_ratio']:
        raise ValueError('Minimum must not exceed maximum; cheap IV/RV must not exceed rich IV/RV')
    for key in ('entry_start','entry_end'):
        stamp=params[key]
        if not isinstance(stamp,str) or len(stamp)!=5 or stamp[2]!=':' or not stamp.replace(':','').isdigit():raise ValueError('Use HH:MM entry times')
        if not '09:45'<=stamp<='14:30' or int(stamp[3:])>=60 or int(stamp[3:])%5:raise ValueError('Entry times must be 5-minute boundaries from 09:45 to 14:30 IST')
    if params['entry_start']>params['entry_end']:raise ValueError('Entry start must precede entry end')
    rules=value.get('rules')
    if not isinstance(rules,list) or not 1<=len(rules)<=9:raise ValueError('Enable between one and nine routing rules')
    seen=set();normal=[]
    for rule in rules:
        if not isinstance(rule,dict) or set(rule)!={'market','volatility','strategy'}:raise ValueError('Invalid routing rule')
        if rule['market'] not in MARKETS or rule['volatility'] not in VOLATILITIES or rule['strategy'] not in STRUCTURES:raise ValueError('Unsupported market, volatility or option structure')
        key=(rule['market'],rule['volatility'])
        if key in seen:raise ValueError('A market/volatility pair may have only one rule')
        seen.add(key);normal.append(dict(rule))
    return {'schema_version':1,'name':name.strip(),'description':description,'parameters':params,'rules':normal}


def dataset():
    import intraday_feed as F
    import intraday_engine as E
    import pandas as pd
    observed=E.features(F.load())
    change=observed.Close.diff();gain=change.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-change.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    observed['rsi']=100-100/(1+gain/loss)
    observed.loc[(gain==0)&(loss==0),'rsi']=50
    columns=['Open','High','Low','Close','VIX','ema_fast','ema_slow','adx','ivr','iv_rv_ratio','realized_vol',
             'bias_close','bias_age_minutes','trigger_fast','trigger_slow','event','shock','vix_observed','rsi','vix_source']
    def clean(value):
        if isinstance(value,float) and not math.isfinite(value):return None
        if hasattr(value,'item'):return clean(value.item())
        return value
    rows=[{'timestamp':ts.isoformat(),**{key:clean(row[key]) for key in columns}} for ts,row in observed.iterrows()]
    return {'schema_version':1,'source':'Observed Yahoo underlying bars with causal features; modelled option fills',
            'first_bar':rows[0]['timestamp'],'last_bar':rows[-1]['timestamp'],
            'expiry_switch':'2025-09-01','config':{key:getattr(C,key) for key in CONFIG_KEYS},'bars':rows}


def backtest(definition):
    definition=validate(definition)
    process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],input=json.dumps(definition),
                           text=True,capture_output=True,timeout=90,cwd=ROOT)
    if process.returncode:raise ValueError('Research backtest failed: '+process.stderr[-1000:])
    return json.loads(process.stdout)


def worker(definition):
    import pandas as pd
    import algorithm as A
    import intraday_engine as E
    from intraday_backtest import simulate
    from report import _json_clean
    definition=validate(definition);p=definition['parameters']
    mapping={'adx_range':'ADX_RANGE','min_iv_rank':'MIN_IV_RANK','min_iv_rv_ratio':'MIN_IV_RV_RATIO',
             'max_cheap_iv_rv_ratio':'MAX_CHEAP_IV_RV_RATIO','spread_width':'SPREAD_WIDTH',
             'max_lots':'MAX_LOTS','entry_start':'INTRADAY_ENTRY_START','entry_end':'INTRADAY_ENTRY_END'}
    for key,setting in mapping.items():setattr(C,setting,p[key])
    C.RISK_PER_TRADE=p['risk_pct']/100
    source=dataset();bars=pd.DataFrame(source['bars']);bars.index=pd.to_datetime(bars.pop('timestamp'),utc=True).dt.tz_convert(E.ZONE)
    rules={(r['market'],r['volatility']):r['strategy'] for r in definition['rules']}
    def decide(row):
        if row.get('bias_age_minutes',999)>20:return A.Decision(None,'missing_completed_15m_bias')
        selected=A.select(E.bias_row(row),bool(row.get('event',False)),'adaptive_regime')
        if selected.reason in ('insufficient_features','invalid_market_data','missing_same_day_vix','volatility_shock','scheduled_event'):
            return selected
        if (p['rsi_min']>0 or p['rsi_max']<100) and (pd.isna(row.rsi) or not p['rsi_min']<=row.rsi<=p['rsi_max']):
            return A.Decision(None,'rsi_filter',selected.condition,selected.volatility)
        name=rules.get((selected.condition,selected.volatility))
        return A.Decision(name,'custom_rule' if name else 'no_custom_rule',selected.condition,selected.volatility)
    E.decision=decide
    state,events,trades,incomplete=simulate(bars,500000)
    return _json_clean({'definition':definition,'equity':state['equity'],'trades':trades,'events':events,
                        'incomplete':incomplete,'mode':'isolated_research'})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--definition',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:result=worker(json.loads(sys.stdin.read()))
    elif args.dataset:
        args.dataset.write_text(json.dumps(dataset(),allow_nan=False,separators=(',',':')));print('Research dataset exported');sys.exit()
    elif args.definition:result=backtest(json.loads(args.definition.read_text()))
    else:parser.error('Choose --dataset or --definition')
    text=json.dumps(result,allow_nan=False,default=str)
    if args.output:args.output.write_text(text)
    else:print(text)
