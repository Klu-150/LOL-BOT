"""Load Nifty + India VIX, build the weekly expiry calendar, load event dates."""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import config as C

ROOT = Path(__file__).resolve().parent


def load_market() -> pd.DataFrame:
    n = pd.read_csv(ROOT / C.NIFTY_CSV, parse_dates=["Date"])
    v = pd.read_csv(ROOT / C.VIX_CSV, parse_dates=["Date"])
    n = n[["Date", "Open", "High", "Low", "Close"]].dropna()
    v = v[["Date", "Close"]].rename(columns={"Close": "VIX"}).dropna()
    df = n.merge(v, on="Date", how="left").sort_values("Date")
    df["vix_observed"] = df["VIX"].notna()
    df["VIX"] = df["VIX"].ffill()
    df = df.dropna(subset=["VIX"]).drop_duplicates("Date").set_index("Date")
    return df


def weekly_expiries(trading_days: pd.DatetimeIndex) -> list:
    """
    Nifty weekly expiry dates that fall inside the data.
    Thursday until 31 Aug 2025, Tuesday from 1 Sep 2025.
    A holiday moves expiry to the previous trading day.
    """
    days = [d.date() for d in trading_days]
    day_set = set(days)
    first, last = days[0], days[-1]
    nominal = []
    d = first
    while d <= last:
        wd = 3 if d < C.EXPIRY_SWITCH_DATE else 1  # Thu=3, Tue=1
        if d.weekday() == wd:
            nominal.append(d)
        d += timedelta(days=1)

    expiries = []
    for nd in nominal:
        x = nd
        while x not in day_set and x > first:
            x -= timedelta(days=1)
        if x in day_set and (not expiries or x > expiries[-1]):
            expiries.append(x)
    return expiries


def load_events() -> list:
    p = ROOT / C.EVENTS_CSV
    if not p.exists():
        return []
    ev = pd.read_csv(p, parse_dates=["date"], comment="#")
    return sorted(d.date() for d in ev["date"])


def first_event_in(events, start: date, end: date):
    """First event with start < event <= end, else None."""
    for e in events:
        if start < e <= end:
            return e
    return None
