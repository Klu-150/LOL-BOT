"""Reviewed NSE F&O regular-session calendar for operational admission only.

Source: NSE/FAOP/71777, 12 December 2025. Reviewed 24 November 2026.
https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf
Amendment: NSE/FAOP/72262, 12 January 2026 (15 January closure).
This does not change the account's pinned option-pricing/expiry model.
Unreviewed years and special sessions never authorise automatic entries.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Kolkata')
REVIEWED_YEARS = {2026}
HOLIDAYS = {
    '2026-01-15': 'Maharashtra municipal election',
    '2026-01-26': 'Republic Day', '2026-03-03': 'Holi',
    '2026-03-26': 'Ram Navami', '2026-03-31': 'Mahavir Jayanti',
    '2026-04-03': 'Good Friday', '2026-04-14': 'Ambedkar Jayanti',
    '2026-05-01': 'Maharashtra Day', '2026-05-28': 'Bakri Id',
    '2026-06-26': 'Muharram', '2026-09-14': 'Ganesh Chaturthi',
    '2026-10-02': 'Gandhi Jayanti', '2026-10-20': 'Dussehra',
    '2026-11-10': 'Diwali Balipratipada', '2026-11-24': 'Guru Nanak Jayanti',
    '2026-12-25': 'Christmas',
}
SPECIAL_SESSIONS = {'2026-11-08': 'Muhurat session unsupported by this intraday policy'}


def regular_day(day):
    return (day.year in REVIEWED_YEARS and day.weekday() < 5
            and day.isoformat() not in HOLIDAYS and day.isoformat() not in SPECIAL_SESSIONS)


def session_status(now=None):
    now = now or datetime.now(ZONE)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Market calendar requires a timezone-aware timestamp')
    now = now.astimezone(ZONE)
    day, stamp = now.date(), now.strftime('%H:%M:%S')
    reviewed, regular = day.year in REVIEWED_YEARS, regular_day(day)
    reason = ('calendar_unverified' if not reviewed else
              'special_session_unsupported' if day.isoformat() in SPECIAL_SESSIONS else
              'holiday' if day.isoformat() in HOLIDAYS else
              'weekend' if day.weekday() >= 5 else
              'pre_open' if stamp < '09:15:00' else
              'post_close' if stamp >= '15:30:00' else 'regular_session')
    next_entry = None
    for offset in range(370):
        candidate = day + timedelta(days=offset)
        if candidate.year not in REVIEWED_YEARS:
            break
        if regular_day(candidate):
            start = datetime.combine(candidate, time(9, 45), ZONE)
            cutoff = datetime.combine(candidate, time(14, 30, 59, 999999), ZONE)
            if now <= cutoff:
                next_entry = max(now, start).isoformat()
                break
    return {'verified': reviewed, 'date': day.isoformat(), 'reason': reason,
            'holiday': HOLIDAYS.get(day.isoformat()),
            'feed_window': regular and '09:15:00' <= stamp <= '15:40:00',
            'entries_allowed': regular and '09:45' <= stamp[:5] <= '14:30',
            'next_entry_at_or_after': next_entry,
            'coverage_end': f'{day.year}-12-31' if reviewed else None,
            'source': 'NSE/FAOP/71777 + NSE/FAOP/72262; special sessions not enabled'}


def deployment_allowed(now=None):
    session = session_status(now)
    return session['verified'] and not session['feed_window']
