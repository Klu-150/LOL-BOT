from copy import deepcopy
import pytest
from research.option_quotes import research_fill


def fixture():
    common={'timestamp':'2026-11-23T10:00:00+05:30','lot_size':65,'bid_qty':650,'ask_qty':650}
    quotes={'short':dict(common,bid=100,ask=102),'hedge':dict(common,bid=49,ask=51)}
    legs=[{'contract':'short','side':'SELL','lots':1},{'contract':'hedge','side':'BUY','lots':1}]
    return quotes,legs


def fill(quotes,legs):
    return research_fill(quotes,legs,'2026-11-23T10:00:10+05:30',source='broker_export',fees_rs=40)


def test_fill_uses_bid_for_sales_ask_for_purchases_and_supplied_contract_size():
    q,l=fixture();r=fill(q,l)
    assert r['gross_cashflow_rs']==65*(100-51)
    assert r['net_cashflow_rs']==65*(100-51)-40
    assert not r['orders_submitted'] and not r['execution_guaranteed']
    q['short']['lot_size']=q['hedge']['lot_size']=50
    assert fill(q,l)['gross_cashflow_rs']==50*(100-51)


@pytest.mark.parametrize('field,value',[('timestamp','2026-11-23T10:01:00+05:30'),('timestamp','2026-11-23T09:59:00+05:30'),('bid',200),('bid',float('nan')),('ask_qty',0),('lot_size',0)])
def test_bad_quotes_are_rejected(field,value):
    q,l=fixture();q['hedge'][field]=value
    with pytest.raises(ValueError):fill(q,l)


def test_fake_provenance_and_asynchronous_spread_are_rejected():
    q,l=fixture()
    with pytest.raises(ValueError):research_fill(q,l,'2026-11-23T10:00:10+05:30',source='synthetic',fees_rs=0)
    q['hedge']['timestamp']='2026-11-23T10:00:09+05:30'
    with pytest.raises(ValueError):fill(q,l)
