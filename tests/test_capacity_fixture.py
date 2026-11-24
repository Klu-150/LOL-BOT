import intraday_paper as P
from tools.capacity_fixture import synthetic_closed_trade


def test_capacity_trade_is_self_contained_and_hedged_without_an_account(tmp_path,monkeypatch):
    path=tmp_path/'private-account-does-not-exist.sqlite3'
    monkeypatch.setattr(P,'DEFAULT_DB',path)
    trade=synthetic_closed_trade()
    assert not path.exists()
    assert trade['exit_reason']=='session_square_off'
    assert len(trade['legs'])==4
    assert sum(leg['qty']>0 for leg in trade['legs'])==2
    assert trade['entry'][:10]==trade['exit'][:10]
