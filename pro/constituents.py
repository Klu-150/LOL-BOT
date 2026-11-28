"""Live Nifty 50 and Sensex 30 constituent board, plus a per-company detail view.

Lists: data/indices/nifty50.csv (official NSE ind_nifty50list.csv) and
data/indices/sensex30.csv (BSE Sensex members, from public listings; reviewed
28 Nov 2026). Index membership changes twice a year: refresh the CSVs then.
Prices: public Yahoo research data for the NSE listing (delayed, unofficial).
"""
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import threading
import time
import urllib.parse
from zoneinfo import ZoneInfo

from data import ROOT
from feed_transport import transport

ZONE = ZoneInfo("Asia/Kolkata")
INDEX_DIR = ROOT / "data" / "indices"
INDICES = {"nifty50": {"name": "Nifty 50", "yahoo": "^NSEI", "file": "nifty50.csv"},
           "sensex30": {"name": "Sensex", "yahoo": "^BSESN", "file": "sensex30.csv"}}


def load_lists():
    members, info = {}, {}
    for key, idx in INDICES.items():
        with open(INDEX_DIR / idx["file"], newline="") as f:
            rows = list(csv.DictReader(f))
        members[key] = [r["symbol"] for r in rows]
        for r in rows:
            info.setdefault(r["symbol"], {"symbol": r["symbol"], "name": r["name"], "industry": r["industry"]})
    return members, info


def _url(yahoo_symbol, rng, interval):
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol, safe='')}"
            f"?range={rng}&interval={interval}")


def _chart(yahoo_symbol, rng, interval, key=None):
    body = transport.fetch(_url(yahoo_symbol, rng, interval), key or yahoo_symbol)
    result = (body.get("chart") or {}).get("result")
    if not result:
        raise ValueError(f"no data for {yahoo_symbol}")
    r = result[0]
    if r["meta"].get("symbol") != yahoo_symbol:
        raise ValueError("unexpected instrument returned")
    closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    points = [(t, c) for t, c in zip(r.get("timestamp") or [], closes) if c is not None]
    return r["meta"], points


def _round(x, d=2):
    return None if x is None else round(float(x), d)


def _quote(meta, points, max_points=48):
    price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
    step = max(1, -(-len(points) // max_points))  # ceil
    spark = [_round(c) for _, c in points[::step]]
    if points and (not spark or spark[-1] != _round(points[-1][1])):
        spark.append(_round(points[-1][1]))
    t = meta.get("regularMarketTime")
    return {"price": _round(price), "prev_close": _round(prev),
            "change": _round(price - prev) if price is not None and prev else None,
            "change_pct": _round(100 * (price / prev - 1)) if price is not None and prev else None,
            "high": _round(meta.get("regularMarketDayHigh")), "low": _round(meta.get("regularMarketDayLow")),
            "volume": meta.get("regularMarketVolume"),
            "w52_high": _round(meta.get("fiftyTwoWeekHigh")), "w52_low": _round(meta.get("fiftyTwoWeekLow")),
            "time": datetime.fromtimestamp(t, ZONE).isoformat() if t else None, "spark": spark}


class IndexBoard:
    def __init__(self):
        self.members, self.info = load_lists()
        self.quotes, self.indices, self.errors, self.updated = {}, {}, {}, None
        self._lock, self._detail = threading.Lock(), {}

    def refresh(self):
        symbols = sorted(self.info)
        errors, quotes, indices = {}, {}, {}

        def stock(sym):
            return sym, _quote(*_chart(sym + ".NS", "1d", "5m"))

        def index(key):
            return key, _quote(*_chart(INDICES[key]["yahoo"], "1d", "5m"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [pool.submit(stock, s) for s in symbols] + [pool.submit(index, k) for k in INDICES]
            for job in jobs:
                try:
                    key, q = job.result()
                except Exception as exc:
                    errors[str(exc)[:60]] = errors.get(str(exc)[:60], 0) + 1
                    continue
                (indices if key in INDICES else quotes)[key] = q
        with self._lock:
            self.quotes.update(quotes)
            self.indices.update(indices)
            self.errors, self.updated = errors, datetime.now(ZONE).isoformat()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            out = {"updated": self.updated, "errors": dict(self.errors), "indices": {}}
            stocks = []
            for sym, meta in self.info.items():
                q = self.quotes.get(sym)
                if q:
                    stocks.append({**meta, **q, "in": [k for k in INDICES if sym in self.members[k]]})
            out["stocks"] = sorted(stocks, key=lambda s: s["name"])
            for key, idx in INDICES.items():
                members = [s for s in stocks if key in s["in"] and s["change_pct"] is not None]
                up = [s for s in members if s["change_pct"] > 0]
                ranked = sorted(members, key=lambda s: s["change_pct"])
                out["indices"][key] = {"name": idx["name"], **(self.indices.get(key) or {}),
                                       "members": len(self.members[key]), "advancing": len(up),
                                       "declining": sum(1 for s in members if s["change_pct"] < 0),
                                       "gainers": [s["symbol"] for s in ranked[::-1][:3]],
                                       "losers": [s["symbol"] for s in ranked[:3]]}
            return out

    def detail(self, symbol, max_age=15):
        """Full intraday (1-minute) and 1-year daily history for one constituent; cached briefly."""
        if symbol not in self.info:
            raise KeyError(symbol)
        cached = self._detail.get(symbol)
        if cached and time.monotonic() - cached[0] < max_age:
            return cached[1]
        y = symbol + ".NS"
        meta, intraday = _chart(y, "1d", "1m", key=y + ":detail")
        _, daily = _chart(y, "1y", "1d", key=y + ":daily")
        out = {**self.info[symbol], **_quote(meta, intraday), "in": [k for k in INDICES if symbol in self.members[k]],
               "open": _round(intraday[0][1]) if intraday else None,
               "intraday": [{"t": datetime.fromtimestamp(t, ZONE).strftime("%H:%M"), "c": _round(c)} for t, c in intraday],
               "daily": [{"d": datetime.fromtimestamp(t, ZONE).strftime("%Y-%m-%d"), "c": _round(c)} for t, c in daily]}
        out.pop("spark", None)
        self._detail[symbol] = (time.monotonic(), out)
        return out
