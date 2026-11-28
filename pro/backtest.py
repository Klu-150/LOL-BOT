"""Walk-forward backtest of the adaptive engine.  python -m pro.backtest"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data import ROOT
from pro import engine, features

OUT = ROOT / "results" / "pro"


def stats(df, col="pts"):
    if df.empty:
        return {"trades": 0}
    x = df[col]
    wins, losses = x[x > 0].sum(), -x[x < 0].sum()
    curve = x.cumsum()
    return {"trades": int(len(x)), "win_rate_%": round(100 * (x > 0).mean(), 1),
            "avg_pts": round(x.mean(), 1), "total_pts": round(x.sum(), 0),
            "avg_R": round(df.r.mean(), 2) if "r" in df else None,
            "profit_factor": round(wins / losses, 2) if losses else None,
            "max_dd_pts": round((curve - curve.cummax()).min(), 0)}


def run(start="2016-01-01", cost=engine.COST_PTS, write=True):
    f = features.load()
    trades = []
    for s in engine.LIBRARY:
        trades += engine.simulate(f, s, cost)
    chosen, decisions = engine.select(f, trades)
    t_all = engine.trades_frame([t for t in trades if t.exit_date is not None])
    t_sel = engine.trades_frame([t for t in chosen if t.exit_date is not None])
    t_all = t_all[t_all.entry_date >= start]
    t_sel = t_sel[t_sel.entry_date >= start]

    table = {"ADAPTIVE (selector)": stats(t_sel)}
    for name, g in t_all.groupby("strategy"):
        table[name] = stats(g)
    period = f.loc[start:]
    table["buy_and_hold_index"] = {"total_pts": round(period.Close.iloc[-1] - period.Open.iloc[0], 0),
                                   "max_dd_pts": round((period.Close - period.Close.cummax()).min(), 0)}
    yearly = t_sel.groupby(t_sel.entry_date.dt.year).pts.agg(["count", "sum"]).round(0) if len(t_sel) else pd.DataFrame()
    by_regime = t_sel.groupby(["regime", "strategy"]).agg(trades=("pts", "size"), total_pts=("pts", "sum"),
                                                          avg_R=("r", "mean")).round(2) if len(t_sel) else pd.DataFrame()
    acct, end_equity = engine.option_account(f, [t for t in chosen if t.entry_date >= pd.Timestamp(start)])
    result = {"period": [str(f.loc[start:].index[0].date()), str(f.index[-1].date())], "cost_pts_per_side": cost,
              "table": table, "options_account": {"start_rs": 500000, "end_rs": round(end_equity, 0),
                                                  "trades": int(len(acct)),
                                                  "max_dd_rs": round(float((acct.equity_rs - acct.equity_rs.cummax()).min()), 0) if len(acct) else 0}}
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        t_sel.to_csv(OUT / "adaptive_trades.csv", index=False)
        t_all.to_csv(OUT / "all_strategy_trades.csv", index=False)
        acct.to_csv(OUT / "options_account.csv", index=False)
        pd.DataFrame(decisions).to_csv(OUT / "decisions.csv", index=False)
        (OUT / "results.json").write_text(json.dumps(result, indent=2, default=str))
        md = [f"# Adaptive engine walk-forward backtest\n", f"Period {result['period'][0]} to {result['period'][1]}, "
              f"cost {cost} index pts per side.\n", "## Signal quality (index points, 1 unit)\n",
              pd.DataFrame(table).T.to_markdown(), "\n## Adaptive by year\n", yearly.to_markdown(),
              "\n## Adaptive by regime/strategy\n", by_regime.to_markdown(),
              "\n## Options account (debit spreads, modelled prices)\n", json.dumps(result["options_account"], indent=2)]
        (OUT / "summary.md").write_text("\n".join(md))
    return result, yearly, by_regime


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2016-01-01")
    p.add_argument("--cost", type=float, default=engine.COST_PTS)
    a = p.parse_args()
    res, yearly, by_regime = run(a.start, a.cost)
    print(pd.DataFrame(res["table"]).T.to_string())
    print("\nAdaptive by year:\n", yearly.to_string())
    print("\nBy regime:\n", by_regime.to_string())
    print("\nOptions account:", res["options_account"])
