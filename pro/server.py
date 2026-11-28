"""LOL Pro terminal: local web app + background engine.  python -m pro.server

Open http://127.0.0.1:8787 . Paper only: no broker connection, no real orders.
Background loops: market (60s in session), news (120s), daily decision at
15:20 IST on weekdays (plus a catch-up run at start), and a health monitor
that raises alerts (in-app, macOS notification, optional Telegram).
"""
import argparse
from datetime import date, datetime
import hashlib
import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import secrets
import threading
import time
import traceback

from data import ROOT
from exchange_calendar import HOLIDAYS, REVIEWED_YEARS
from pro import alerts, assistant, daily, live, trial
from pro.constituents import IndexBoard
from pro.market import MarketDesk, ZONE
from pro.news import NewsDesk

WEB = Path(__file__).resolve().parent / "web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8"), "/icon.svg": ("icon.svg", "image/svg+xml")}
DAILY_RUN_TIME = "15:20"
# Hosts the terminal answers to. Add private names (e.g. a Tailscale name) with LOLPRO_ALLOWED_HOSTS=a,b
ALLOWED_HOSTS = {"127.0.0.1", "localhost", *filter(None, os.environ.get("LOLPRO_ALLOWED_HOSTS", "").split(","))}
log = logging.getLogger("lolpro")


def _read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class Engine:
    def __init__(self, notify=True):
        self.market, self.news, self.alerts = MarketDesk(), NewsDesk(), alerts.AlertCenter(notify=notify)
        self.board = IndexBoard()
        self._last_board = 0.0
        self.token = secrets.token_urlsafe(24)
        self.health = {"started": datetime.now(ZONE).isoformat(), "daily": {}, "market_failures": 0, "loops": {}}
        self._job_lock, self._stop = threading.Lock(), threading.Event()
        # Market refresh and the daily job fetch the same symbols; the shared feed transport
        # allows one in-flight request per symbol, so the two never run at the same time.
        self._feed_lock = threading.Lock()
        self._last_market = self._last_news = 0.0
        self._last_action = (_read_json(live.PLAN) or {}).get("action")

    # ---------------------------------------------------------------- jobs
    def run_daily(self, include_today):
        if not self._job_lock.acquire(blocking=False):
            return {"status": "busy"}
        try:
            self.health["daily"].update(running=True, started=datetime.now(ZONE).isoformat())
            with self._feed_lock:
                result = daily.run(include_today, self.news.snapshot() if self.news.updated else None)
            self.health["daily"].update(running=False, ok=True, finished=datetime.now(ZONE).isoformat(),
                                        as_of_bar=result.get("as_of_bar"), error=None)
            if include_today:
                self.health["daily"]["last_close_run"] = date.today().isoformat()
            self.alerts.resolve("daily_failed")
            self._announce(result)
            return {"status": "ok", "plan": result}
        except Exception as exc:
            self.health["daily"].update(running=False, ok=False, error=str(exc), finished=datetime.now(ZONE).isoformat())
            log.error("daily run failed: %s", traceback.format_exc())
            self.alerts.raise_alert("daily_failed", "error", "Daily decision failed",
                                    f"The engine could not build today's plan: {exc}", cooldown_minutes=30)
            return {"status": "error", "error": str(exc)}
        finally:
            self._job_lock.release()

    def _announce(self, plan):
        action = plan.get("action")
        if action in ("BUY_AT_NEXT_OPEN", "SELL_AT_NEXT_OPEN") and action != self._last_action:
            what = "open a bull put spread" if action.startswith("BUY") else "close the open spread"
            self.alerts.raise_alert(f"action_{plan.get('as_of_bar')}_{action}", "trade", "New paper trade signal",
                                    f"The bot will {what} at the next open. {plan.get('reason', '')}", cooldown_minutes=1)
        if plan.get("vetoed_signal"):
            self.alerts.raise_alert(f"veto_{plan.get('as_of_bar')}", "warning", "Entry vetoed by news",
                                    plan.get("reason", ""), cooldown_minutes=1)
        self._last_action = action

    def refresh_market(self):
        try:
            with self._feed_lock:
                snap = self.market.refresh()
            self._last_market = time.monotonic()
            if "nifty" in snap.get("errors", {}):
                self.health["market_failures"] += 1
            else:
                self.health["market_failures"] = 0
                self.alerts.resolve("market_feed")
        except Exception as exc:
            self.health["market_failures"] += 1
            log.warning("market refresh failed: %s", exc)

    def refresh_board(self):
        try:
            with self._feed_lock:
                self.board.refresh()
            self._last_board = time.monotonic()
        except Exception as exc:
            log.warning("constituent refresh failed: %s", exc)

    def refresh_news(self):
        try:
            snap = self.news.refresh()
            self._last_news = time.monotonic()
            if snap["errors"] and len(snap["errors"]) == 4:
                self.alerts.raise_alert("news_feed", "warning", "News feeds unavailable",
                                        "All news sources failed; the news veto is not active until they recover.", 120)
            elif not snap["errors"]:
                self.alerts.resolve("news_feed")
        except Exception as exc:
            log.warning("news refresh failed: %s", exc)

    # --------------------------------------------------------------- monitor
    def monitor(self, now=None):
        now = now or datetime.now(ZONE)
        mkt, plan = self.market.snapshot(), _read_json(live.PLAN) or {}
        opt = _read_json(daily.OPTIONS_LEDGER) or {}
        in_session = bool((mkt.get("session") or {}).get("feed_window"))
        if in_session and self.health["market_failures"] >= 3:
            self.alerts.raise_alert("market_feed", "error", "Market data feed failing",
                                    "Nifty prices could not be refreshed 3 times in a row. Check the internet connection.", 30)
        nifty = (mkt.get("nifty") or {}).get("price")
        stop = (plan.get("position") or {}).get("stop")
        if in_session and nifty and stop and nifty < stop:
            self.alerts.raise_alert("stop_breach", "critical", "Nifty below the protective stop",
                                    f"Nifty {nifty:,.0f} is below the stop {stop:,.0f}. The bot will close the spread "
                                    "at the next open after today's 15:20 decision.", 120)
        pos = opt.get("position")
        if pos and pos.get("mark") and pos["mark"]["pnl_rs"] <= -0.5 * pos["max_loss_rs"]:
            self.alerts.raise_alert("spread_loss", "warning", "Spread loss above half of max loss",
                                    f"{pos['label']}: P&L ₹{pos['mark']['pnl_rs']:,.0f} of max ₹{pos['max_loss_rs']:,.0f}.", 240)
        risk = (self.news.snapshot().get("risk") or {})
        if risk.get("level") == "high":
            self.alerts.raise_alert("news_risk", "warning", "High market news risk",
                                    f"News risk {risk.get('score')}/100: new entries are paused until it eases.", 120)
        elif risk.get("level") in ("normal", "elevated"):
            self.alerts.resolve("news_risk")
        if now.weekday() < 5 and plan.get("as_of_bar"):
            age = (now.date() - date.fromisoformat(plan["as_of_bar"])).days
            if age > 4:
                self.alerts.raise_alert("stale_plan", "error", "Decision data is stale",
                                        f"The last completed bar is {plan['as_of_bar']} ({age} days old).", 240)
        if now.year not in REVIEWED_YEARS:
            self.alerts.raise_alert(f"calendar_{now.year}", "warning", f"Add NSE holidays for {now.year}",
                                    "exchange_calendar.py has no reviewed holiday list for this year; the daily job "
                                    "still runs, but holiday handling is unverified.", 24 * 60)
        if not assistant.configured():
            self.alerts.raise_alert("assistant_key", "info", "AI assistant in basic mode",
                                    "Set ANTHROPIC_API_KEY (or run `ant auth login`) to enable the Claude-powered assistant.", 7 * 24 * 60)

    def _due_daily(self, now):
        stamp = now.strftime("%H:%M")
        trading = now.weekday() < 5 and now.date().isoformat() not in HOLIDAYS
        return trading and stamp >= DAILY_RUN_TIME and self.health["daily"].get("last_close_run") != now.date().isoformat()

    def loop(self):
        now = datetime.now(ZONE)
        after_close = now.weekday() < 5 and now.strftime("%H:%M") >= DAILY_RUN_TIME
        threading.Thread(target=self.run_daily, args=(after_close,), daemon=True).start()
        while not self._stop.is_set():
            now = datetime.now(ZONE)
            in_session = bool((self.market.snapshot().get("session") or {}).get("feed_window"))
            try:
                if time.monotonic() - self._last_market > (60 if in_session else 900):
                    self.refresh_market()
                if time.monotonic() - self._last_board > (60 if in_session else 900):
                    self.refresh_board()
                if time.monotonic() - self._last_news > 120:
                    self.refresh_news()
                if self._due_daily(now):
                    threading.Thread(target=self.run_daily, args=(True,), daemon=True).start()
                self.monitor(now)
                self.health["loops"]["last_tick"] = now.isoformat()
            except Exception:
                log.error("monitor loop error: %s", traceback.format_exc())
            self._stop.wait(20)

    # ----------------------------------------------------------------- state
    def state(self, include_items=True):
        news = self.news.snapshot()
        alerts_list = self.alerts.list()
        options = _read_json(daily.OPTIONS_LEDGER)
        backtest = _read_json(ROOT / "results" / "pro" / "results.json")
        return {"now": datetime.now(ZONE).isoformat(), "mode": "paper", "orders_submitted": False,
                "plan": _read_json(live.PLAN), "options_account": options,
                "etf_account": _read_json(daily.LEDGER), "market": self.market.snapshot(),
                "daily_chart": _read_json(daily.CHART, []),
                "board": self.board.snapshot(),
                "news": {**news, "items": news["items"][:80] if include_items else []},
                "alerts": alerts_list, "trial": trial.scorecard(options, alerts_list),
                "backtest": backtest and {"period": backtest.get("period"),
                                          "adaptive": backtest.get("table", {}).get("ADAPTIVE (selector)"),
                                          "buy_and_hold": backtest.get("table", {}).get("buy_and_hold_index")},
                "health": {**self.health, "assistant": assistant.configured(), "channels": alerts.channels(),
                           "news_updated": news.get("updated"), "news_errors": news.get("errors"),
                           "market_updated": self.market.updated}}


def _short_name(name):
    """'Infosys Ltd.' -> 'Infosys' for news searches."""
    for suffix in (" Limited", " Ltd.", " Ltd", " Co."):
        name = name.replace(suffix, "")
    return name.strip()


# ------------------------------------------------------------------ login
# When LOLPRO_ACCESS_KEY_SHA256 is set (required for any public deployment), every API call needs a
# signed session cookie obtained by entering the access key. Only its SHA-256 is stored on the server.
ACCESS_HASH = os.environ.get("LOLPRO_ACCESS_KEY_SHA256", "").strip().lower()
SESSION_DAYS = 30
LOGIN_WINDOW, LOGIN_ATTEMPTS = 900, 8
_SECRET_FILE = ROOT / "paper" / "pro_session_secret"
_login_attempts, _login_lock = {}, threading.Lock()


def _session_secret():
    try:
        return _SECRET_FILE.read_bytes()
    except OSError:
        value = secrets.token_bytes(32)
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(value)
        return value


def make_session(now=None):
    exp = int((time.time() if now is None else now) + SESSION_DAYS * 86400)
    mac = hmac.new(_session_secret(), str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{mac}"


def valid_session(token, now=None):
    exp, _, mac = (token or "").partition(".")
    if not exp.isdigit() or int(exp) < (time.time() if now is None else now):
        return False
    good = hmac.new(_session_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, good)


def key_matches(key):
    if not ACCESS_HASH or not isinstance(key, str) or not 8 <= len(key) <= 200:
        return False
    return hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(), ACCESS_HASH)


def _allow_login_attempt(ip, now=None):
    now = now or time.monotonic()
    with _login_lock:
        recent = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW]
        if len(recent) >= LOGIN_ATTEMPTS:
            _login_attempts[ip] = recent
            return False
        _login_attempts[ip] = recent + [now]
        return True


class Handler(BaseHTTPRequestHandler):
    server_version = "LOLPro/1.0"

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _local(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ALLOWED_HOSTS

    def _cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "lolpro_session":
                return value
        return ""

    def _authed(self):
        return not ACCESS_HASH or valid_session(self._cookie())

    def _client_ip(self):
        # The public gateway (Caddy) and Tailscale both set X-Forwarded-For; the container port is loopback-only.
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def _send(self, code, body, ctype="application/json; charset=utf-8", cookie=None):
        raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        if cookie is not None:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            age = SESSION_DAYS * 86400 if cookie else 0
            self.send_header("Set-Cookie", f"lolpro_session={cookie}; Max-Age={age}; Path=/; HttpOnly; SameSite=Strict{secure}")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self._local():
            return self._send(403, {"error": "local access only"})
        engine, path = self.server.engine, self.path.split("?")[0]
        if path in STATIC:
            name, ctype = STATIC[path]
            return self._send(200, (WEB / name).read_bytes(), ctype)
        if path == "/api/auth":
            return self._send(200, {"login_required": bool(ACCESS_HASH), "authenticated": self._authed()})
        if path.startswith("/api/") and not self._authed():
            return self._send(401, {"error": "login required"})
        if path == "/api/session":
            return self._send(200, {"token": engine.token, "mode": "paper"})
        if path == "/api/state":
            return self._send(200, engine.state())
        if path in ("/api/company-news", "/api/stock"):
            from urllib.parse import parse_qs, urlsplit
            symbol = (parse_qs(urlsplit(self.path).query).get("symbol") or [""])[0].upper()
            if symbol not in engine.board.info:
                return self._send(404, {"error": "unknown symbol"})
            try:
                if path == "/api/stock":
                    return self._send(200, engine.board.detail(symbol))
                name = engine.board.info[symbol]["name"]
                return self._send(200, {"symbol": symbol, "name": name, "items": engine.news.company(_short_name(name))})
            except Exception as exc:
                return self._send(502, {"error": f"data source unavailable: {exc}"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        engine = self.server.engine
        from urllib.parse import urlsplit
        origin = urlsplit(self.headers.get("Origin", ""))
        # Same-site browser requests only: the Origin must be an allowed host, and the session token
        # (readable only by same-origin pages, as no CORS headers are sent) must match.
        same_site = self._local() and origin.scheme in ("http", "https") and origin.hostname in ALLOWED_HOSTS
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 64_000)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": "invalid JSON"})
        if self.path == "/api/login" and same_site:
            if not ACCESS_HASH:
                return self._send(200, {"ok": True})
            if not _allow_login_attempt(self._client_ip()):
                return self._send(429, {"error": "Too many attempts. Wait 15 minutes and try again."})
            if not key_matches(body.get("key")):
                return self._send(401, {"error": "That access key is not correct."})
            return self._send(200, {"ok": True}, cookie=make_session())
        if self.path == "/api/logout" and same_site:
            return self._send(200, {"ok": True}, cookie="")
        if (not same_site or not self._authed()
                or not secrets.compare_digest(self.headers.get("X-Session-Token", ""), engine.token)):
            return self._send(403 if self._authed() else 401, {"error": "forbidden"})
        if self.path == "/api/chat":
            question = str(body.get("question", "")).strip()[:2000]
            if not question:
                return self._send(400, {"error": "empty question"})
            history = body.get("history") if isinstance(body.get("history"), list) else []
            return self._send(200, assistant.ask(question, history, engine.state()))
        if self.path == "/api/run-daily":
            now = datetime.now(ZONE)
            return self._send(200, engine.run_daily(now.weekday() < 5 and now.strftime("%H:%M") >= DAILY_RUN_TIME))
        if self.path == "/api/alerts/read":
            engine.alerts.mark_read()
            return self._send(200, {"ok": True})
        if self.path == "/api/refresh":
            threading.Thread(target=engine.refresh_market, daemon=True).start()
            threading.Thread(target=engine.refresh_news, daemon=True).start()
            return self._send(202, {"ok": True})
        return self._send(404, {"error": "not found"})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--host", default="127.0.0.1", help="bind address (0.0.0.0 only inside a container behind a private port)")
    p.add_argument("--no-notify", action="store_true", help="in-app alerts only")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine(notify=not a.no_notify)
    threading.Thread(target=engine.loop, daemon=True, name="lolpro-engine").start()
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    server.engine = engine
    print(f"LOL Pro terminal (paper only): http://{a.host}:{a.port}  allowed hosts: {sorted(ALLOWED_HOSTS)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        engine._stop.set()


if __name__ == "__main__":
    main()
