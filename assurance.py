"""Bounded, allowlisted operational evidence; never a profitability certificate."""
from datetime import datetime,timezone
import json
from pathlib import Path


def evidence(directory,version,now=None):
    now=now or datetime.now(timezone.utc);directory=Path(directory)
    def read(name):
        path=directory/name
        try:
            if path.stat().st_size>65536:return {}
            value=json.loads(path.read_text())
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError,TypeError):return {}
    recovery=read('recovery-drill.json');soak=read('soak.summary.json')
    def fresh(stamp,limit):
        try:return -60 <= (now-datetime.fromisoformat(stamp)).total_seconds() <= limit
        except (ValueError,TypeError):return False
    drill_ok=(recovery.get('version')==version and recovery.get('boot_verified') is True
              and recovery.get('exact_account_preservation') is True and fresh(recovery.get('at'),8*86400))
    soak_fresh=fresh(soak.get('last_at'),900)
    alerts=[]
    failure=read('recovery-drill-error.json')
    if failure.get('state')=='failed' and str(failure.get('at',''))>str(recovery.get('at','')):
        drill_ok=False
    if (directory/'recovery-drill-required').exists() and not drill_ok:alerts.append('application_recovery_not_verified')
    if (directory/'soak-required').exists() and not soak_fresh:alerts.append('readiness_observer_stale')
    return {'alerts':alerts,'application_recovery':{k:recovery.get(k) for k in ('at','version','recovery_seconds','snapshot_at','scope')}|{'verified':drill_ok},
        'soak':{k:soak.get(k) for k in ('state','samples','successes','failures','observed_seconds','maximum_gap_seconds','first_at','last_at','target_days','scope')}|{'fresh':soak_fresh,'qualified':soak.get('qualified') is True and soak_fresh},
        'release_scope':'modelled_options_paper_trading',
        'independent_security_review':'not_verified','observed_options_execution':'not_connected',
        'real_money_ready':False}
