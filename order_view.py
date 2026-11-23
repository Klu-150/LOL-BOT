"""Read-only per-leg paper order view derived solely from persisted fills."""
import hashlib
import math


def order_book(paper):
    orders, warnings = [], []
    account = paper.get('started_at') or paper.get('start_date') or ''
    for trade in paper.get('trades', []):
        entry, exit_data = trade.get('entry', {}), trade.get('exit', {})
        legs = entry.get('legs', [])
        entry_time = trade.get('entry_date') or entry.get('entry')
        strategy = trade.get('strategy', '')
        key = hashlib.sha256(f'{account}|{entry_time}|{strategy}'.encode()).hexdigest()[:12].upper()
        lots = trade.get('lots', 0)
        if not isinstance(lots, (int, float)) or not math.isfinite(lots) or lots <= 0:
            warnings.append(f'{key}: no positive lot count recorded')
            continue
        phases = [('OPEN', entry_time, entry.get('fills', []))]
        if trade.get('status') == 'closed':
            phases.append(('CLOSE', trade.get('exit_date'), exit_data.get('exit_fills', [])))
        for phase, timestamp, fills in phases:
            if not legs or len(fills) != len(legs) or not timestamp:
                warnings.append(f'{key}: {phase.lower()} leg fills unavailable; no orders invented')
                continue
            for index, (leg, fill) in enumerate(zip(legs, fills), 1):
                if not isinstance(fill, (int, float)) or not math.isfinite(fill) or fill < 0:
                    warnings.append(f'{key}: invalid {phase.lower()} fill {index}')
                    continue
                qty = leg.get('qty', 0)
                if not isinstance(qty, (int, float)) or not math.isfinite(qty) or not qty:
                    warnings.append(f'{key}: invalid leg quantity {index}')
                    continue
                buy = qty > 0 if phase == 'OPEN' else qty < 0
                orders.append({'order_id': f'PAPER-{key}-{phase}-{index}', 'position_id': key,
                               'mode': 'paper', 'status': 'MODELLED_FILL', 'phase': phase,
                               'side': 'BUY' if buy else 'SELL', 'instrument': 'NIFTY',
                               'option_type': 'CE' if leg.get('cp') == 'C' else 'PE',
                               'strike': leg.get('K'), 'expiry': trade.get('expiry'),
                               'filled_at': timestamp, 'lots': abs(qty) * lots,
                               'fill_price': float(fill), 'strategy': strategy})
    return sorted(orders, key=lambda row: (row['filled_at'], row['order_id']), reverse=True), warnings
