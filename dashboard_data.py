"""Read-only dashboard snapshots from existing reports, market CSVs and paper ledger."""
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd

from data import ROOT, load_market
import regime
import config as C


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if hasattr(value, "item"):
        return clean(value.item())
    return value


def csv_records(path):
    if not path.is_file():
        return []
    return clean(pd.read_csv(path).to_dict("records"))


def paper_snapshot(path):
    if not path.is_file():
        return {"available": False, "trades": [], "decisions": [], "notes": []}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        state = json.loads(conn.execute("SELECT value FROM meta WHERE key='account'").fetchone()[0])
        trades = []
        for row in conn.execute("SELECT * FROM trades ORDER BY id DESC"):
            trade = dict(row)
            for key in ("entry_json", "exit_json", "mark_json"):
                trade[key.removesuffix("_json")] = json.loads(trade.pop(key) or "{}")
            trades.append(trade)
        decisions = [dict(row) for row in conn.execute("SELECT day,action,reason,equity,unrealised FROM decisions ORDER BY day")]
        notes = [dict(row) for row in conn.execute("SELECT * FROM notes ORDER BY id DESC")]
    closed = [trade for trade in trades if trade["status"] == "closed"]
    last_unrealised = decisions[-1]["unrealised"] if decisions else 0
    return clean({"available": True, "algorithm": state.get("algorithm", "credit_regime"),
                  "start_date": state["start_date"], "last_processed": state["last_processed"],
                  "initial_capital_rs": state["initial_capital"], "realised_equity_rs": state["realised_equity"],
                  "marked_equity_rs": state["realised_equity"] + last_unrealised, "halted": state["halted"],
                  "closed_trades": len(closed), "open_trades": len(trades) - len(closed),
                  "net_closed_pnl_rs": sum(t["exit"].get("net_pnl_rs", 0) for t in closed),
                  "trades": trades, "decisions": decisions, "notes": notes})


def build_snapshot(root=ROOT):
    root = Path(root)
    primary = root / "results" / "results.json"
    report_files = [primary, *sorted(set([*root.glob("results/*/results.json"),
                                         *root.glob("results/algorithms/*/results.json")]) - {primary})]
    reports, warnings = [], []
    for path in report_files:
        if not path.is_file():
            continue
        try:
            report = json.loads(path.read_text())
            if not isinstance(report.get("summary"), list) or not report["summary"] or not isinstance(report.get("equity"), dict):
                raise ValueError("report needs summary and equity")
            report["id"] = str(path.parent.relative_to(root))
            report["label"] = report.get("label") or ("Weekly research" if path.parent == root / "results" else path.parent.name.replace("_", " ").title())
            report["trades"] = csv_records(path.parent / "trades.csv")
            report["weekly_decisions"] = csv_records(path.parent / "weeks.csv")
            report["account_ledger"] = csv_records(path.parent / "account.csv")
            reports.append(clean(report))
        except (ValueError, OSError, pd.errors.ParserError) as exc:
            warnings.append(f"Could not load {path.relative_to(root)}: {exc}")
    if not reports:
        raise ValueError("No valid results/results.json found. Run run_backtest.py first.")
    reports.sort(key=lambda r: r.get("algorithm") != "adaptive_intraday")
    # Market loading uses the bot's configured local CSVs; never fetch remotely.
    market = regime.classify(regime.add_features(load_market()))
    market = market.reset_index().rename(columns={"Date": "date", "Close": "close", "Open": "open",
                                                 "High": "high", "Low": "low", "VIX": "vix"})
    market["date"] = market["date"].dt.strftime("%Y-%m-%d")
    columns = ["date", "open", "high", "low", "close", "vix", "ema_fast", "ema_slow", "adx", "ivr", "realized_vol", "trend", "iv"]
    try:
        intraday_path = root / C.INTRADAY_DB
        if intraday_path.is_file():
            from ledger_store import snapshot as intraday_snapshot
            paper = intraday_snapshot(intraday_path)
            closed = []
            for trade in paper["trades"]:
                closed.append({"id": trade["id"], "entry_date": trade["entry"], "exit_date": trade["exit"],
                               "strategy": trade["strategy"], "lots": trade["lots"], "expiry": trade["expiry"],
                               "status": "closed", "entry": trade,
                               "exit": {"exit_reason": trade["exit_reason"], "net_pnl_rs": trade["net_pnl_rs"],
                                        "exit_fills": trade.get("exit_fills", [])},
                               "mark": trade.get("mark", {})})
            if paper.get("position"):
                position = paper["position"]
                closed.insert(0, {"id": "open", "entry_date": position["entry"], "exit_date": None,
                                  "strategy": position["strategy"], "lots": position["lots"], "expiry": position["expiry"],
                                  "status": "open", "entry": position, "exit": {}, "mark": position.get("mark", {})})
            paper["trades"] = closed
            paper["decisions"] = [{**row, "day": row["timestamp"], "equity": row["equity_rs"], "unrealised": 0}
                                  for row in paper["decisions"]]
        else:
            paper = paper_snapshot(root / "paper" / "account.sqlite3")
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        warnings.append(f"Paper account unavailable: {exc}")
        paper = {"available": False, "trades": [], "decisions": [], "notes": []}
    from order_view import order_book
    paper["orders"], paper["order_warnings"] = order_book(paper)
    intraday = {"available": False, "bars": [], "playbook": __import__('algorithm').playbook()}
    feed_path = root / C.INTRADAY_CSV
    if feed_path.is_file():
        try:
            from intraday_feed import load as intraday_load
            from intraday_engine import features as intraday_features, decision
            observed = intraday_features(intraday_load(feed_path))
            latest = observed.iloc[-1]
            pick = decision(latest)
            bars = observed.iloc[-300:].reset_index().rename(columns={"index": "timestamp"})
            bars["timestamp"] = bars["timestamp"].map(lambda ts: ts.isoformat())
            intraday_columns = ["timestamp", "Open", "High", "Low", "Close", "VIX", "trigger_fast", "trigger_slow", "ema_fast", "ema_slow", "adx", "ivr"]
            intraday.update(available=True, bars=bars[intraday_columns].to_dict('records'), latest_bar=observed.index[-1].isoformat(),
                            condition=pick.condition, volatility=pick.volatility, candidate=pick.strategy, reason=pick.reason,
                            vix_source=str(latest.vix_source))
        except (ValueError, OSError, KeyError) as exc:
            warnings.append(f"Intraday data unavailable: {exc}")
    runtime_path = root / 'paper' / 'intraday_runtime.json'
    runtime = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {"enabled": False, "state": "stopped"}
    return clean({"schema_version": 1, "bot_name": C.BOT_NAME, "intraday": intraday, "automation": runtime,
                  "generated_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                  "market_as_of": market.iloc[-1]["date"], "reports": reports,
                  "market": market[columns].to_dict("records"), "paper": paper, "warnings": warnings,
                  "settings": {name: getattr(C, name) for name in
                               ("RISK_PER_TRADE", "MAX_LOTS", "MAX_ACCOUNT_DRAWDOWN", "SPREAD_WIDTH", "MIN_IV_RANK",
                                "MIN_IV_RV_RATIO", "CREDIT_TAKE_PROFIT", "CREDIT_STOP_MULT", "LOT_SIZE")},
                  "trading_plan": (root / "TRADING_PLAN.md").read_text() if (root / "TRADING_PLAN.md").is_file() else "",
                  "pricing": "Modelled option prices and fills. Daily closes. No broker orders."})


def export_snapshot(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot()
    path.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")))
    return payload
