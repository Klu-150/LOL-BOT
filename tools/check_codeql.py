"""Fail CI on actionable CodeQL SARIF findings, not just scanner failures."""
import argparse
import json
import math
from pathlib import Path


def evaluate(directory):
    files=sorted(Path(directory).glob('*.sarif'))
    if not files:
        raise ValueError('No CodeQL SARIF results were produced')
    findings=[]
    for path in files:
        if path.stat().st_size>64*1024**2:
            raise ValueError('CodeQL result exceeds the review size bound')
        report=json.loads(path.read_text())
        if report.get('version')!='2.1.0' or not isinstance(report.get('runs'),list) or not report['runs']:
            raise ValueError('Invalid CodeQL SARIF report')
        for run in report['runs']:
            driver=run.get('tool',{}).get('driver',{})
            if driver.get('name')!='CodeQL' or not isinstance(run.get('results'),list):
                raise ValueError('Expected CodeQL results')
            if any(inv.get('executionSuccessful') is False for inv in run.get('invocations',[])):
                raise ValueError('CodeQL did not complete successfully')
            rules={rule.get('id'):rule for rule in driver.get('rules',[])}
            for result in run['results']:
                rule=rules.get(result.get('ruleId'),{})
                level=result.get('level',rule.get('defaultConfiguration',{}).get('level','warning'))
                try:score=float(rule.get('properties',{}).get('security-severity',0))
                except (TypeError,ValueError):raise ValueError('Invalid security severity') from None
                if not math.isfinite(score) or not 0<=score<=10:
                    raise ValueError('Invalid security severity')
                location=(result.get('locations') or [{}])[0].get('physicalLocation',{})
                findings.append({'rule':result.get('ruleId','unknown'),'level':level,'security_severity':score,
                    'path':location.get('artifactLocation',{}).get('uri'),
                    'line':location.get('region',{}).get('startLine'),
                    'blocking':level in ('warning','error') or score>=4})
    return {'sarif_files':len(files),'findings':len(findings),
            'blocking_findings':sum(item['blocking'] for item in findings),'details':findings[:100]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    try:
        result=evaluate(args.directory)
    except (ValueError,OSError) as error:
        print(json.dumps({'error':str(error)}));raise SystemExit(1)
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(result['blocking_findings']))
