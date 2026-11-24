"""Synthetic, read-only Gunicorn app. Never starts a trading worker."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import cloud_server as C
from dashboard_data import build_snapshot

TEST_KEY='capacity-fixture-only-not-a-real-access-key'


def synthetic_closed_trade():
    """Construct a hedged test trade; never read a real account as sample data."""
    import pandas as pd
    import intraday_engine as E
    row=pd.Series(dict(Open=25000.,High=25010.,Low=24990.,Close=25000.,VIX=20.,
        ema_fast=24900.,ema_slow=24800.,adx=15.,realized_vol=15.,ivr=55.,
        iv_rv_ratio=1.33,bias_age_minutes=0.,trigger_fast=24980.,trigger_slow=24900.,
        event=False,vix_observed=True,shock=False))
    state=E.new_state(500000)
    E.step(state,row,pd.Timestamp('2026-11-16T09:45:00',tz=E.ZONE))
    _,trade=E.step(state,row,pd.Timestamp('2026-11-16T15:15:00',tz=E.ZONE))
    if trade is None or state['position'] is not None:
        raise ValueError('Synthetic capacity fixture could not form a complete hedged trade')
    return trade


def create_app():
    root=Path(os.environ['LEAGUE_BENCH_ROOT']).resolve()
    if not root.name.startswith('league-capacity-') or not (root/'BENCHMARK_ONLY').is_file():
        raise ValueError('A separate marked capacity fixture is required')
    C.build_snapshot=lambda:build_snapshot(root)
    users={f'client{i}':{'sha256':hashlib.sha256(TEST_KEY.encode()).hexdigest(),'role':'viewer'} for i in range(32)}
    status={'enabled':False,'state':'market_closed','checked_at':datetime.now(timezone.utc).isoformat(),'mode':'synthetic_capacity_fixture'}
    runtime=SimpleNamespace(trader=SimpleNamespace(db=root/'paper/intraday_500k.sqlite3',status=status),jobs={})
    return C.create_app(C.Settings(users,{'https://capacity.example'},trust_proxy=True),runtime,root/'paper/control.json')
