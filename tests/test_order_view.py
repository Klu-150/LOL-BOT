from copy import deepcopy
from order_view import order_book


def position(status='open'):
    return {'id': 1, 'entry_date': '2026-11-16T10:00:00+05:30', 'exit_date': '2026-11-16T10:30:00+05:30',
            'strategy': 'bull_put_spread', 'lots': 2, 'expiry': '2026-11-17T15:30:00+05:30', 'status': status,
            'entry': {'legs': [{'cp': 'P', 'K': 24900, 'qty': -1}, {'cp': 'P', 'K': 24800, 'qty': 1}],
                      'fills': [55.25, 30.5]},
            'exit': {'exit_fills': [42.0, 22.0]}}


def test_open_orders_match_stored_buy_sell_legs_and_prices():
    paper={'start_date':'2026-11-15','trades':[position()]}
    before=deepcopy(paper)
    orders,warnings=order_book(paper)
    assert not warnings and len(orders)==2
    by_strike={o['strike']:o for o in orders}
    assert by_strike[24900]['side']=='SELL' and by_strike[24900]['fill_price']==55.25
    assert by_strike[24800]['side']=='BUY' and by_strike[24800]['fill_price']==30.5
    assert all(o['phase']=='OPEN' and o['lots']==2 and o['status']=='MODELLED_FILL' for o in orders)
    assert paper==before


def test_close_orders_reverse_entry_sides_and_keep_stable_open_ids():
    opened,_=order_book({'start_date':'2026-11-15','trades':[position()]})
    closed,_=order_book({'start_date':'2026-11-15','trades':[position('closed')]})
    assert len(closed)==4
    assert {o['order_id'] for o in opened}=={o['order_id'] for o in closed if o['phase']=='OPEN'}
    exits={o['strike']:o for o in closed if o['phase']=='CLOSE'}
    assert exits[24900]['side']=='BUY' and exits[24900]['fill_price']==42
    assert exits[24800]['side']=='SELL' and exits[24800]['fill_price']==22
    assert len({o['order_id'] for o in closed})==4


def test_missing_exit_fills_are_not_invented():
    trade=position('closed');trade['exit']={}
    orders,warnings=order_book({'trades':[trade]})
    assert len(orders)==2 and all(o['phase']=='OPEN' for o in orders)
    assert any('no orders invented' in warning for warning in warnings)
    assert order_book({'trades':[]})==([],[])


def test_condor_displays_all_four_legs_each_side_of_round_trip():
    trade=position('closed')
    trade['entry']['legs'] += [{'cp':'C','K':25100,'qty':-1},{'cp':'C','K':25200,'qty':1}]
    trade['entry']['fills'] += [50.,25.]
    trade['exit']['exit_fills'] += [30.,12.]
    orders,warnings=order_book({'trades':[trade]})
    assert len(orders)==8 and not warnings
    assert sum(o['side']=='BUY' for o in orders)==4
    assert sum(o['side']=='SELL' for o in orders)==4
