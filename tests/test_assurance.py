from datetime import datetime,timedelta,timezone
import json
from assurance import evidence


def test_readiness_evidence_never_fabricates_missing_external_certification(tmp_path):
    value=evidence(tmp_path,'1.3.1')
    assert not value['application_recovery']['verified'] and not value['soak']['qualified']
    assert value['independent_security_review']=='not_verified' and not value['real_money_ready']
    (tmp_path/'recovery-drill-required').touch();(tmp_path/'soak-required').touch()
    assert len(evidence(tmp_path,'1.3.1')['alerts'])==2


def test_recovery_is_version_bound_and_stale_or_corrupt_evidence_fails_closed(tmp_path):
    stamp=datetime.now(timezone.utc)
    (tmp_path/'recovery-drill.json').write_text(json.dumps({'at':stamp.isoformat(),'version':'1.3.1','boot_verified':True,'exact_account_preservation':True,'secret':'NEVER-EXPOSE'}))
    value=evidence(tmp_path,'1.3.1')
    assert value['application_recovery']['verified'] and 'NEVER-EXPOSE' not in json.dumps(value)
    assert not evidence(tmp_path,'1.3.2')['application_recovery']['verified']
    assert not evidence(tmp_path,'1.3.1',stamp+timedelta(days=9))['application_recovery']['verified']
    (tmp_path/'recovery-drill.json').write_text('{corrupt')
    assert not evidence(tmp_path,'1.3.1')['application_recovery']['verified']


def test_failed_new_drill_immediately_invalidates_previous_pass(tmp_path):
    stamp=datetime.now(timezone.utc)
    (tmp_path/'recovery-drill-required').touch()
    (tmp_path/'recovery-drill.json').write_text(json.dumps({'at':stamp.isoformat(),'version':'1.3.1','boot_verified':True,'exact_account_preservation':True}))
    (tmp_path/'recovery-drill-error.json').write_text(json.dumps({'at':(stamp+timedelta(seconds=1)).isoformat(),'state':'failed'}))
    assert 'application_recovery_not_verified' in evidence(tmp_path,'1.3.1')['alerts']


def test_future_or_wrong_type_soak_evidence_cannot_pass(tmp_path):
    future=(datetime.now(timezone.utc)+timedelta(minutes=3)).isoformat()
    (tmp_path/'soak.summary.json').write_text(json.dumps({'last_at':future,'qualified':True}))
    assert not evidence(tmp_path,'1.3.1')['soak']['qualified']
