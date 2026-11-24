import json
import pytest
from tools.check_codeql import evaluate


def report(tmp_path,results=None,level='warning',score='7.5',successful=True):
    body={'version':'2.1.0','runs':[{'tool':{'driver':{'name':'CodeQL','rules':[
        {'id':'py/test-finding','defaultConfiguration':{'level':level},'properties':{'security-severity':score}}]}},
        'results':results or [],'invocations':[{'executionSuccessful':successful}]}]}
    (tmp_path/'python.sarif').write_text(json.dumps(body))


def test_clean_completed_scan_passes(tmp_path):
    report(tmp_path)
    assert evaluate(tmp_path)['blocking_findings']==0


def test_successful_scan_with_findings_blocks_even_if_result_level_is_omitted(tmp_path):
    report(tmp_path,[{'ruleId':'py/test-finding','locations':[{'physicalLocation':{
        'artifactLocation':{'uri':'cloud_server.py'},'region':{'startLine':12}}}]}])
    result=evaluate(tmp_path)
    assert result['blocking_findings']==1
    assert result['details'][0]['path']=='cloud_server.py'


def test_security_score_blocks_a_mislabelled_informational_result(tmp_path):
    report(tmp_path,[{'ruleId':'py/test-finding','level':'note'}])
    assert evaluate(tmp_path)['blocking_findings']==1


def test_genuine_low_score_note_is_reported_without_blocking(tmp_path):
    report(tmp_path,[{'ruleId':'py/test-finding','level':'note'}],score='1.0')
    assert evaluate(tmp_path)['findings']==1
    assert evaluate(tmp_path)['blocking_findings']==0


def test_absent_invalid_or_failed_scan_never_passes(tmp_path):
    with pytest.raises(ValueError,match='No CodeQL'):evaluate(tmp_path)
    (tmp_path/'python.sarif').write_text('{}')
    with pytest.raises(ValueError,match='Invalid'):evaluate(tmp_path)
    report(tmp_path,successful=False)
    with pytest.raises(ValueError,match='did not complete'):evaluate(tmp_path)
    report(tmp_path,score='NaN')
    report(tmp_path,[{'ruleId':'py/test-finding'}],score='NaN')
    with pytest.raises(ValueError,match='Invalid security severity'):evaluate(tmp_path)
