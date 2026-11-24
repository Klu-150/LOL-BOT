from datetime import date
import hashlib
import json

import pandas as pd
import pytest

import dashboard_data as D
from paper_trade import initialise


def market():
    return pd.DataFrame(dict(Open=[25000., 25010., 25020.], High=[25100.] * 3,
                             Low=[24900.] * 3, Close=[25000., 25010., 25020.],
                             VIX=[15.] * 3, vix_observed=[True] * 3),
                        index=pd.DatetimeIndex(['2026-11-11', '2026-11-12', '2026-11-13'], name='Date'))


def write_report(root, folder='results'):
    path = root / folder
    path.mkdir(parents=True)
    (path / 'results.json').write_text(json.dumps(dict(summary=[dict(strategy='example', total_rs=-10)],
                                                         equity={'example': [['2026-11-11', -10]]})))
    return path


def test_snapshot_discovers_algorithms_and_keeps_primary_first(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'load_market', market)
    write_report(tmp_path)
    write_report(tmp_path, 'results/algorithms/another')
    snapshot = D.build_snapshot(tmp_path)
    assert [r['id'] for r in snapshot['reports']] == ['results', 'results/algorithms/another']
    assert snapshot['market_as_of'] == '2026-11-13'
    assert len(snapshot['market']) == 3
    assert snapshot['paper']['available'] is False
    assert snapshot['market'][0]['ivr'] is None
    json.dumps(snapshot, allow_nan=False)


def test_invalid_additional_report_does_not_hide_valid_results(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'load_market', market)
    write_report(tmp_path)
    bad = tmp_path / 'results' / 'broken'
    bad.mkdir()
    (bad / 'results.json').write_text('{broken')
    snapshot = D.build_snapshot(tmp_path)
    assert len(snapshot['reports']) == 1
    assert len(snapshot['warnings']) == 1
    with pytest.raises(ValueError, match='No valid'):
        D.build_snapshot(tmp_path / 'absent')


def test_snapshot_reads_ledger_without_changes_or_policy_exposure(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'load_market', market)
    write_report(tmp_path)
    ledger = tmp_path / 'paper' / 'account.sqlite3'
    initialise(ledger, 20000, market(), as_of=date(2026,11,14), cutoff=date(2026,11,14))
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    snapshot = D.build_snapshot(tmp_path)
    assert snapshot['paper']['available'] is True
    assert snapshot['paper']['realised_equity_rs'] == 20000
    assert snapshot['paper']['open_trades'] == 0
    assert snapshot['paper']['closed_trades'] == 0
    assert 'policy' not in snapshot['paper']
    assert 'source_hashes' not in json.dumps(snapshot)
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before


def test_corrupt_ledger_is_reported_without_breaking_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'load_market', market)
    write_report(tmp_path)
    (tmp_path / 'paper').mkdir()
    (tmp_path / 'paper' / 'account.sqlite3').write_text('not a database')
    result = D.build_snapshot(tmp_path)
    assert not result['paper']['available']
    assert 'Paper account unavailable' in result['warnings'][0]


def test_daily_and_intraday_market_columns_remain_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'load_market', market)
    write_report(tmp_path)
    frame=market().iloc[:3].copy()
    frame.index=pd.date_range('2026-11-13 09:20',periods=3,freq='5min',tz='Asia/Kolkata',name='timestamp')
    (tmp_path/'data').mkdir()
    frame.to_csv(tmp_path/'data'/'intraday_nifty.csv')
    result=D.build_snapshot(tmp_path)
    assert result['intraday']['available']
    assert len(result['intraday']['bars'])==3
    assert 'close' in result['market'][0] and 'timestamp' not in result['market'][0]


def test_cloud_recovery_keeps_account_visible_without_optional_research_reports(tmp_path,monkeypatch):
    monkeypatch.setattr(D,'load_market',market)
    ledger=tmp_path/'paper'/'account.sqlite3'
    initialise(ledger,20000,market(),as_of=date(2026,11,14),cutoff=date(2026,11,14))
    snapshot=D.build_snapshot(tmp_path,allow_empty_reports=True)
    assert snapshot['paper']['available'] and snapshot['paper']['realised_equity_rs']==20000
    report=snapshot['reports'][0]
    assert report['research_available'] is False and report['summary'][0]['total_rs'] is None
    assert report['equity']['INTRADAY_BOT']==[]
    assert any('No research report' in warning for warning in snapshot['warnings'])
