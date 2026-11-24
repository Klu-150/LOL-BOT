"""Isolated high-risk virtual account. Never used by the baseline interpreter."""
import hashlib
import json
from pathlib import Path

POLICY = {
    'id': 'adaptive25', 'label': 'Adaptive 25% risk experiment',
    'initial_capital': 500000, 'risk_fraction': .25, 'daily_loss_fraction': .25,
    'max_drawdown': .30, 'max_lots': 100, 'max_entries': 6,
    'cooldown_minutes': 5, 'target_fraction': .25, 'confirmation_bars': 2,
    'paper_only': True,
}
DB_NAME = 'intraday_experiment25.sqlite3'
CONTROL_NAME = 'experiment25-control.json'
STATUS_NAME = 'experiment25-runtime.json'


def install_policy():
    """Call only in a dedicated child process, never in the HTTP interpreter."""
    import config as C
    import intraday_engine as E
    import intraday_paper as P
    import strategies as ST
    C.RISK_PER_TRADE = POLICY['risk_fraction']
    C.INTRADAY_DAILY_LOSS_LIMIT = POLICY['daily_loss_fraction']
    C.MAX_ACCOUNT_DRAWDOWN = POLICY['max_drawdown']
    C.MAX_LOTS = POLICY['max_lots']
    C.INTRADAY_MAX_TRADES = POLICY['max_entries']
    C.INTRADAY_COOLDOWN_MINUTES = POLICY['cooldown_minutes']
    original_step, original_fingerprint = E.step, P.fingerprint
    module_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    P.fingerprint = lambda: {**original_fingerprint(), 'paper_experiment.py': module_hash}

    def step(state, row, ts, allow_entry=True):
        pick = E.decision(row)
        previous = state.get('routing_candidate')
        count = state.get('routing_confirmation', 0) + 1 if pick.strategy and pick.strategy == previous else int(bool(pick.strategy))
        if state.get('routing_day') != str(ts.date()):
            count = int(bool(pick.strategy))
        state.update(routing_candidate=pick.strategy, routing_confirmation=count, routing_day=str(ts.date()))
        position = state.get('position')
        switch = False
        if position and pick.strategy and pick.strategy != position['strategy'] and count >= POLICY['confirmation_bars']:
            # A replacement must qualify under the existing quote and 5m trigger filters.
            from risk import entry_quote, entry_filter
            years = max((E.expiry_timestamp(ts)-ts).total_seconds(), 60)/(365*86400)
            quote = entry_quote(pick.strategy, float(row.Close), years, float(row.VIX)/100)
            trigger = (not pick.strategy.startswith(('bull_', 'bear_')) or
                       pick.strategy.startswith('bull_') and row.Close > row.trigger_fast >= row.trigger_slow or
                       pick.strategy.startswith('bear_') and row.Close < row.trigger_fast <= row.trigger_slow)
            # Reserve against marked equity after closing this position, including fees.
            marked_equity = state['equity'] + E.mark(position, row, ts)['gross_rs'] - E.mark(position, row, ts)['exit_charges_rs']
            daily_remaining = state['session_equity'] * C.INTRADAY_DAILY_LOSS_LIMIT + marked_equity - state['session_equity']
            affordable = min(marked_equity * C.RISK_PER_TRADE, daily_remaining) >= quote['risk_estimate_rs']
            eligible = (allow_entry and C.INTRADAY_ENTRY_START <= ts.strftime('%H:%M') <= C.INTRADAY_ENTRY_END
                        and not state['halted'] and state['daily_entries'] < C.INTRADAY_MAX_TRADES
                        and marked_equity > state['peak_equity'] * (1-C.MAX_ACCOUNT_DRAWDOWN))
            switch = bool(eligible and affordable and trigger and entry_filter(pick.strategy, quote, 'adaptive_regime') is None)
        original_exit = ST.exit_signal

        def exit_signal(name, points, entry_net):
            reason = original_exit(name, points, entry_net)
            if reason and reason != 'take_profit':
                return reason
            mark = state['position']['mark']
            basis = -entry_net if ST.KIND[name] == 'credit' else C.SPREAD_WIDTH-entry_net
            target = max(0, basis) * C.LOT_SIZE * state['position']['lots'] * POLICY['target_fraction']
            if target > 0 and mark['net_pnl_rs'] >= target:
                return 'experiment_net_take_profit'
            return 'confirmed_structure_change' if switch else None

        ST.exit_signal = exit_signal
        try:
            event, closed = original_step(state, row, ts, allow_entry=allow_entry)
        finally:
            ST.exit_signal = original_exit
        event.update(profile=POLICY['id'], confirmation_bars=count,
                     active_strategy=state['position']['strategy'] if state.get('position') else None)
        if state.get('position'):
            event['open_net_pnl_rs'] = state['position']['mark']['net_pnl_rs']
        if event['action'] == 'open':
            pos=state['position']
            event.update(risk_per_lot_rs=pos['risk_estimate_rs'],reserved_risk_rs=pos['lots']*pos['risk_estimate_rs'])
        return event, closed

    E.step = step


def worker(directory):
    import fcntl
    import signal
    import threading
    import auto_trader as A
    import intraday_paper as P
    import ledger_store as L
    from operations import atomic_json
    install_policy()
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    db=directory/DB_NAME
    A.STATUS_FILE=directory/STATUS_NAME
    A.MIGRATION_FILE=directory/'experiment25-migration-guard.json'
    control=directory/CONTROL_NAME
    lock=(directory/'experiment25-control.lock').open('a')
    exclusive=(directory/'experiment25-worker.lock').open('a')
    fcntl.flock(exclusive,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not db.exists():
        P.initialise(db,POLICY['initial_capital'],A.feed.load())
    L.migrate(db)
    trader=A.AutoTrader(db=db)
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_:stop.set())
    try:
        while not stop.is_set():
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                value=json.loads(control.read_text()) if control.exists() else {'enabled':False}
                if type(value.get('enabled')) is not bool:
                    raise ValueError('Invalid experiment control state')
                trader.entries_enabled=value['enabled']
                result=trader.cycle(refresh=False)
                atomic_json(A.STATUS_FILE,{**result,'profile':POLICY,'source':'shared observed feed; separate virtual ledger'})
            finally:
                fcntl.flock(lock,fcntl.LOCK_UN)
            stop.wait(15)
    finally:
        trader.entries_enabled=False
        lock.close();exclusive.close()


def backtest(profile, output):
    import intraday_engine as E
    import intraday_feed as F
    from intraday_backtest import simulate
    if profile == 'adaptive25':
        install_policy()
    bars=F.load()
    state,events,trades,incomplete=simulate(E.features(bars),500000)
    result={'profile':profile,'initial_capital':500000,'ending_equity':state['equity'],
        'net_pnl_rs':state['equity']-500000,'trades':trades,'events':events,
        'incomplete_sessions_excluded':incomplete,'halted':state['halted'],
        'assumptions':['Modelled options/fills; no observed option-chain or broker execution validation.',
                       'No optimization; high exposure changes loss size and does not establish an edge.']}
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False,default=str)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('trades','events')},default=str))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('worker');p.add_argument('--state-dir',type=Path,required=True)
    p=sub.add_parser('backtest');p.add_argument('--profile',choices=['baseline','adaptive25'],required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='worker':worker(args.state_dir)
    else:backtest(args.profile,args.output)
