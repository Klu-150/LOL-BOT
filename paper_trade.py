"""Persistent modelled paper trading. Run once after updating completed daily bars."""
import argparse
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd

import algorithm
import config as C
from data import ROOT, first_event_in, load_events, load_market
from execution import evaluate_position
from live_signal import _next_expiry
import regime
import risk
from strategies import Leg, KIND

DEFAULT_DB = ROOT / C.PAPER_DB


def _dump(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def policy_snapshot():
    def normalise(value):
        if isinstance(value, dict):
            return {str(k): normalise(v) for k, v in value.items()}
        if isinstance(value, date):
            return value.isoformat()
        return value
    settings = {k: normalise(v) for k, v in vars(C).items() if k.isupper()}
    sources = ["algorithm.py", "execution.py", "regime.py", "risk.py", "pricing.py", "costs.py", "strategies.py"]
    settings["source_hashes"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    settings["events_hash"] = hashlib.sha256((ROOT / C.EVENTS_CSV).read_bytes()).hexdigest()
    return settings


def completed_through(now=None):
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    now = now.astimezone(ZoneInfo("Asia/Kolkata"))
    return now.date() if now.time() >= time(15, 30) else now.date() - timedelta(days=1)


def _market_through(mkt, cutoff):
    mkt = mkt.loc[mkt.index.date <= cutoff].copy().sort_index()
    if mkt.empty or mkt.index.has_duplicates:
        raise ValueError("Need nonempty daily market data with unique dates")
    return mkt


def _connect(path):
    if not Path(path).is_file():
        raise ValueError("Paper account does not exist; run init first")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _state(conn):
    return json.loads(conn.execute("SELECT value FROM meta WHERE key='account'").fetchone()[0])


def _save(conn, state):
    conn.execute("UPDATE meta SET value=? WHERE key='account'", (_dump(state),))


def initialise(path, capital, mkt, as_of=None, cutoff=None, profile=None):
    profile = profile or C.ALGORITHM
    if profile not in algorithm.PAPER_PROFILES:
        raise ValueError("Paper mode supports adaptive_regime or credit_regime")
    as_of = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    cutoff = cutoff or completed_through()
    mkt = _market_through(mkt, cutoff)
    latest = mkt.index[-1].date()
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Capital must be finite and positive")
    if not 0 <= (as_of - latest).days <= 3:
        raise ValueError("Refresh market data before starting a forward paper account")
    path = Path(path)
    if path.exists():
        raise ValueError("Account already exists; choose another --db to start a separate experiment")
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(mode="forward_modelled_paper", algorithm=profile, engine_version=2,
                 bot_name=C.BOT_NAME,
                 start_date=str(as_of), initial_capital=capital,
                 realised_equity=capital, peak_equity=capital, halted=False,
                 last_processed=str(latest), policy=policy_snapshot())
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE trades(id INTEGER PRIMARY KEY, entry_date TEXT NOT NULL UNIQUE,
                strategy TEXT NOT NULL, lots INTEGER NOT NULL, expiry TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open','closed')), entry_json TEXT NOT NULL,
                exit_date TEXT, exit_json TEXT, mark_json TEXT);
            CREATE UNIQUE INDEX one_open_position ON trades(status) WHERE status='open';
            CREATE TABLE decisions(day TEXT PRIMARY KEY, action TEXT NOT NULL, reason TEXT NOT NULL,
                equity REAL NOT NULL, unrealised REAL NOT NULL, details_json TEXT NOT NULL);
            CREATE TABLE notes(id INTEGER PRIMARY KEY, trade_id INTEGER NOT NULL REFERENCES trades(id),
                recorded_at TEXT NOT NULL, emotion TEXT, note TEXT NOT NULL);
        """)
        conn.execute("INSERT INTO meta VALUES('account', ?)", (_dump(state),))
    return state


def _mark(trade, row, day, market_row=None, profile=None):
    entry = json.loads(trade["entry_json"])
    if not row.get("vix_observed", True) or not all(math.isfinite(float(row[k])) and row[k] > 0 for k in ("Close", "VIX")):
        raise ValueError(f"Cannot value open position on {day}: missing/invalid spot or same-day VIX")
    mark = evaluate_position(trade["strategy"], [Leg(**leg) for leg in entry["legs"]], entry["fills"],
                             entry["entry_net_pts"], float(row["Close"]), float(row["VIX"]) / 100,
                             day, {"front": date.fromisoformat(trade["expiry"])},
                             market_row=market_row, profile=profile)
    mark["gross_rs"] = mark["pnl_pts"] * C.LOT_SIZE * trade["lots"]
    mark["exit_charges_total_rs"] = mark["exit_charges_rs"] * trade["lots"]
    mark["net_pnl_rs"] = mark["gross_rs"] - mark["exit_charges_total_rs"] - entry["entry_charges_rs"] * trade["lots"]
    return mark


def process(path, mkt, as_of=None, cutoff=None, features=None):
    """Catch up existing positions, but only open on the newest completed fresh bar.

    A transaction prevents duplicate fills, partial updates and concurrent entries.
    Historical missed entry days are logged, never opened retrospectively.
    """
    as_of = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    cutoff = cutoff or completed_through()
    mkt = _market_through(mkt, min(cutoff, as_of))
    features = regime.classify(regime.add_features(mkt)) if features is None else features.loc[mkt.index]
    latest = mkt.index[-1].date()
    events = load_events()
    conn = _connect(path)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            state = _state(conn)
            if state["policy"] != policy_snapshot():
                raise ValueError("Policy, costs, code or events changed; use a new --db so experiments stay comparable")
            if latest < date.fromisoformat(state["last_processed"]):
                raise ValueError("Market data ends before the account's last processed bar")
            pending = mkt.loc[mkt.index.date > date.fromisoformat(state["last_processed"])]
            count = 0
            for ts, row in pending.iterrows():
                day = ts.date()
                if day < date.fromisoformat(state["start_date"]):
                    continue
                action, reason, unrealised, details = "skip", "waiting_for_weekly_entry", 0.0, {}
                closed_today = False
                opened = conn.execute("SELECT * FROM trades WHERE status='open'").fetchone()
                if opened:
                    mark = _mark(opened, row, day, features.loc[ts], state["algorithm"])
                    details["position_mark"] = mark
                    conn.execute("UPDATE trades SET mark_json=? WHERE id=?", (_dump(mark), opened["id"]))
                    if mark["exit_reason"]:
                        state["realised_equity"] += mark["gross_rs"] - mark["exit_charges_total_rs"]
                        conn.execute("UPDATE trades SET status='closed', exit_date=?, exit_json=? WHERE id=?",
                                     (str(day), _dump(mark), opened["id"]))
                        action, reason, closed_today = "close", mark["exit_reason"], True
                    else:
                        unrealised = mark["gross_rs"] - mark["exit_charges_total_rs"]
                        action, reason = "hold", "position_open"
                state["peak_equity"] = max(state["peak_equity"], state["realised_equity"])
                state["halted"] = state["halted"] or state["realised_equity"] <= state["peak_equity"] * (1 - C.MAX_ACCOUNT_DRAWDOWN)
                # Never close and reopen on the same bar; this is stricter than the backtest.
                if not opened and not closed_today:
                    weekday = 3 if day < C.EXPIRY_SWITCH_DATE else 1
                    if day.weekday() == weekday:
                        if day != latest or (as_of - day).days > 3:
                            reason = "missed_entry_not_backfilled"
                        elif state["halted"]:
                            reason = "drawdown_halt"
                        else:
                            expiry = _next_expiry(day)
                            decision = algorithm.select(features.loc[ts], first_event_in(events, day, expiry) is not None,
                                                        profile=state["algorithm"])
                            reason = decision.reason
                            if decision.strategy:
                                quote = risk.entry_quote(decision.strategy, float(row["Close"]),
                                                         (expiry - day).days / 365, float(row["VIX"]) / 100)
                                rejection = risk.entry_filter(decision.strategy, quote, state["algorithm"])
                                lots, sizing = risk.size_position(state["realised_equity"], state["peak_equity"],
                                                                  quote["risk_estimate_rs"], state["halted"])
                                reason = rejection or sizing
                                details["candidate"] = decision.strategy
                                details["risk_per_lot_rs"] = quote["risk_estimate_rs"]
                                if not rejection and lots:
                                    quote["legs"] = [asdict(leg) for leg in quote["legs"]]
                                    debit_structure = KIND[decision.strategy] == "debit_vertical"
                                    net = quote["entry_net_pts"]
                                    quote.update(setup=decision.reason,
                                                 condition=decision.condition, volatility=decision.volatility,
                                                 take_profit_pnl_pts=(C.SPREAD_WIDTH - net) * C.DEBIT_TAKE_PROFIT if debit_structure else -net * C.CREDIT_TAKE_PROFIT,
                                                 stop_loss_pnl_pts=-net * C.DEBIT_STOP if debit_structure else net * C.CREDIT_STOP_MULT,
                                                 spot=float(row["Close"]), vix=float(row["VIX"]),
                                                 pricing="modelled", calendar="nominal; holidays unverified")
                                    quote["features"] = {k: float(features.at[ts, k]) for k in
                                                         ("ivr", "adx", "ema_fast", "ema_slow", "realized_vol", "iv_rv_ratio")}
                                    conn.execute("INSERT INTO trades(entry_date,strategy,lots,expiry,status,entry_json) VALUES(?,?,?,?,?,?)",
                                                 (str(day), decision.strategy, lots, str(expiry), "open", _dump(quote)))
                                    state["realised_equity"] -= quote["entry_charges_rs"] * lots
                                    trade = conn.execute("SELECT * FROM trades WHERE status='open'").fetchone()
                                    mark = _mark(trade, row, day)
                                    conn.execute("UPDATE trades SET mark_json=? WHERE id=?", (_dump(mark), trade["id"]))
                                    unrealised = mark["gross_rs"] - mark["exit_charges_total_rs"]
                                    action, reason = "open", decision.reason
                                    details["lots"] = lots
                state["halted"] = state["halted"] or state["realised_equity"] <= state["peak_equity"] * (1 - C.MAX_ACCOUNT_DRAWDOWN)
                conn.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                             (str(day), action, reason, state["realised_equity"], unrealised, _dump(details)))
                state["last_processed"] = str(day)
                count += 1
            _save(conn, state)
        return {"bars_processed": count, "last_processed": state["last_processed"],
                "realised_equity_rs": state["realised_equity"], "halted": state["halted"],
                "orders_submitted": False}
    finally:
        conn.close()


def add_note(path, trade_id, text, emotion=None):
    if not text.strip():
        raise ValueError("A review note cannot be empty")
    conn = _connect(path)
    try:
        with conn:
            if not conn.execute("SELECT id FROM trades WHERE id=?", (trade_id,)).fetchone():
                raise ValueError("Trade ID does not exist")
            conn.execute("INSERT INTO notes(trade_id,recorded_at,emotion,note) VALUES(?,?,?,?)",
                         (trade_id, datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(), emotion, text))
    finally:
        conn.close()


def review(path, output=None):
    conn = _connect(path)
    try:
        state = _state(conn)
        raw = [dict(row) for row in conn.execute("SELECT * FROM trades ORDER BY id")]
        decisions = pd.read_sql_query("SELECT * FROM decisions ORDER BY day", conn)
        notes = pd.read_sql_query("SELECT * FROM notes ORDER BY id", conn)
        records = []
        for trade in raw:
            entry = json.loads(trade.pop("entry_json"))
            exit_data = json.loads(trade.pop("exit_json") or "{}")
            mark = json.loads(trade.pop("mark_json") or "{}")
            records.append({**trade, "setup": entry["setup"], "entry_net_pts": entry["entry_net_pts"],
                            "entry_fills": _dump(entry["fills"]), "legs": _dump(entry["legs"]),
                            "take_profit_pnl_pts": entry["take_profit_pnl_pts"], "stop_loss_pnl_pts": entry["stop_loss_pnl_pts"],
                            "risk_per_lot_rs": entry["risk_estimate_rs"], "exit_reason": exit_data.get("exit_reason"),
                            "exit_fills": _dump(exit_data.get("exit_fills", [])),
                            "fees_rs": entry["entry_charges_rs"] * trade["lots"] + exit_data.get("exit_charges_total_rs", 0),
                            "net_pnl_rs": exit_data.get("net_pnl_rs"), "marked_pnl_rs": mark.get("net_pnl_rs")})
        closed = [r for r in records if r["status"] == "closed"]
        by_setup = {}
        for name in sorted({r["setup"] for r in closed}):
            group = [r for r in closed if r["setup"] == name]
            by_setup[name] = {"closed_trades": len(group), "net_pnl_rs": sum(r["net_pnl_rs"] for r in group),
                              "win_rate_pct": 100 * sum(r["net_pnl_rs"] > 0 for r in group) / len(group),
                              "fees_rs": sum(r["fees_rs"] for r in group)}
        equity = [state["initial_capital"]] + decisions["equity"].tolist()
        peak, max_dd = equity[0], 0.0
        for value in equity:
            peak = max(peak, value)
            max_dd = max(max_dd, 100 * (1 - value / peak))
        last_unrealised = float(decisions.iloc[-1]["unrealised"]) if len(decisions) else 0.0
        result = {"mode": state["mode"], "bot_name": state.get("bot_name", C.BOT_NAME),
                  "algorithm": state["algorithm"], "start_date": state["start_date"], "last_processed": state["last_processed"],
                  "initial_capital_rs": state["initial_capital"], "realised_equity_rs": state["realised_equity"],
                  "marked_equity_rs": state["realised_equity"] + last_unrealised,
                  "halted": state["halted"], "closed_trades": len(closed),
                  "open_trades": sum(r["status"] == "open" for r in records),
                  "win_rate_pct": 100 * sum(r["net_pnl_rs"] > 0 for r in closed) / len(closed) if closed else None,
                  "net_closed_pnl_rs": sum(r["net_pnl_rs"] for r in closed), "max_realised_drawdown_pct": max_dd,
                  "by_setup": by_setup,
                  "sample_status": "insufficient_sample" if len(closed) < 100 else "review_required_not_validated",
                  "sample_note": "100 closed trades is a review milestone, not proof of an edge; prices and fills are modelled",
                  "skip_reasons": decisions.loc[decisions.action == "skip", "reason"].value_counts().to_dict(),
                  "orders_submitted": False}
        if output:
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            columns = ["id", "entry_date", "strategy", "lots", "expiry", "status", "exit_date", "setup", "entry_net_pts",
                       "entry_fills", "legs", "take_profit_pnl_pts", "stop_loss_pnl_pts", "risk_per_lot_rs", "exit_reason",
                       "exit_fills", "fees_rs", "net_pnl_rs", "marked_pnl_rs"]
            pd.DataFrame(records, columns=columns).to_csv(output / "trades.csv", index=False)
            decisions.to_csv(output / "decisions.csv", index=False)
            notes.to_csv(output / "notes.csv", index=False)
            (output / "review.json").write_text(_dump(result) + "\n")
        return result
    finally:
        conn.close()


def daily(path=DEFAULT_DB, capital=None, output=None, refresh_data=False):
    """One manual paper session: optional data refresh, manage positions and export."""
    if refresh_data:
        from update_data import fetch
        fetch(C.NIFTY_URL, ROOT / C.NIFTY_CSV)
        fetch(C.VIX_URL, ROOT / C.VIX_CSV)
    mkt = load_market()
    path = Path(path)
    if not path.exists():
        initialise(path, C.PAPER_CAPITAL if capital is None else capital, mkt)
    result = process(path, mkt)
    review_result = review(path, output or ROOT / "paper" / "review")
    from live_signal import latest_signal
    signal = latest_signal(mkt, capital=review_result["realised_equity_rs"], profile=review_result["algorithm"])
    if review_result["open_trades"] or review_result["halted"]:
        signal.update(strategy="no trade", preview_lots=0,
                      reason="position_open" if review_result["open_trades"] else "drawdown_halt")
    signal["risk_context"] = "paper account equity; open-position and persistent halt checks applied"
    result.update(account=review_result, signal=signal, next_action="Update completed daily data and run another paper session")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "process", "review", "note", "daily"):
        child = sub.add_parser(command)
        child.add_argument("--db", type=Path, default=DEFAULT_DB)
        if command in ("init", "daily"):
            child.add_argument("--capital", type=float, default=C.PAPER_CAPITAL)
        if command == "init":
            child.add_argument("--profile", choices=algorithm.PAPER_PROFILES, default=C.ALGORITHM)
        if command == "daily":
            child.add_argument("--refresh-data", action="store_true")
        if command == "review":
            child.add_argument("--output", type=Path, default=ROOT / "paper" / "review")
        if command == "note":
            child.add_argument("--trade-id", type=int, required=True)
            child.add_argument("--text", required=True)
            child.add_argument("--emotion")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialise(args.db, args.capital, load_market(), profile=args.profile)
            result = {k: v for k, v in result.items() if k != "policy"}
        elif args.command == "process":
            result = process(args.db, load_market())
        elif args.command == "review":
            result = review(args.db, args.output)
        elif args.command == "daily":
            result = daily(args.db, capital=args.capital, refresh_data=args.refresh_data)
        else:
            add_note(args.db, args.trade_id, args.text, args.emotion)
            result = {"note_added": True, "trade_id": args.trade_id}
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"Paper account: {exc}\n")


if __name__ == "__main__":
    main()
