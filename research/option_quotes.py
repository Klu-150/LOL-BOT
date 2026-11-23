"""Conservative research fills from observed bid/ask exports, never a broker API.

The caller supplies quote provenance and actual contract lot sizes. Quotes remain
separate from the model-priced live paper ledger until a feed is independently
validated. This adapter refuses stale, future, crossed or illiquid observations.
"""
from datetime import datetime
import math


def research_fill(quotes, legs, decision_at, *, source, fees_rs):
    if source not in ('broker_export', 'exchange_export'):
        raise ValueError('Require an observed broker/exchange export; synthetic prices are not accepted')
    now=datetime.fromisoformat(decision_at) if isinstance(decision_at,str) else decision_at
    if now.tzinfo is None or not math.isfinite(fees_rs) or fees_rs<0:
        raise ValueError('Use a timezone-aware decision and nonnegative total fees')
    if not 2<=len(legs)<=4:
        raise ValueError('Use two to four hedged research legs')
    result=[];times=[];cash=0.;contracts=set()
    for leg in legs:
        contract=leg['contract'];side=leg['side'];lots=leg['lots']
        if contract in contracts or side not in ('BUY','SELL') or type(lots) is not int or lots<=0:
            raise ValueError('Unique contracts, BUY/SELL and positive integer lots are required')
        contracts.add(contract)
        quote=quotes[contract]
        stamp=datetime.fromisoformat(quote['timestamp'])
        if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=30:
            raise ValueError('Quotes must be observable at the decision, and no more than 30 seconds old')
        bid,ask=float(quote['bid']),float(quote['ask'])
        if not all(math.isfinite(x) for x in (bid,ask)) or not 0<bid<=ask:
            raise ValueError('Invalid or crossed bid/ask quote')
        if (ask-bid)/((ask+bid)/2)>.15:
            raise ValueError('Bid/ask spread exceeds the research liquidity bound')
        lot_size=quote['lot_size']
        if type(lot_size) is not int or lot_size<=0:
            raise ValueError('Supply the actual exchange contract lot size')
        quantity=lots*lot_size
        available=float(quote['ask_qty' if side=='BUY' else 'bid_qty'])
        if not math.isfinite(available) or available<quantity:
            raise ValueError('Quoted size cannot cover this research leg')
        fill=ask if side=='BUY' else bid
        cash+=(-1 if side=='BUY' else 1)*quantity*fill
        result.append({'contract':contract,'side':side,'lots':lots,'lot_size':lot_size,'quantity':quantity,'fill':fill})
        times.append(stamp)
    if (max(times)-min(times)).total_seconds()>5:
        raise ValueError('Multi-leg observations must be synchronized within five seconds')
    return {'mode':'observed_quote_research','source':source,'legs':result,'gross_cashflow_rs':cash,
            'fees_rs':fees_rs,'net_cashflow_rs':cash-fees_rs,'orders_submitted':False,
            'execution_guaranteed':False,'note':'Top-of-book research estimate; not a confirmed multi-leg fill or margin/risk check'}
