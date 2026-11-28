"""Live market snapshot: Nifty, India VIX, today's 5-minute path, and heavyweight stocks.

Public Yahoo research data (delayed, unofficial). Read-only; no orders.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import threading
from zoneinfo import ZoneInfo

import intraday_feed
from exchange_calendar import session_status
from pro.news import COMPANIES

ZONE = ZoneInfo("Asia/Kolkata")


def _quote(symbol):
    bars = intraday_feed.chart(symbol, "1d", "5d")
    last, prev = bars.iloc[-1], bars.iloc[-2]
    return {"symbol": symbol, "price": round(float(last.Close), 2), "prev_close": round(float(prev.Close), 2),
            "change_pct": round(100 * (float(last.Close) / float(prev.Close) - 1), 2),
            "high": round(float(last.High), 2), "low": round(float(last.Low), 2),
            "as_of": str(bars.index[-1].tz_convert(ZONE).date())}


def _intraday(symbol):
    bars = intraday_feed.chart(symbol, "5m", "5d")
    day = bars.index[-1].date()
    today = bars.loc[[ts.date() == day for ts in bars.index]]
    return [{"t": ts.strftime("%H:%M"), "c": round(float(c), 2)} for ts, c in today.Close.items()]


class MarketDesk:
    def __init__(self):
        self.data, self.errors, self.updated, self._lock = {}, {}, None, threading.Lock()

    def refresh(self):
        jobs, errors, data = {}, {}, {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            # One request per instrument at a time (the transport's circuit breaker is per symbol).
            jobs["nifty"] = pool.submit(_quote, "^NSEI")
            jobs["vix"] = pool.submit(_quote, "^INDIAVIX")
            for sym, name, _ in COMPANIES:
                jobs[sym] = pool.submit(_quote, sym)
        try:
            data["nifty_intraday"] = _intraday("^NSEI")
        except Exception as exc:
            errors["nifty_intraday"] = str(exc)[:200]
        stocks = []
        for key, job in jobs.items():
            try:
                value = job.result()
            except Exception as exc:
                errors[key] = str(exc)[:200]
                continue
            if key.endswith(".NS"):
                value["name"] = next(n for s, n, _ in COMPANIES if s == key)
                stocks.append(value)
            else:
                data[key] = value
        if stocks:
            up = sum(1 for s in stocks if s["change_pct"] > 0)
            data["stocks"] = sorted(stocks, key=lambda s: s["change_pct"], reverse=True)
            data["breadth"] = {"advancing": up, "declining": len(stocks) - up, "total": len(stocks)}
        now = datetime.now(ZONE)
        data["session"] = session_status(now)
        with self._lock:
            # Keep the last good values when a refresh partially fails.
            self.data = {**self.data, **data}
            self.errors, self.updated = errors, now.isoformat()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return {**self.data, "errors": dict(self.errors), "updated": self.updated}
