"""Durable automatic intraday paper account. No broker connectivity."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

import config as C
from data import ROOT
import intraday_engine as E
import intraday_feed as F

DEFAULT_DB = ROOT / C.INTRADAY_DB


def dumps(value):
    return json.dumps(value, allow_nan=False, default=lambda v: v.item() if hasattr(v, "item") else str(v))


def fingerprint():
    files = ["intraday_engine.py", "intraday_paper.py", "algorithm.py", "risk.py", "pricing.py", "costs.py", "strategies.py", "regime.py", "config.py", C.EVENTS_CSV]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


def initialise(path=DEFAULT_DB, capital=C.PAPER_CAPITAL, bars=None, now=None):
    path = Path(path)
    if path.exists():
        raise ValueError("Intraday account already exists; it will not be overwritten")
    now = pd.Timestamp(now or pd.Timestamp.now(tz=E.ZONE))
    if now.tzinfo is None:
        raise ValueError("Use a timezone-aware current time")
    now = now.tz_convert(E.ZONE)
    state = E.new_state(capital, now.isoformat())
    if bars is not None and len(bars.loc[bars.index <= now]):
        state["last_timestamp"] = bars.loc[bars.index <= now].index[-1].isoformat()
    state["fingerprint"] = fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE account(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
        CREATE TABLE events(timestamp TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE trades(id INTEGER PRIMARY KEY, entry TEXT NOT NULL UNIQUE, body TEXT NOT NULL);
        ''')
        conn.execute("INSERT INTO account VALUES(1,?)", (dumps(state),))
    return snapshot(path)


def snapshot(path=DEFAULT_DB):
    path = Path(path)
    if not path.is_file():
        return {"available": False, "mode": "intraday_modelled_paper", "trades": [], "decisions": [], "notes": []}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("BEGIN")
        state = json.loads(conn.execute("SELECT body FROM account WHERE id=1").fetchone()[0])
        trades = [dict(json.loads(body), id=ident) for ident, body in conn.execute("SELECT id,body FROM trades ORDER BY id DESC")]
        events = [json.loads(row[0]) for row in conn.execute("SELECT body FROM events ORDER BY timestamp")]
    position = state["position"]
    unrealised = position["mark"]["gross_rs"] - position["mark"]["exit_charges_rs"] if position else 0
    public_state = {k: v for k, v in state.items() if k != "fingerprint"}
    return {"available": True, **public_state, "initial_capital_rs": state["initial_capital"],
            "realised_equity_rs": state["equity"], "marked_equity_rs": state["equity"] + unrealised,
            "closed_trades": len(trades), "open_trades": int(position is not None),
            "net_closed_pnl_rs": sum(t["net_pnl_rs"] for t in trades), "trades": trades,
            "decisions": events, "notes": [], "last_processed": state["last_timestamp"],
            "start_date": state["started_at"], "orders_submitted": False}


def process(path=DEFAULT_DB, bars=None, now=None, prepared=None, entries_enabled=True):
    now = pd.Timestamp(now or pd.Timestamp.now(tz=E.ZONE))
    if now.tzinfo is None:
        raise ValueError("Use timezone-aware current time")
    now = now.tz_convert(E.ZONE)
    bars = F.load() if bars is None else bars
    # Feed timestamps mean end-of-bar; future/incomplete observations are excluded.
    bars = bars.loc[bars.index <= now]
    if bars.empty:
        return {"bars_processed": 0, "status": "awaiting_completed_bars"}
    prepared = E.features(bars) if prepared is None else prepared.loc[bars.index]
    path = Path(path)
    if not path.exists():
        initialise(path, bars=bars, now=now)
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            state = json.loads(conn.execute("SELECT body FROM account WHERE id=1").fetchone()[0])
            if state["fingerprint"] != fingerprint():
                raise ValueError("Intraday policy/code changed; restore its pinned version or start a separate account")
            last = pd.Timestamp(state["last_timestamp"]) if state["last_timestamp"] else now
            pending = prepared.loc[(prepared.index > last) & (prepared.index >= pd.Timestamp(state["started_at"]))]
            count = 0
            latest = prepared.index[-1]
            latest_age = (now - latest).total_seconds() / 60
            for ts, row in pending.iterrows():
                # Manage old positions during catch-up. Do not fabricate old entries.
                allow = entries_enabled and ts == latest and latest_age <= C.INTRADAY_MAX_BAR_AGE_MINUTES and ts.date() == now.date()
                event, closed = E.step(state, row, ts, allow_entry=allow)
                conn.execute("INSERT INTO events VALUES(?,?)", (ts.isoformat(), dumps(event)))
                if closed:
                    conn.execute("INSERT INTO trades(entry,body) VALUES(?,?)", (closed["entry"], dumps(closed)))
                count += 1
            conn.execute("UPDATE account SET body=? WHERE id=1", (dumps(state),))
        status = "watching" if latest_age <= C.INTRADAY_MAX_BAR_AGE_MINUTES and latest.date() == now.date() else "awaiting_fresh_market_data"
        if state["position"] and now.strftime("%H:%M") >= C.INTRADAY_EXIT_TIME and latest.strftime("%H:%M") < C.INTRADAY_EXIT_TIME:
            status = "square_off_waiting_for_data"
        row = prepared.iloc[-1]
        pick = E.decision(row)
        return {"bars_processed": count, "status": status, "latest_bar": latest.isoformat(),
                "bar_age_minutes": round(latest_age, 1), "candidate": pick.strategy,
                "market_condition": pick.condition, "volatility_condition": pick.volatility,
                "reason": pick.reason, "vix_source": str(row.get("vix_source", "unavailable")),
                "position_open": state["position"] is not None, "equity_rs": state["equity"],
                "orders_submitted": False}
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "process", "review"])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--capital", type=float, default=C.PAPER_CAPITAL)
    args = parser.parse_args()
    if args.command == "init":
        result = initialise(args.db, args.capital, F.load())
    elif args.command == "process":
        result = process(args.db)
    else:
        result = snapshot(args.db)
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
