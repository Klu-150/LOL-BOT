from datetime import date, datetime, timedelta, timezone
import io
import json
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest

from pro import alerts, assistant, daily, news, options_paper, trial


# ----------------------------------------------------------------- news
@pytest.mark.parametrize("title,sentiment", [
    ("Sensex crashes 1,000 points as war fears grip markets", "negative"),
    ("Sensex, Nifty end four-week rally as rupee weakens", "negative"),
    ("RBI cuts repo rate; Nifty rallies to record high", "positive"),
    ("Nifty ends flat ahead of expiry", "neutral"),
])
def test_headline_sentiment(title, sentiment):
    assert news._score(title)[0] == sentiment


def test_company_tagging_uses_word_boundaries():
    assert news._companies("Infosys and HDFC Bank lead gains") == ["HDFC Bank", "Infosys"] or \
        set(news._companies("Infosys and HDFC Bank lead gains")) == {"HDFC Bank", "Infosys"}
    assert news._companies("Editorial on bitcoin") == []  # "itc" inside a word must not match


def test_risk_rises_with_recent_negative_macro_news():
    now = datetime.now(timezone.utc)
    item = lambda t, h=1: {"title": t, "published": (now - timedelta(hours=h)).isoformat(), **dict(zip(("sentiment", "impact", "macro"), news._score(t)))}
    calm = [item("Nifty ends flat"), item("Markets rise on strong earnings")]
    panic = [item(t) for t in ("Sensex crashes 2,000 points as war fears grip markets", "FPI outflows deepen, rupee plunges to record low",
             "Global sell-off: Nasdaq tumbles on recession fears", "Crude spikes after attack, markets plunge",
             "Nifty sinks 4%, biggest fall since 2020 as panic selling hits", "Bank stocks crash as RBI rate hike shocks market",
             "Investors lose Rs 10 lakh crore in market bloodbath", "India VIX surges 30% as war escalates, Sensex tumbles")]
    opinion = [item(t) for t in ("If a stock market crash is coming, here is the smartest move",
               "Investors must brace for deeper market corrections, warn fund managers", "Sensex, Nifty end four-week rally as rupee weakens",
               "Smallcap stocks that plunged the most in a year", "Is a crash coming?", "Gold is less volatile despite the correction")]
    assert news.risk(opinion)["level"] != "high"  # opinion pieces alone must never block trades
    assert news.risk(panic[:4])["level"] != "high"
    old_panic = [item(i["title"], 10) for i in panic]
    assert news.risk(calm)["level"] == "normal"
    assert news.risk(panic)["level"] == "high"
    assert news.risk(old_panic)["level"] == "normal"  # only the last 3 hours count


def test_rss_parsing_strips_publisher_and_rejects_bad_links(monkeypatch):
    rss = b"""<rss><channel>
      <item><title>Nifty jumps 1% - Livemint</title><link>https://example.com/a</link>
        <pubDate>Fri, 27 Nov 2026 10:00:00 GMT</pubDate><source url="x">Livemint</source></item>
      <item><title>Bad link</title><link>javascript:alert(1)</link></item>
    </channel></rss>"""
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: io.BytesIO(rss))
    items = news._fetch("Google News", "https://news.google.com/rss")
    assert [i["title"] for i in items] == ["Nifty jumps 1%"]
    assert items[0]["source"] == "Livemint" and items[0]["sentiment"] == "positive"


# --------------------------------------------------------------- options
def test_monthly_expiry_is_last_tuesday():
    assert options_paper.monthly_expiry(date(2026, 12, 3)) == date(2026, 12, 29)
    assert options_paper.monthly_expiry(date(2027, 2, 1)) == date(2027, 2, 23)
    d = date(2026, 12, 10)
    assert (options_paper.pick_expiry(d) - d).days >= options_paper.MIN_DTE


def test_spread_is_defined_risk_and_sized_to_budget():
    pos = options_paper.open_spread(500_000, 25_600, date(2026, 11, 30), 16.5)
    short, long = pos["legs"]
    assert short["qty"] == -1 and long["qty"] == 1 and short["K"] - long["K"] == options_paper.WIDTH
    assert short["K"] < 25_600 and pos["credit_pts"] > 0
    assert pos["max_loss_rs"] <= 500_000 * options_paper.RISK_PER_TRADE
    same = options_paper.mark(pos, 25_600, date(2026, 11, 30), 16.5)
    assert -3_000 < same["pnl_rs"] < 0  # closing immediately costs only slippage and charges
    assert options_paper.mark(pos, 26_200, date(2026, 12, 14), 14.0)["pnl_rs"] > 0
    assert options_paper.mark(pos, 24_000, date(2026, 12, 14), 22.0)["pnl_rs"] >= -pos["max_loss_rs"] - 1


def _frame(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame({"Open": [r[1] for r in rows], "Close": [r[2] for r in rows], "VIX": [16.0] * len(rows)}, index=idx)


def test_options_ledger_opens_rolls_and_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "OPTIONS_LEDGER", tmp_path / "opt.json")
    res = lambda d, a: {"as_of_bar": d, "action": a, "generated_at": d}
    days = pd.bdate_range("2026-12-01", "2027-01-20")
    rows = [(str(d.date()), 25_000 + 10 * i, 25_005 + 10 * i) for i, d in enumerate(days)]
    led = daily.update_options_ledger(res(rows[0][0], "BUY_AT_NEXT_OPEN"), _frame(rows[:1]))
    assert led["pending"] == "OPEN" and not led["position"]
    led = daily.update_options_ledger(res(rows[1][0], "HOLD"), _frame(rows[:2]))
    assert led["position"]["opened"] == rows[1][0] and "pending" not in led
    first_expiry = led["position"]["expiry"]
    led = daily.update_options_ledger(res(rows[-2][0], "HOLD"), _frame(rows[:-1]))
    assert any(t["reason"] == "roll" for t in led["trades"]) and led["position"]["expiry"] != first_expiry
    led = daily.update_options_ledger(res(rows[-2][0], "SELL_AT_NEXT_OPEN"), _frame(rows[:-1]))
    led = daily.update_options_ledger(res(rows[-1][0], "STAND_ASIDE"), _frame(rows))
    assert led["position"] is None and led["trades"][-1]["reason"] == "engine exit"
    assert led["equity"] == pytest.approx(500_000 + led["realised_rs"])
    assert len(led["history"]) == len(rows) - 1


# ------------------------------------------------------------ trial/alerts
def test_trial_requires_time_sessions_and_trades():
    opt = {"started": "2026-11-27", "capital": 500_000, "return_pct": 0.0, "trades": [],
           "history": [{"date": "2026-11-27", "equity": 500_000, "nifty": 25_600}]}
    card = trial.scorecard(opt, [], today=date(2026, 11, 28))
    assert card["status"] == "in_progress" and not all(c["ok"] for c in card["checks"])
    assert trial.scorecard(None, [])["status"] == "not_started"


def test_alert_cooldown_dedupes(tmp_path):
    center = alerts.AlertCenter(store=tmp_path / "a.json", notify=False)
    assert center.raise_alert("k", "warning", "T", "M") is not None
    assert center.raise_alert("k", "warning", "T", "M") is None
    center.resolve("k")
    assert center.list()[0]["resolved"] is True
    reloaded = alerts.AlertCenter(store=tmp_path / "a.json", notify=False)
    assert reloaded.raise_alert("k", "warning", "T", "M") is None  # cooldown survives a restart


def test_assistant_without_credentials_answers_from_state(monkeypatch):
    monkeypatch.setattr(assistant, "configured", lambda: False)
    state = {"plan": {"regime": "uptrend", "action": "HOLD", "reason": "trend intact"},
             "options_account": {"equity": 501_234, "return_pct": 0.25, "trades": []},
             "market": {"nifty": {"price": 25_600, "change_pct": -1.0, "as_of": "2026-11-27"}, "vix": {"price": 16.5, "change_pct": 1}}}
    r = assistant.ask("How is my performance?", [], state)
    assert "₹5,01,234" in r["answer"] and r["source"].startswith("built-in")


# ---------------------------------------------------------------- server
def test_server_rejects_unauthenticated_posts(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer
    from pro import server
    engine = server.Engine(notify=False)
    engine.alerts = alerts.AlertCenter(store=tmp_path / "a.json", notify=False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.engine = engine
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        assert json.load(urllib.request.urlopen(base + "/api/session"))["mode"] == "paper"
        state = json.load(urllib.request.urlopen(base + "/api/state"))
        assert state["orders_submitted"] is False
        req = urllib.request.Request(base + "/api/run-daily", data=b"{}", method="POST",
                                     headers={"Origin": base, "X-Session-Token": "wrong"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        assert err.value.code == 403
        assert urllib.request.urlopen(base + "/").read().startswith(b"<!doctype html>")
    finally:
        httpd.shutdown()


# ------------------------------------------------------------ constituents
def test_index_lists_are_complete():
    from pro import constituents
    members, info = constituents.load_lists()
    assert len(members["nifty50"]) == 50 and len(set(members["nifty50"])) == 50
    assert len(members["sensex30"]) == 30 and set(members["sensex30"]) <= set(info)
    assert all(i["name"] and i["industry"] for i in info.values())


def test_quote_maths_and_sparkline_thinning():
    from pro import constituents
    meta = {"regularMarketPrice": 110.0, "chartPreviousClose": 100.0, "regularMarketDayHigh": 112, "regularMarketDayLow": 99,
            "regularMarketTime": 1795773550}
    q = constituents._quote(meta, [(1795770000 + 60 * i, 100 + i * 0.1) for i in range(375)])
    assert q["change"] == 10.0 and q["change_pct"] == 10.0
    assert len(q["spark"]) <= 49 and q["spark"][-1] == round(100 + 374 * 0.1, 2)


def test_board_snapshot_counts_breadth(monkeypatch):
    from pro import constituents
    board = constituents.IndexBoard()
    syms = list(board.info)
    board.quotes = {s: {"price": 10, "change_pct": 1.0 if i % 3 else -1.0, "change": 0.1, "spark": []} for i, s in enumerate(syms)}
    snap = board.snapshot()
    n = snap["indices"]["nifty50"]
    assert n["advancing"] + n["declining"] == 50 and len(snap["stocks"]) == 50
    assert snap["indices"]["sensex30"]["members"] == 30
    with pytest.raises(KeyError):
        board.detail("NOT-A-STOCK")
