"""Synthetic, read-only Gunicorn app. Never starts a trading worker."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import cloud_server as C
from dashboard_data import build_snapshot

TEST_KEY='capacity-fixture-only-not-a-real-access-key'


def create_app():
    root=Path(os.environ['LEAGUE_BENCH_ROOT']).resolve()
    if not root.name.startswith('league-capacity-') or not (root/'BENCHMARK_ONLY').is_file():
        raise ValueError('A separate marked capacity fixture is required')
    C.build_snapshot=lambda:build_snapshot(root)
    users={f'client{i}':{'sha256':hashlib.sha256(TEST_KEY.encode()).hexdigest(),'role':'viewer'} for i in range(32)}
    status={'enabled':False,'state':'market_closed','checked_at':datetime.now(timezone.utc).isoformat(),'mode':'synthetic_capacity_fixture'}
    runtime=SimpleNamespace(trader=SimpleNamespace(db=root/'paper/intraday_500k.sqlite3',status=status),jobs={})
    return C.create_app(C.Settings(users,{'https://capacity.example'},trust_proxy=True),runtime,root/'paper/control.json')
