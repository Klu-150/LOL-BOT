from datetime import datetime,timedelta,timezone
import json
import pytest
from tools.soak_probe import summarize,record


def observations(days=7):
    end=datetime.now(timezone.utc)
    return [{'at':(end-timedelta(minutes=5*n)).isoformat(),'ready':True} for n in range(days*288,-1,-1)]


def test_qualification_needs_elapsed_time_continuous_coverage_and_no_failures():
    rows=observations()
    assert summarize(rows)['qualified']
    assert not summarize(rows[-100:])['qualified']
    assert not summarize(rows[::2])['qualified']
    failed=[dict(r) for r in rows];failed[100]['ready']=False
    assert not summarize(failed)['qualified']
    assert not summarize(rows,datetime.now(timezone.utc)+timedelta(hours=1))['qualified']
    with pytest.raises(ValueError):summarize(list(reversed(rows)))


def test_evidence_is_private_and_restart_preserves_observations(tmp_path):
    path=tmp_path/'soak.jsonl';rows=observations()[-2:]
    record(path,rows[0]);result=record(path,rows[1])
    assert result['samples']==2 and not result['qualified']
    assert path.stat().st_mode & 0o777==0o600
    assert json.loads(path.with_suffix('.summary.json').read_text())['samples']==2


def test_old_failure_does_not_erase_a_subsequent_complete_healthy_week():
    rows=observations(days=8)
    rows[0]['ready']=False
    assert summarize(rows)['qualified']
