"""Charts (PNG), a markdown summary and a JSON dump of the results."""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as C
import strategies as ST
import algorithm

# validated categorical palette (light mode) + chart ink
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, MUTED, GRID, BASE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SURFACE = "#fcfcfb"
NEG, POS = "#e34948", "#2a78d6"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_equity(wide: pd.DataFrame, cols, path: Path):
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=SURFACE)
    _style(ax)
    for i, c in enumerate(cols):
        eq = wide[c].cumsum()
        ax.plot(eq.index, eq.values, color=SERIES[i], linewidth=2, label=c)
        ax.annotate(f"{c}  ₹{eq.iloc[-1]:,.0f}", (eq.index[-1], eq.iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", color=INK2, fontsize=8, va="center")
    ax.axhline(0, color=BASE, linewidth=1)
    ax.set_title("Cumulative P&L per 1 lot, after costs (₹)", loc="left", color=INK, fontsize=12)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def chart_strategy_bars(summary: pd.DataFrame, path: Path):
    s = summary["avg_per_trade_rs"].sort_values()
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.barh(s.index, s.values, color=[NEG if v < 0 else POS for v in s.values], height=0.6)
    for y, v in enumerate(s.values):
        ax.annotate(f"₹{v:,.0f}", (v, y), xytext=(4 if v >= 0 else -4, 0), textcoords="offset points",
                    ha="left" if v >= 0 else "right", va="center", fontsize=8, color=INK2)
    ax.axvline(0, color=BASE, linewidth=1)
    ax.set_title("Average P&L per trade per lot (₹, after costs)", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def chart_regime_heatmap(matrix: pd.DataFrame, path: Path):
    m = matrix.drop(columns=["weeks"])
    lim = np.nanpercentile(np.abs(m.values), 90)
    fig, ax = plt.subplots(figsize=(11, 6), facecolor=SURFACE)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("div", [NEG, "#f0efec", POS])
    ax.imshow(m.values, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(m.shape[1]), m.columns, rotation=30, ha="right", fontsize=8, color=INK2)
    ax.set_yticks(range(m.shape[0]), [f"{r}  (n={int(matrix.loc[r, 'weeks'])})" for r in m.index],
                  fontsize=8, color=INK2)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=7, color=INK)
    ax.set_title("Avg ₹ per lot per week, by regime (rows) and strategy (columns)",
                 loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _fmt_table(df: pd.DataFrame) -> str:
    # A regime label contains " | "; escape it so Markdown keeps the cell intact.
    table = df.rename(index=lambda x: str(x).replace("|", "\\|"),
                      columns=lambda x: str(x).replace("|", "\\|"))
    return table.to_markdown(floatfmt=",.1f")


def _json_clean(value):
    if isinstance(value, dict):
        return {k: _json_clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_clean(v) for v in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(value):
        return None
    return value


def write_all(out: Path, weeks, trades, wide, summary, matrix, sensitivity, yearly, latest,
              account=None, evaluation=None):
    out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "trades.csv", index=False)
    weeks.to_csv(out / "weeks.csv", index=False)
    summary.to_csv(out / "summary.csv")
    matrix.to_csv(out / "regime_matrix.csv")
    sensitivity.to_csv(out / "sensitivity.csv")
    if account is not None:
        account.to_csv(out / "account.csv", index=False)
    if evaluation is not None:
        evaluation.to_csv(out / "evaluation.csv", index=False)

    chart_equity(wide, ["REGIME_BOT", "LEGACY_BOT", "iron_condor", "bear_call_spread"],
                 out / "equity_curve.png")
    chart_strategy_bars(summary, out / "strategy_avg.png")
    chart_regime_heatmap(matrix, out / "regime_heatmap.png")

    period = f"{weeks['entry'].min()} to {weeks['front'].max()}"
    md = [
        f"# {C.BOT_NAME}: weekly condition-router backtest",
        "",
        f"Period: {period} ({len(weeks)} weekly expiries). Per 1 lot ({C.LOT_SIZE} units), "
        "after Zerodha brokerage, STT, exchange charges, GST, stamp duty and slippage.",
        "",
        "Prices are **modelled** (Black-Scholes with India VIX + skew), not real option quotes.",
        "This is the weekly research comparison. The intraday backtest is in results/intraday/summary.md.",
        f"All structures in this run use {C.SPREAD_WIDTH}-point hedges and {C.LOT_SIZE} units per lot.",
        "",
        "## Condition-to-strategy playbook",
        _fmt_table(pd.DataFrame(algorithm.playbook())),
        f"Algorithm: **{C.ALGORITHM}**. Comparison tables assume one lot whenever the policy selects a trade; "
        "they do not apply account sizing. The account below applies risk limits.",
        "Same-close signal/fill modelling is optimistic. Expiries are inferred from available trading days; "
        "missing rows can be mistaken for holidays. Event coverage is limited to events.csv.",
        "No broker margin, liquidity, intraday fills, historical lot/rate changes or real option IV surface is modelled.",
        "",
        "## Trading plan and forward paper journal",
        "Read the [five-step trading plan](../TRADING_PLAN.md) for market, timeframe, "
        "setup, entry trigger, exits and review rules. Run `paper_trade.py init` once, "
        "then `paper_trade.py process` after updating completed daily bars, and "
        "`paper_trade.py review` to export fills, outcomes and optional human notes. "
        "Paper fills remain modelled and no orders are submitted.",
        f"Selected historical trades: {int(summary.loc['REGIME_BOT', 'trades'])}. "
        "A 100-trade milestone is only a review threshold, not a statistical guarantee or live-readiness test.",
        "",
        "## Risk-sized account",
        "```", json.dumps(latest.get("account_sim", {}), indent=2), "```",
        "Sizing uses full payoff loss plus estimated fees and a cost buffer, capped at "
        f"{C.RISK_PER_TRADE:.0%} of current equity; maximum {C.MAX_LOTS} lots. "
        f"New entries halt after {C.MAX_ACCOUNT_DRAWDOWN:.0%} realised drawdown. "
        "Fee reserves are estimates, not guaranteed maximum losses; stops are checked only at daily closes. "
        "Zero trades means the account could not satisfy the filters or risk budget, not evidence of an edge.",
        "",
        "## Chronological evaluation",
        f"Split: {C.EVALUATION_SPLIT}. Rules are fixed, with no automatic fitting or winner selection. "
        "Development excludes weeks crossing the split. This history has already been inspected, "
        "so the later period is a diagnostic, not an untouched out-of-sample claim.",
        _fmt_table(evaluation) if evaluation is not None else "Not run.",
        "",
        "## Strategy comparison",
        _fmt_table(summary),
        "",
        "## Sensitivity: average ₹ per trade per lot",
        _fmt_table(sensitivity),
        "",
        "## Regime bot by year (₹ per lot)",
        _fmt_table(yearly.to_frame("REGIME_BOT ₹")),
        "",
        "## Average ₹ per lot by regime and strategy",
        _fmt_table(matrix),
        "",
        "## Latest regime",
        "```", json.dumps(latest, indent=2, default=str), "```",
    ]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")

    def ser(s):
        return [[d.strftime("%Y-%m-%d"), round(float(v), 1)] for d, v in s.items()]

    payload = {
        "period": period,
        "weeks": len(weeks),
        "lot_size": C.LOT_SIZE,
        "algorithm": C.ALGORITHM,
        "label": "Weekly adaptive router · 100pt",
        "bot_name": C.BOT_NAME,
        "timeframe": "weekly",
        "spread_width": C.SPREAD_WIDTH,
        "playbook": algorithm.playbook(),
        "evaluation": evaluation.round(2).to_dict("records") if evaluation is not None else [],
        "account": latest.get("account_sim", {}),
        "summary": summary.round(1).reset_index().rename(columns={"index": "strategy"}).to_dict("records"),
        "sensitivity": sensitivity.round(0).reset_index().rename(columns={"index": "strategy"}).to_dict("records"),
        "yearly": {str(k): round(float(v), 0) for k, v in yearly.items()},
        "equity": {c: ser(wide[c].cumsum()) for c in wide.columns},
        "regime_matrix": matrix.round(0).reset_index().to_dict("records"),
        "regime_counts": weeks.groupby(["trend", "iv"]).size().rename("n").reset_index().to_dict("records"),
        "picks": weeks["pick"].fillna("no trade").value_counts().to_dict(),
        "latest": latest,
    }
    (out / "results.json").write_text(json.dumps(_json_clean(payload), default=str, allow_nan=False), encoding="utf-8")
