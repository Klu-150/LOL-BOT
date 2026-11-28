from datetime import date, datetime

import pytest

from pro import broker as B

ZONE = B.ZONE


class Market:
    def __init__(self):
        self.now = datetime(2026, 12, 1, 10, 0, tzinfo=ZONE)   # a Tuesday, session open
        self.px = {"RELIANCE": 1400.0, "TCS": 3000.0}
        self.spot, self.vix = 25_600.0, 15.0

    def stock(self, sym):
        return {"price": self.px.get(sym), "time": self.now.isoformat(), "prev_close": 1390.0} if sym in self.px else None

    def index(self):
        return {"spot": self.spot, "vix": self.vix, "time": self.now}


@pytest.fixture
def mk(tmp_path):
    m = Market()
    q = B.Quotes(m.stock, m.index, clock=lambda: m.now)
    m.broker = B.Broker(tmp_path / "acct.json", q, clock=lambda: m.now)
    return m


def test_market_buy_sell_updates_cash_avg_and_realised(mk):
    b = mk.broker
    o = b.place("EQ:RELIANCE", "BUY", "CNC", "MARKET", 10)
    assert o["status"] == "COMPLETE" and o["fill_price"] == pytest.approx(1400 * 1.0005)
    b.place("EQ:RELIANCE", "BUY", "CNC", "MARKET", 10)
    hold = b.snapshot()["holdings"][0]
    assert hold["qty"] == 20 and hold["avg"] == pytest.approx(1400 * 1.0005)
    mk.px["RELIANCE"] = 1500.0
    b.place("EQ:RELIANCE", "SELL", "CNC", "MARKET", 20)
    f = b.funds()
    assert f["total_pnl"] == pytest.approx(20 * (1500 * 0.9995 - 1400 * 1.0005) - f["charges"], abs=0.01)
    assert b.snapshot()["holdings"] == []


def test_rejections(mk):
    b = mk.broker
    assert b.place("EQ:RELIANCE", "BUY", "CNC", "MARKET", 1000)["status"] == "REJECTED"   # ₹14 lakh > ₹5 lakh
    with pytest.raises(ValueError, match="delivery"):
        b.place("EQ:TCS", "SELL", "CNC", "MARKET", 1)
    with pytest.raises(ValueError, match="lot size"):
        b.place(B.option_id(date(2026, 12, 29), 25600, "CE"), "BUY", "NRML", "MARKET", 10)
    with pytest.raises(ValueError, match="Unknown instrument"):
        b.place("EQ:", "BUY", "CNC", "MARKET", 1)


def test_limit_and_stop_orders_wait_for_price(mk):
    b = mk.broker
    lim = b.place("EQ:TCS", "BUY", "MIS", "LIMIT", 5, price=2950)
    assert lim["status"] == "OPEN"
    sl = b.place("EQ:TCS", "BUY", "MIS", "SL-M", 5, trigger=3100)
    assert sl["status"] == "TRIGGER_PENDING"
    mk.px["TCS"] = 2940.0
    b.process()
    assert lim["status"] == "COMPLETE" and lim["fill_price"] <= 2950
    mk.px["TCS"] = 3105.0
    b.process()
    assert sl["status"] == "COMPLETE"
    b.cancel(b.place("EQ:TCS", "SELL", "MIS", "LIMIT", 1, price=9999)["id"])
    assert b.snapshot()["orders"][0]["status"] == "CANCELLED"


def test_after_hours_order_waits_for_next_session_and_stale_quotes_never_fill(mk):
    b = mk.broker
    mk.now = datetime(2026, 12, 1, 18, 0, tzinfo=ZONE)
    o = b.place("EQ:RELIANCE", "BUY", "CNC", "MARKET", 1)
    assert o["status"] == "AMO"
    mk.now = datetime(2026, 12, 2, 9, 20, tzinfo=ZONE)
    stale = b.quotes.stock_quote
    b.quotes.stock_quote = lambda s: {**stale(s), "time": "2026-12-01T15:29:00+05:30"}
    b.process()
    assert o["status"] == "AMO"            # yesterday's price is never used for a fill
    b.quotes.stock_quote = stale
    b.process()
    assert o["status"] == "COMPLETE"


def test_intraday_square_off_at_1520(mk):
    b = mk.broker
    b.place("EQ:TCS", "SELL", "MIS", "MARKET", 10)         # intraday short
    assert b.funds()["margin_used"] > 0
    mk.now = mk.now.replace(hour=15, minute=21)
    b.process()
    snap = b.snapshot()
    assert all(p["qty"] == 0 for p in snap["positions"]) and snap["orders"][0]["tag"] == "auto_square_off"


def test_hedged_spread_needs_less_margin_than_naked_short(mk):
    b = mk.broker
    exp = date(2026, 12, 29)
    short = B.option_id(exp, 25300, "PE")
    b.place(short, "SELL", "NRML", "MARKET", 65)
    naked = b.funds()["margin_used"]
    b.place(B.option_id(exp, 25000, "PE"), "BUY", "NRML", "MARKET", 65)
    hedged = b.funds()["margin_used"]
    assert naked == pytest.approx(65 * 25_600 * B.SHORT_OPTION_MARGIN)
    assert hedged == pytest.approx(300 * 65)                # max loss of the 300-point spread


def test_options_settle_at_expiry(mk):
    b = mk.broker
    inst = B.option_id(date(2026, 12, 1), 25500, "CE")      # expires today 15:30
    b.place(inst, "BUY", "NRML", "MARKET", 65)
    mk.spot = 25_700.0
    mk.now = mk.now.replace(hour=15, minute=31)
    b.process()
    trade = b.snapshot()["trades"][0]
    assert trade["tag"] == "expiry_settlement" and trade["price"] == pytest.approx(200.0)


def test_chain_and_reset(mk):
    b = mk.broker
    ch = b.chain()
    assert ch["atm"] == 25600 and len(ch["rows"]) == 25 and ch["model"] is True
    row = next(r for r in ch["rows"] if r["strike"] == 25600)
    assert row["CE"]["bid"] < row["CE"]["ltp"] < row["CE"]["ask"] and 0.3 < row["CE"]["delta"] < 0.7
    assert b.reset(1_000_000)["funds"]["cash"] == 1_000_000
    with pytest.raises(ValueError):
        b.reset(5)
