"""Alerts: in-app list, macOS notifications and optional Telegram messages.

Telegram is used only when both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.
Desktop notifications can be turned off with PRO_DESKTOP_NOTIFY=0.
"""
from datetime import datetime, timedelta
import json
import os
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from data import ROOT

ZONE = ZoneInfo("Asia/Kolkata")
STORE = ROOT / "paper" / "pro_alerts.json"
LEVELS = ("info", "trade", "warning", "error", "critical")
NOTIFY_FROM = "trade"  # info alerts stay in the app only


class AlertCenter:
    def __init__(self, store=STORE, notify=True):
        self.store, self.notify_enabled, self._lock = store, notify, threading.Lock()
        try:
            self.items = json.loads(store.read_text()) if store.exists() else []
        except (OSError, ValueError):
            self.items = []
        self._last = {}

    def raise_alert(self, key, level, title, message, cooldown_minutes=60):
        """Record an alert unless the same key fired within the cooldown. Returns the alert or None."""
        now = datetime.now(ZONE)
        with self._lock:
            last = self._last.get(key)
            if last is None:
                last = next((datetime.fromisoformat(a["time"]) for a in self.items if a["key"] == key), None)
            if last and now - last < timedelta(minutes=cooldown_minutes):
                return None
            alert = {"id": uuid.uuid4().hex[:10], "key": key, "level": level, "title": title,
                     "message": message, "time": now.isoformat(), "read": False}
            self.items.insert(0, alert)
            del self.items[300:]
            self._last[key] = now
            self._save()
        if self.notify_enabled and LEVELS.index(level) >= LEVELS.index(NOTIFY_FROM):
            threading.Thread(target=self._deliver, args=(alert,), daemon=True).start()
        return alert

    def resolve(self, key):
        with self._lock:
            for a in self.items:
                if a["key"] == key:
                    a["resolved"] = True
            self._save()

    def mark_read(self):
        with self._lock:
            for a in self.items:
                a["read"] = True
            self._save()

    def list(self, limit=100):
        with self._lock:
            return [dict(a) for a in self.items[:limit]]

    def _save(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, indent=1))
        os.replace(tmp, self.store)

    def _deliver(self, alert):
        text = f"{alert['title']}: {alert['message']}"
        if sys.platform == "darwin" and os.environ.get("PRO_DESKTOP_NOTIFY", "1") != "0":
            try:
                script = f"display notification {json.dumps(alert['message'][:220])} with title {json.dumps('LOL Pro · ' + alert['title'][:60])}"
                subprocess.run(["osascript", "-e", script], timeout=10, check=False, capture_output=True)
            except Exception:
                pass
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if token and chat:
            try:
                body = urllib.parse.urlencode({"chat_id": chat, "text": f"[{alert['level'].upper()}] {text}"[:3500]}).encode()
                urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=body, timeout=10).read()
            except Exception:
                pass


def channels():
    return {"in_app": True,
            "desktop": sys.platform == "darwin" and os.environ.get("PRO_DESKTOP_NOTIFY", "1") != "0",
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))}
