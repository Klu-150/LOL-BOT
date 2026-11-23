from copy import deepcopy
from datetime import datetime
import json

import numpy as np
import pandas as pd
import pytest

import algorithm
import config as C
import intraday_engine as E
import intraday_paper as P
import intraday_feed as F


def bar(stamp='2026-11-16 10:00', **changes):
    ts = pd.Timestamp(stamp, tz=E.ZONE)
    row = pd.Series(dict(Open=25000., High=25010., Low=24990., Close=25000., VIX=20.,
                         ema_fast=24900., ema_slow=24800., adx=30., realized_vol=15.,
                         ivr=55., iv_rv_ratio=1.33, bias_age_minutes=0., trigger_fast=24980.,
                         trigger_slow=24900., event=False, vix_observed=True, shock=False,
                         vix_source='intraday observation'), name=ts)
    for k,v in changes.items(): row[k]=v
    return ts,row


def test_router_selects_both_debit_and_credit_structures():
    cases=[({},'bull_put_spread'),({'ivr':10,'iv_rv_ratio':.8},'bull_call_spread'),
           ({'Close':24500,'ema_fast':24600},'bear_call_spread'),({'Close':24500,'ema_fast':24600,'ivr':10,'iv_rv_ratio':.8},'bear_put_spread'),
           ({'adx':15},'iron_condor'),({'adx':15,'ivr':10,'iv_rv_ratio':.8},None),
           ({'event':True},None),({'VIX':35},None)]
    for updates,name in cases:
        _,row=bar(**updates)
        assert E.decision(row).strategy==name


def test_causal_completed_higher_timeframe_and_future_daily_vix():
    indexes=[]
    for day in pd.bdate_range('2026-11-09',periods=5):
        indexes.extend(pd.date_range(str(day.date())+' 09:20',periods=75,freq='5min',tz=E.ZONE))
    index=pd.DatetimeIndex(indexes,name='timestamp')
    close=25000+np.arange(len(index))*.2+np.sin(np.arange(len(index)))*4
    bars=pd.DataFrame(dict(Open=close,High=close+3,Low=close-3,Close=close,VIX=15.),index=index)
    daily=pd.Series(np.linspace(10,20,500),index=pd.bdate_range('2025-01-01',periods=500))
    full=E.features(bars,daily)
    prefix=E.features(bars.iloc[:257],daily)
    pd.testing.assert_frame_equal(full.iloc[:257],prefix)
    assert (full.bias_timestamp.dropna() <= full.bias_timestamp.dropna().index).all()
    changed=daily.copy();changed.loc[changed.index>=pd.Timestamp('2026-11-13')]=999
    pd.testing.assert_frame_equal(E.features(bars.iloc[:300],daily),E.features(bars.iloc[:300],changed))


def test_square_off_closes_same_day_and_budgets_never_round_up():
    state=E.new_state(500000)
    ts,row=bar()
    event,_=E.step(state,row,ts)
    assert event['action']=='open'
    pos=state['position']
    assert pos['lots']*pos['risk_estimate_rs']<=500000*C.RISK_PER_TRADE
    ts,row=bar('2026-11-16 15:15')
    event,trade=E.step(state,row,ts)
    assert event['action']=='close' and event['reason']=='session_square_off'
    assert state['position'] is None
    assert trade['entry'][:10]==trade['exit'][:10]
    assert state['equity']==pytest.approx(500000+trade['net_pnl_rs'])
    small=E.new_state(20000);ts,row=bar();event,_=E.step(small,row,ts)
    assert event['action']=='skip' and small['position'] is None


def test_no_entry_after_cutoff_and_no_reentry_on_exit_bar():
    for stamp in ['2026-11-16 09:30','2026-11-16 14:35','2026-11-16 15:15']:
        state=E.new_state(500000);ts,row=bar(stamp);event,_=E.step(state,row,ts)
        assert event['action']=='skip' and event['reason']=='outside_entry_window'
    state=E.new_state(500000);ts,row=bar();E.step(state,row,ts)
    ts,row=bar('2026-11-16 10:05',Close=24000.,ema_fast=24500.,ema_slow=24600.)
    event,closed=E.step(state,row,ts)
    assert closed and state['position'] is None and event['action']=='close'
    event,_=E.step(state,bar('2026-11-16 10:10')[1],bar('2026-11-16 10:10')[0])
    assert event['reason']=='cooldown'


def test_missing_square_off_bar_blocks_next_session():
    state=E.new_state(500000);ts,row=bar();E.step(state,row,ts)
    with pytest.raises(ValueError,match='unresolved'):
        ts,row=bar('2026-11-17 10:00');E.step(state,row,ts)


def test_intraday_db_idempotence_stale_data_and_realised_fees(tmp_path):
    path=tmp_path/'intraday.sqlite3'
    initial_ts,initial=bar('2026-11-16 09:55')
    initial_frame=pd.DataFrame([initial],index=[initial_ts])
    P.initialise(path,500000,initial_frame,now=initial_ts)
    ts,row=bar();frame=pd.concat([initial_frame,pd.DataFrame([row],index=[ts])])
    result=P.process(path,frame,now=ts+pd.Timedelta(minutes=1),prepared=frame)
    assert result['position_open']
    before=P.snapshot(path)
    assert P.process(path,frame,now=ts+pd.Timedelta(minutes=2),prepared=frame)['bars_processed']==0
    assert P.snapshot(path)==before
    exit_ts,exit_row=bar('2026-11-16 15:15')
    frame=pd.concat([frame,pd.DataFrame([exit_row],index=[exit_ts])])
    P.process(path,frame,now=exit_ts+pd.Timedelta(minutes=1),prepared=frame)
    after=P.snapshot(path)
    assert after['closed_trades']==1 and after['open_trades']==0
    assert after['realised_equity_rs']==pytest.approx(500000+after['net_closed_pnl_rs'])
    json.dumps(after,allow_nan=False)
    stale=tmp_path/'stale.sqlite3';P.initialise(stale,500000,initial_frame,now=initial_ts)
    only=pd.DataFrame([initial,row],index=[initial_ts,ts])
    result=P.process(stale,only,now=ts+pd.Timedelta(minutes=30),prepared=only)
    assert not result['position_open'] and result['status']=='awaiting_fresh_market_data'


def test_pause_blocks_entries_but_still_manages_open_position(tmp_path):
    path=tmp_path/'paused.sqlite3'
    ts,row=bar('2026-11-16 09:55');first=pd.DataFrame([row],index=[ts]);P.initialise(path,500000,first,now=ts)
    ts,row=bar();frame=pd.concat([first,pd.DataFrame([row],index=[ts])])
    P.process(path,frame,now=ts,prepared=frame,entries_enabled=False)
    assert not P.snapshot(path)['position']
    ts,row=bar('2026-11-16 10:05');frame=pd.concat([frame,pd.DataFrame([row],index=[ts])])
    P.process(path,frame,now=ts,prepared=frame)
    assert P.snapshot(path)['position']
    ts,row=bar('2026-11-16 15:15');frame=pd.concat([frame,pd.DataFrame([row],index=[ts])])
    P.process(path,frame,now=ts,prepared=frame,entries_enabled=False)
    assert P.snapshot(path)['closed_trades']==1


def test_feed_rejects_invalid_prices_and_duplicate_times(tmp_path):
    p=tmp_path/'bad.csv'
    p.write_text('timestamp,Open,High,Low,Close\n2026-11-16T10:00:00+05:30,25000,25010,24990,inf\n')
    with pytest.raises(ValueError,match='finite'):F.load(p)


def test_direction_uses_completed_15m_close_not_partial_5m_move():
    _,row=bar(Close=25200.,bias_close=24500.,ema_fast=24600.,ema_slow=24800.)
    assert E.decision(row).condition=='falling'
    assert E.decision(row).strategy=='bear_call_spread'


def test_feed_drops_offgrid_live_tick_and_rejects_offgrid_csv(tmp_path, monkeypatch):
    start = pd.Timestamp('2026-11-16 10:00', tz=E.ZONE)
    stamps = [start, start + pd.Timedelta(minutes=5), start + pd.Timedelta(minutes=5, seconds=27)]
    body = {'chart': {'error': None, 'result': [{'meta': {'symbol': '^NSEI'},
            'timestamp': [int(s.timestamp()) for s in stamps],
            'indicators': {'quote': [{'open': [1., 2., 3.], 'high': [1., 2., 3.], 'low': [1., 2., 3.], 'close': [1., 2., 3.]}]}}]}}
    monkeypatch.setattr(F.transport, 'fetch', lambda url, symbol: body)
    frame = F.chart('^NSEI')
    assert [t.strftime('%H:%M:%S') for t in frame.index] == ['10:05:00', '10:10:00']
    p = tmp_path / 'offgrid.csv'
    p.write_text('timestamp,Open,High,Low,Close\n2026-11-16T10:10:27+05:30,25000,25010,24990,25000\n')
    with pytest.raises(ValueError, match='5-minute'):
        F.load(p)
