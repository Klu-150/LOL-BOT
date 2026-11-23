"""
Run the full backtest and write everything to results/.

    python run_backtest.py              # main run + sensitivity variants
    python run_backtest.py --quick      # main run only
"""
import argparse
from pathlib import Path

import pandas as pd

import backtest as B
import config as C
import report
import algorithm
from live_signal import latest_signal

ROOT = Path(__file__).resolve().parent

ZERO_COSTS = dict(BROKERAGE_PER_ORDER=0, STT_SELL_PREMIUM=0, STT_EXERCISE=0, EXCHANGE_TXN=0,
                  SEBI_FEE=0, STAMP_BUY=0, SLIPPAGE_FIXED=0, SLIPPAGE_PCT=0)


def run_with(**overrides):
    old = {k: getattr(C, k) for k in overrides}
    for k, v in overrides.items():
        setattr(C, k, v)
    try:
        mkt, feat, weeks, trades = B.run()
        wide = B.weekly_pnl(weeks, trades)
        return mkt, feat, weeks, trades, wide, B.summary_table(weeks, trades, wide)
    finally:
        for k, v in old.items():
            setattr(C, k, v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--profile", choices=algorithm.PROFILES, default=C.ALGORITHM)
    ap.add_argument("--capital", type=float, default=C.PAPER_CAPITAL)
    ap.add_argument("--output", type=Path, default=ROOT / "results")
    args = ap.parse_args()
    if not 0 < args.capital < float("inf"):
        ap.error("--capital must be finite and positive")
    C.ALGORITHM = args.profile
    C.START_CAPITAL = args.capital

    mkt, feat, weeks, trades, wide, summary = run_with()
    print(f"\nWeeks simulated: {len(weeks)}   ({weeks['entry'].min()} -> {weeks['front'].max()})")
    print("\nPer 1 lot, after all costs (Rs):")
    print(summary.round(1).to_string())

    variants = {"base (config)": summary["avg_per_trade_rs"]}
    if not args.quick:
        variants["hold to expiry"] = run_with(MANAGE_EXITS=False)[-1]["avg_per_trade_rs"]
        variants["no costs"] = run_with(**ZERO_COSTS)[-1]["avg_per_trade_rs"]
        variants["2x slippage"] = run_with(SLIPPAGE_FIXED=C.SLIPPAGE_FIXED * 2,
                                           SLIPPAGE_PCT=C.SLIPPAGE_PCT * 2)[-1]["avg_per_trade_rs"]
    sensitivity = pd.DataFrame(variants)
    print("\nSensitivity, avg Rs per trade per lot:")
    print(sensitivity.round(0).to_string())

    yearly = B.by_year(wide["REGIME_BOT"])
    matrix = B.regime_matrix(trades)
    account = B.account_simulation(weeks, trades)
    evaluation = B.period_evaluation(weeks, wide)
    latest = latest_signal(mkt, feat, capital=args.capital)
    print("\nChronological diagnostic split (not untouched validation):")
    print(evaluation.round(1).to_string(index=False))
    print(f"\nRisk-sized account: start Rs {C.START_CAPITAL:,.0f}, "
          f"end Rs {account['equity_rs'].iloc[-1]:,.0f}, "
          f"trades {int((account['lots'] > 0).sum())}")
    latest["account_sim"] = {
        "start": C.START_CAPITAL, "risk_per_trade": C.RISK_PER_TRADE,
        "trades": int((account["lots"] > 0).sum()),
        "end": round(float(account["equity_rs"].iloc[-1]), 2),
        "max_drawdown_pct": round(float(account["drawdown_pct"].max()), 2),
        "halted": bool(account["halted"].iloc[-1]),
    }

    report.write_all(args.output, weeks, trades, wide, summary, matrix, sensitivity, yearly, latest,
                     account=account, evaluation=evaluation)
    print(f"\nSaved reports to {args.output}")
    print("\nLatest regime:", latest)


if __name__ == "__main__":
    main()
