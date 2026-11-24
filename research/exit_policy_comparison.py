"""Offline hedged exit-policy experiments; no broker or paper-account interface.

Independent implementations of ideas in the supplied strategy archive. Each replay
runs in a new process with the bot's existing hedged entries and risk limits.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

VARIANTS = ('baseline', 'basket_fixed_points', 'basket_percentage',
            'basket_trailing', 'daily_mtm_guard')
LABELS = {'baseline': 'Existing adaptive exits', 'basket_fixed_points': '30-point basket stop',
          'basket_percentage': '30% credit basket stop',
          'basket_trailing': 'Credit profit trail', 'daily_mtm_guard': '1% daily MTM guard'}


@dataclass
class BasketExit:
    mode: str
    peak_points: float = 0.

    def __post_init__(self):
        if self.mode not in VARIANTS:
            raise ValueError('Unsupported research exit policy')

    def reset(self):
        self.peak_points = 0.

    def reason(self, pnl_points, credit_points):
        if not all(math.isfinite(x) for x in (pnl_points, credit_points)) or credit_points <= 0:
            raise ValueError('Use finite P&L and positive entry credit')
        self.peak_points = max(self.peak_points, pnl_points)
        if self.mode == 'basket_fixed_points' and pnl_points <= -30:
            return 'research_fixed_basket_stop'
        if self.mode == 'basket_percentage' and pnl_points <= -.30 * credit_points:
            return 'research_percentage_basket_stop'
        if (self.mode == 'basket_trailing' and self.peak_points >= .25 * credit_points
                and self.peak_points - pnl_points >= .15 * credit_points):
            return 'research_basket_trail'
        return None


def mtm_reason(marked_equity, session_equity):
    if not all(math.isfinite(x) for x in (marked_equity, session_equity)) or session_equity <= 0:
        raise ValueError('Use finite equity and positive session capital')
    change = marked_equity - session_equity
    if change <= -.01 * session_equity:
        return 'research_daily_mtm_loss'
    if change >= .01 * session_equity:
        return 'research_daily_mtm_target'
    return None


def worker(source, mode, sessions):
    import pandas as pd
    import intraday_engine as E
    import strategies as ST
    import config as C
    if mode not in VARIANTS:
        raise ValueError('Unsupported research exit policy')
    bars = pd.DataFrame(source['bars'])
    bars.index = pd.to_datetime(bars.pop('timestamp'), utc=True).dt.tz_convert(E.ZONE)
    state = E.new_state(500000)
    policy = BasketExit(mode)
    original_exit = ST.exit_signal
    trades, daily_curve = [], []
    peak, max_dd, cumulative_per_lot = 500000., 0., 0.
    day_locked = False

    def exit_reason(name, points, entry_net):
        nonlocal day_locked
        if mode == 'daily_mtm_guard':
            marked = state['equity'] + state['position']['mark']['gross_rs'] - state['position']['mark']['exit_charges_rs']
            reason = mtm_reason(marked, state['session_equity'])
            if reason:
                day_locked = True
                return reason
        if ST.KIND[name] == 'credit':
            reason = policy.reason(points, -entry_net)
            if reason:
                return reason
        return original_exit(name, points, entry_net)

    ST.exit_signal = exit_reason
    try:
        for session, day in bars.groupby(bars.index.date):
            if str(session) not in sessions:
                continue
            if (day.index[0].strftime('%H:%M') > C.INTRADAY_ENTRY_START
                    or day.index[-1].strftime('%H:%M') < C.INTRADAY_EXIT_TIME):
                raise ValueError('An explicitly selected replay session is incomplete')
            day_locked = False
            for ts, row in day.iterrows():
                if state['position'] is None:
                    policy.reset()
                before_equity = state['equity']
                event, closed = E.step(state, row, ts, allow_entry=not day_locked)
                if event['action'] == 'open':
                    assert state['position']['lots'] * state['position']['risk_estimate_rs'] <= before_equity * C.RISK_PER_TRADE + 1e-6
                if closed:
                    trades.append(closed)
                    cumulative_per_lot += closed['net_pnl_rs'] / closed['lots']
                if mode == 'daily_mtm_guard' and mtm_reason(state['equity'], state['session_equity']):
                    day_locked = True
                marked = state['equity']
                if state['position']:
                    value = state['position']['mark']
                    marked += value['gross_rs'] - value['exit_charges_rs']
                peak = max(peak, marked)
                max_dd = min(max_dd, marked - peak)
            if state['position']:
                raise ValueError('Missing exit observation: refusing an invented overnight close')
            daily_curve.append([str(session), cumulative_per_lot])
    finally:
        ST.exit_signal = original_exit
    pnls = [t['net_pnl_rs'] for t in trades]
    return {'policy': mode, 'label': LABELS[mode], 'sessions': len(daily_curve),
            'trades_count': len(trades), 'net_account_pnl_rs': state['equity'] - 500000,
            'ending_virtual_equity_rs': state['equity'], 'marked_max_drawdown_rs': max_dd,
            'win_rate_pct': 100 * sum(p > 0 for p in pnls) / len(pnls) if pnls else None,
            'net_per_lot_sum_rs': cumulative_per_lot,
            'all_same_day_exits': all(t['entry'][:10] == t['exit'][:10] for t in trades),
            'curve_per_lot': daily_curve, 'trades': trades}


def run(output):
    import pandas as pd
    import strategy_workshop as W
    source = W.dataset()
    grouped = {}
    for row in source['bars']:
        grouped.setdefault(row['timestamp'][:10], []).append(row['timestamp'][11:16])
    complete = sorted(day for day, times in grouped.items() if min(times) <= '09:45' and max(times) >= '15:15')
    if len(complete) < 30:
        raise ValueError('Need at least 30 complete sessions for a separated development/holdout comparison')
    split = len(complete) - max(10, len(complete) // 3)
    windows = {'development': complete[:split], 'holdout': complete[split:]}
    results = {}
    with tempfile.TemporaryDirectory(prefix='league-exit-research-') as temp:
        data_path = Path(temp) / 'observed.json'
        data_path.write_text(json.dumps(source, allow_nan=False))
        for window, dates in windows.items():
            results[window] = []
            for mode in VARIANTS:
                payload = {'data': str(data_path), 'mode': mode, 'sessions': dates}
                child = subprocess.run([sys.executable, '-m', 'research.exit_policy_comparison', '--worker'],
                                       input=json.dumps(payload), capture_output=True, text=True,
                                       timeout=120, cwd=Path(__file__).resolve().parents[1])
                if child.returncode:
                    raise RuntimeError('Isolated research replay failed: ' + child.stderr[-1500:])
                results[window].append(json.loads(child.stdout))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'mode': 'isolated_hedged_research', 'source_archive_sha256':
                'e370aa83317920dbce6f9230d661fea2f069859d04c68b05112fafbc74de1695',
                'policy_promoted': False, 'broker_orders_submitted': False,
                'fixed_parameters': {'basket_stop_points': 30, 'basket_stop_credit_fraction': .30,
                                     'trail_activation_credit_fraction': .25,
                                     'trail_distance_credit_fraction': .15, 'daily_mtm_fraction': .01},
                'period': [complete[0], complete[-1]], 'partition_sessions': windows,
                'results': results, 'assumptions': [
                    'Independent hedged adaptations of exit ideas; not replicas of the naked source strategies.',
                    'Existing 09:45-14:30 entries, regime/trigger filters and risk sizing are unchanged.',
                    'Fixed/percentage/trailing rules close the complete hedged position, never an isolated leg.',
                    'Underlying observations and modelled option fills; no observed option-chain validation.',
                    'Fixed predeclared parameters, no search or automatic promotion; short holdout is exploratory.',
                    'Same-bar model fills and five-minute observations cannot establish tick-level stop execution.',
                    '1% MTM boundary is a trigger, not guaranteed maximum loss or profit; it can be overshot.']}
    (output / 'comparison.json').write_text(json.dumps(evidence, indent=2, allow_nan=False, default=str) + '\n')
    rows = [{k: v for k, v in r.items() if k not in ('trades', 'curve_per_lot')} | {'partition': window}
            for window, variants in results.items() for r in variants]
    pd.DataFrame(rows).to_csv(output / 'comparison.csv', index=False)
    # Compatible with the dashboard's existing Import report action.
    variants = results['holdout']
    imported = {'label': 'ZIP-inspired hedged exit policies - holdout', 'algorithm': 'exit_policy_research',
                'period': windows['holdout'][0] + ' to ' + windows['holdout'][-1],
                'lot_size': source['config']['LOT_SIZE'], 'sessions': len(windows['holdout']),
                'summary': [{'strategy': r['policy'], 'trades': r['trades_count'],
                             'total_rs': r['net_per_lot_sum_rs'], 'win_rate_%': r['win_rate_pct']} for r in variants],
                'equity': {r['policy']: r['curve_per_lot'] for r in variants},
                'trades': [{'strategy': r['policy'], 'structure': t['strategy'], 'entry': t['entry'],
                            'exit': t['exit'], 'pnl_rs': t['net_pnl_rs'] / t['lots'],
                            'lots': t['lots'], 'exit_reason': t['exit_reason']} for r in variants for t in r['trades']],
                'evaluation': [], 'assumptions': evidence['assumptions']}
    (output / 'dashboard-report.json').write_text(json.dumps(imported, allow_nan=False) + '\n')
    lines = ['# Hedged exit-policy comparison', '',
             'Independent research adaptations of ideas in the supplied archive. No broker orders or active-paper-account changes.', '',
             f'Period: {complete[0]} to {complete[-1]}. Development: {len(windows["development"])} complete sessions; holdout: {len(windows["holdout"])}.', '',
             'Each partition starts a separate Rs 500,000 virtual account. Values below include model fees/slippage and position sizing.', '',
             '| Holdout policy | Trades | Virtual account P&L (Rs) | Marked max drawdown (Rs) |',
             '| --- | ---: | ---: | ---: |']
    for r in variants:
        lines.append(f'| {r["label"]} | {r["trades_count"]} | {r["net_account_pnl_rs"]:.2f} | {r["marked_max_drawdown_rs"]:.2f} |')
    lines += ['', 'No automatic selection or promotion is made. A short, model-priced comparison does not validate a trading edge.', '',
              *['- ' + text for text in evidence['assumptions']], '',
              'Import `dashboard-report.json` using the existing dashboard Import report action to compare per-lot curves. Account P&L above is risk-sized and is not the same unit as those per-lot curves.']
    (output / 'summary.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'output': str(output), 'period': evidence['period'], 'summary': rows}, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/research/zip-exit-policies'))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        value = json.loads(sys.stdin.read())
        print(json.dumps(worker(json.loads(Path(value['data']).read_text()), value['mode'], value['sessions']), allow_nan=False, default=str))
    else:
        run(args.output)
