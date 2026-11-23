"""Backtest automatic intraday switching on observed 5m bars, with model option fills."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

import backtest as B
import config as C
from data import ROOT
import intraday_engine as E
import intraday_feed as F
from report import _json_clean


def simulate(prepared, capital):
    state = E.new_state(capital)
    events, trades, incomplete = [], [], []
    for session, day in prepared.groupby(prepared.index.date):
        if day.index[0].strftime("%H:%M") > C.INTRADAY_ENTRY_START or day.index[-1].strftime("%H:%M") < C.INTRADAY_EXIT_TIME:
            incomplete.append(str(session))
            continue
        for ts, row in day.iterrows():
            event, closed = E.step(state, row, ts)
            events.append(event)
            if closed:
                trades.append(closed)
        if state["position"]:
            raise AssertionError("A complete session left an overnight position")
    return state, events, trades, incomplete


def trade_stats(trades, events):
    pnls = pd.Series([t["pnl_rs"] for t in trades], dtype=float)
    if events:
        dates = sorted(set(e["timestamp"][:10] for e in events))
        daily = pd.Series(0., index=pd.to_datetime(dates))
        for t in trades:
            daily.at[pd.Timestamp(t["exit"][:10])] += t["pnl_rs"]
    else:
        daily = pd.Series(dtype=float)
    stats = B.stats(daily)
    positives, negatives = pnls[pnls > 0].sum(), pnls[pnls < 0].sum()
    stats.update(trades=len(pnls), **{"win_rate_%": 100 * (pnls > 0).mean() if len(pnls) else None},
                 avg_per_trade_rs=pnls.mean() if len(pnls) else None, worst_trade_rs=pnls.min() if len(pnls) else None,
                 best_trade_rs=pnls.max() if len(pnls) else None, profit_factor=positives / -negatives if negatives else None,
                 sharpe_weekly_ann=None)
    return stats, daily


def run(output=None, capital=C.PAPER_CAPITAL):
    output = Path(output or ROOT / "results" / "intraday")
    bars = F.load()
    prepared = E.features(bars)
    state, events, trades, incomplete = simulate(prepared, capital)
    stats, daily = trade_stats(trades, events)
    sensitivities = {"base (config)": stats["avg_per_trade_rs"]}
    settings = ["BROKERAGE_PER_ORDER", "STT_SELL_PREMIUM", "STT_EXERCISE", "EXCHANGE_TXN", "SEBI_FEE", "STAMP_BUY", "SLIPPAGE_FIXED", "SLIPPAGE_PCT"]
    original = {k: getattr(C, k) for k in settings}
    try:
        for k in settings:
            setattr(C, k, 0.)
        sensitivity = simulate(prepared, capital)
        sensitivities["no costs"] = trade_stats(sensitivity[2], sensitivity[1])[0]["avg_per_trade_rs"]
    finally:
        for k, v in original.items():
            setattr(C, k, v)
    try:
        C.SLIPPAGE_FIXED *= 2
        C.SLIPPAGE_PCT *= 2
        sensitivity = simulate(prepared, capital)
        sensitivities["2x slippage"] = trade_stats(sensitivity[2], sensitivity[1])[0]["avg_per_trade_rs"]
    finally:
        for k, v in original.items():
            setattr(C, k, v)
    closed = []
    for t in trades:
        legs = "; ".join(f"{'+' if l['qty']>0 else '-'}{int(l['K'])}{l['cp']}" for l in t["legs"])
        closed.append({**{k: v for k, v in t.items() if k not in ["legs", "fills", "mark", "exit_fills"]},
                       "legs": legs, "max_loss_rs": t["payoff_max_loss_rs"], "trend": t["condition"], "iv": t["volatility"]})
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(closed).to_csv(output / "trades.csv", index=False)
    pd.DataFrame(events).to_csv(output / "decisions.csv", index=False)
    equity = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in daily.cumsum().items()]
    last = prepared.iloc[-1]
    pick = E.decision(last)
    summary = {"strategy": "INTRADAY_BOT", **stats}
    report = {"label": C.BOT_NAME + " · intraday", "algorithm": "adaptive_intraday", "timeframe": "intraday",
              "period": f"{bars.index[0].date()} to {bars.index[-1].date()}", "weeks": len(daily), "sessions": len(daily),
              "lot_size": C.LOT_SIZE, "spread_width": C.SPREAD_WIDTH, "summary": [summary],
              "equity": {"INTRADAY_BOT": equity}, "sensitivity": [{"strategy": "INTRADAY_BOT", **sensitivities}],
              "account": {"start": capital, "end": state["equity"], "trades": len(trades), "risk_per_trade": C.RISK_PER_TRADE,
                          "halted": state["halted"]}, "evaluation": [],
              "latest": {"date": str(bars.index[-1].date()), "nifty_close": float(last.Close),
                         "india_vix": float(last.VIX) if pd.notna(last.VIX) else None, "iv_rank": float(last.ivr) if pd.notna(last.ivr) else None,
                         "adx": float(last.adx) if pd.notna(last.adx) else None, "trend": pick.condition, "iv_rv_ratio": float(last.iv_rv_ratio) if pd.notna(last.iv_rv_ratio) else None,
                         "strategy": pick.strategy or "no trade", "reason": pick.reason},
              "playbook": __import__('algorithm').playbook(), "incomplete_sessions_excluded": incomplete,
              "assumptions": ["Observed public 5m underlying data; synthetic option prices and fills",
                              "15m completed bias / 5m entry; square-off target 15:15 IST",
                              "VIX is a labelled prior-day pricing proxy where intraday observations are absent",
                              "Same-bar fills are optimistic; no broker margin or real option bid/ask data",
                              "Short recent history; not a validated trading edge"]}
    (output / "results.json").write_text(json.dumps(_json_clean(report), allow_nan=False, default=str))
    md = [f"# {C.BOT_NAME}: intraday backtest", "", f"Period: {report['period']}; {len(daily)} complete sessions.",
          "", pd.DataFrame([summary]).to_markdown(index=False, floatfmt=',.2f'), "", "## Risk-sized virtual account", "",
          json.dumps(report["account"], indent=2), "", "## Assumptions", "", *[f"- {v}" for v in report["assumptions"]],
          "", f"Excluded incomplete sessions: {', '.join(incomplete) or 'none'}.", "",
          "All trades were closed within their entry session. These are historical model fills, not forward paper fills."]
    (output / "summary.md").write_text('\n'.join(md))
    return _json_clean({"sessions": len(daily), "trades": len(trades), "summary": stats,
                        "account_end_rs": state["equity"], "output": str(output), "assumptions": report["assumptions"]})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "intraday")
    parser.add_argument("--capital", type=float, default=C.PAPER_CAPITAL)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.capital), indent=2))
