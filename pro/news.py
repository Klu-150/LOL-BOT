"""Live market and company news from public RSS feeds, scored for market risk.

News is used only as a risk veto (stand aside / warn), never as a buy or sell
trigger: headline sentiment has weak, hard-to-test predictive evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import re
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (Macintosh) paper-research-terminal"
MARKET_FEEDS = {
    "Google News": "https://news.google.com/rss/search?q=Nifty+OR+Sensex+OR+%22stock+market%22+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    "Economic Times": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Livemint": "https://www.livemint.com/rss/markets",
    "Business Standard": "https://www.business-standard.com/rss/markets-106.rss",
}
# Nifty heavyweights (Yahoo symbol, display name, words that identify the company in headlines).
COMPANIES = [
    ("RELIANCE.NS", "Reliance Industries", ["reliance", "ril"]),
    ("HDFCBANK.NS", "HDFC Bank", ["hdfc bank"]),
    ("ICICIBANK.NS", "ICICI Bank", ["icici bank"]),
    ("INFY.NS", "Infosys", ["infosys", "infy"]),
    ("TCS.NS", "TCS", ["tcs", "tata consultancy"]),
    ("BHARTIARTL.NS", "Bharti Airtel", ["airtel", "bharti"]),
    ("ITC.NS", "ITC", ["itc"]),
    ("LT.NS", "Larsen & Toubro", ["larsen", "l&t"]),
    ("SBIN.NS", "State Bank of India", ["sbi", "state bank"]),
    ("KOTAKBANK.NS", "Kotak Mahindra Bank", ["kotak"]),
    ("AXISBANK.NS", "Axis Bank", ["axis bank"]),
    ("HINDUNILVR.NS", "Hindustan Unilever", ["hul", "hindustan unilever"]),
    ("BAJFINANCE.NS", "Bajaj Finance", ["bajaj finance"]),
    ("M&M.NS", "Mahindra & Mahindra", ["mahindra", "m&m"]),
    ("SUNPHARMA.NS", "Sun Pharma", ["sun pharma"]),
    ("MARUTI.NS", "Maruti Suzuki", ["maruti"]),
]
# Regex word patterns (stems allowed) -> weight.
NEGATIVE = {r"crash\w*": 3, r"plung\w*": 3, r"plummet\w*": 3, r"tumbl\w*": 2, r"slump\w*": 2,
            r"sell-?offs?": 2, r"fall(s|ing)?": 1, r"fell": 1, r"drops?|dropped": 1, r"slip\w*": 1,
            r"declin\w*": 1, r"slid\w*|slides?": 1, r"sinks?|sank": 2, r"los(es|ing|ses)": 1,
            r"war": 3, r"attacks?": 3, r"terror\w*": 3, r"sanctions?": 2, r"tariffs?": 2, r"defaults?": 3,
            r"fraud\w*": 3, r"probe\w*": 2, r"raids?": 2, r"bans?|banned": 2, r"downgrad\w*": 2,
            r"recession\w*": 3, r"rate hikes?|hikes? rates?": 2, r"outflows?": 2, r"weak\w*": 1,
            r"warn\w*": 1, r"panic\w*": 3, r"bloodbath": 3, r"lockdowns?": 3, r"fears?": 2,
            r"correction": 1, r"volatil\w*": 1, r"red": 1,
            # A rally or streak that ends is bad news even though it contains "rally".
            r"(?:end|ends|ended|snaps?|snapped|breaks?|halts?|halted)\b[\w\s-]{0,25}(?:rally|streak|gains)": 4}
POSITIVE = {r"rall(y|ies|ied)": 2, r"surg\w*": 2, r"soar\w*": 2, r"jump\w*": 1, r"gain\w*": 1,
            r"rise[sn]?|rising|rose": 1, r"record high\w*": 2, r"all-time high": 2, r"upgrad\w*": 2,
            r"beats?": 2, r"rate cuts?|cuts? rates?": 2, r"inflows?": 1, r"strong\w*": 1, r"recover\w*": 1,
            r"rebound\w*": 1, r"bullish": 2, r"green": 1, r"climb\w*": 1, r"high(er|s)": 1}
MACRO = ["rbi", "fed", "budget", "gdp", "inflation", "war", "election", "crude", "rupee", "sebi", "fii", "fpi",
         "tariff", "sanction", "us market", "wall street", "nasdaq", "china", "geopolitical", "repo"]


def _score(text):
    t = f" {text.lower()} "
    neg = sum(w for k, w in NEGATIVE.items() if re.search(rf"\b(?:{k})\b", t))
    pos = sum(w for k, w in POSITIVE.items() if re.search(rf"\b(?:{k})\b", t))
    macro = any(re.search(rf"\b{re.escape(k)}\b", t) for k in MACRO)
    sentiment = "negative" if neg > pos else "positive" if pos > neg else "neutral"
    impact = min(5, max(neg, pos) + (2 if macro else 0))
    return sentiment, impact, macro


def _companies(text):
    t = f" {text.lower()} "
    return [name for sym, name, words in COMPANIES
            if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in words)]


def _fetch(source, url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(2_000_000)
    root = ET.fromstring(body)
    items = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        publisher = source
        src = it.find("source")
        if src is not None and src.text:
            publisher = src.text.strip()
            title = re.sub(rf"\s+-\s+{re.escape(publisher)}$", "", title)
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            when = datetime.now(timezone.utc)
        sentiment, impact, macro = _score(title)
        items.append({"id": hashlib.sha1(title.lower().encode()).hexdigest()[:12], "title": title, "link": link,
                      "source": publisher, "feed": source, "published": when.isoformat(),
                      "sentiment": sentiment, "impact": impact, "macro": macro, "companies": _companies(title)})
    return items


def company_url(name):
    q = urllib.parse.quote_plus(f'"{name}" share when:3d')
    return f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def risk(items, hours=3, now=None):
    """Market news risk 0-100 from recent high-impact negative headlines (macro weighted)."""
    now = now or datetime.now(timezone.utc)
    recent = [i for i in items if datetime.fromisoformat(i["published"]) >= now - timedelta(hours=hours)]
    neg = sum(i["impact"] * (1.5 if i["macro"] else 1) for i in recent if i["sentiment"] == "negative")
    pos = sum(i["impact"] for i in recent if i["sentiment"] == "positive")
    score = max(0.0, min(100.0, 4 * (neg - 0.5 * pos)))
    level = "high" if score >= 60 else "elevated" if score >= 35 else "normal"
    return {"score": round(score), "level": level, "window_hours": hours, "headlines": len(recent),
            "negative": sum(1 for i in recent if i["sentiment"] == "negative"),
            "positive": sum(1 for i in recent if i["sentiment"] == "positive")}


class NewsDesk:
    """Thread-safe cache of market news, refreshed by the server's background loop."""

    def __init__(self):
        self.items, self.errors, self.updated, self._lock = [], {}, None, threading.Lock()
        self._company = {}

    def refresh(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {name: pool.submit(_fetch, name, url) for name, url in MARKET_FEEDS.items()}
        merged, errors = {}, {}
        for name, job in jobs.items():
            try:
                for i in job.result():
                    merged.setdefault(i["id"], i)
            except Exception as exc:
                errors[name] = str(exc)[:200]
        items = sorted(merged.values(), key=lambda i: i["published"], reverse=True)[:250]
        with self._lock:
            if items:
                self.items = items
            self.errors, self.updated = errors, datetime.now(timezone.utc).isoformat()
        return self.snapshot()

    def company(self, name, max_age=300):
        cached = self._company.get(name)
        if cached and (datetime.now(timezone.utc) - cached[0]).total_seconds() < max_age:
            return cached[1]
        items = _fetch("Google News", company_url(name))[:30]
        self._company[name] = (datetime.now(timezone.utc), items)
        return items

    def snapshot(self):
        with self._lock:
            return {"items": list(self.items), "errors": dict(self.errors), "updated": self.updated,
                    "risk": risk(self.items) if self.items else risk([])}
