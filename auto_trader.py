"""Automatic intraday PAPER runner. Public bars and model fills; no real orders."""
import json
import os
from pathlib import Path
import threading
import logging
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import config as C
from data import ROOT
import intraday_feed as feed
import intraday_paper as paper

STATUS_FILE = ROOT / "paper" / "intraday_runtime.json"
MIGRATION_FILE = ROOT / "paper" / "cloud_migration.json"


class AutoTrader:
    def __init__(self, interval=None, db=None):
        self.interval = max(15, int(interval or C.INTRADAY_POLL_SECONDS))
        self.db = Path(db or paper.DEFAULT_DB)
        self.entries_enabled = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._cycle_lock = threading.Lock()
        # Serialize entry admission with start/pause acknowledgements, not feed I/O.
        self._entry_lock = threading.RLock()
        self._status_lock = threading.Lock()
        self._thread = None
        self.status = {"enabled": False, "state": "stopped", "mode": "paper", "orders_submitted": False}

    def _migration(self):
        if self.db.resolve() != Path(paper.DEFAULT_DB).resolve() or not MIGRATION_FILE.exists():
            return None
        try:
            return json.loads(MIGRATION_FILE.read_text()) or {"message": "Account migration marker exists"}
        except (OSError, ValueError):
            return {"message": "Migration marker needs review before local trading can resume"}

    def _migrated_status(self, migration):
        self.entries_enabled = False
        return self._write({"state": "migrated_to_cloud", "cloud_origin": migration.get("cloud_origin"),
                            "message": "This account has moved to the hosted engine. Use the mobile app connection."})

    def _write(self, value):
        with self._status_lock:
            self.status = {**value, "enabled": self.entries_enabled, "mode": "paper", "bot_name": C.BOT_NAME,
                           "poll_seconds": self.interval, "checked_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                           "orders_submitted": False}
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = STATUS_FILE.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.status, allow_nan=False, default=str))
            os.replace(temporary, STATUS_FILE)
            return self.status

    def cycle(self, refresh=True, now=None):
        if not self._cycle_lock.acquire(blocking=False):
            return self.status
        try:
            migration = self._migration()
            if migration:
                return self._migrated_status(migration)
            now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
            stamp = now.strftime("%H:%M")
            session_window = now.weekday() < 5 and "09:15" <= stamp <= "15:40"
            source = None
            if refresh and session_window:
                try:
                    source = feed.refresh(period="5d")
                except Exception as exc:
                    # A failed refresh never authorises a new paper entry.
                    try:
                        with self._entry_lock:
                            paper.process(self.db, now=now, entries_enabled=False)
                    except Exception:
                        pass
                    return self._write({"state": "data_error", "error": str(exc)})
            if not (ROOT / C.INTRADAY_CSV).exists():
                return self._write({"state": "awaiting_data", "message": "Refresh the intraday feed or supply timestamped 5m CSV bars"})
            if self._stop.is_set():
                return self.status
            storage_ok = shutil.disk_usage(self.db.parent).free >= 1024 ** 3
            with self._entry_lock:
                result = paper.process(self.db, now=now,
                                       entries_enabled=self.entries_enabled and storage_ok and not self._stop.is_set())
            result["state"] = result.pop("status")
            if not storage_ok:
                result.update(state='storage_guard', message='Low disk space blocks new entries; existing exits remain managed')
            if not session_window and result["state"] == "awaiting_fresh_market_data":
                result["state"] = "market_closed"
            if not self.entries_enabled and result["state"] == "watching":
                result["state"] = "entries_paused_managing_exits"
            if source:
                result["feed"] = source
            return self._write(result)
        except Exception as exc:
            return self._write({"state": "error", "error": str(exc)})
        finally:
            self._cycle_lock.release()

    def start(self):
        migration = self._migration()
        if migration:
            return self._migrated_status(migration)
        with self._entry_lock:
            self.entries_enabled = True
            try:
                self._write({**self.status, "state": "starting"})
            except Exception:
                self.entries_enabled = False
                raise
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="league-paper-trader")
            self._thread.start()
        else:
            self._wake.set()
        return self.status

    def pause(self):
        with self._entry_lock:
            self.entries_enabled = False
        # Keep the worker active so an existing position can reach its exit.
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="league-paper-trader")
            self._thread.start()
        else:
            self._wake.set()
        return self._write({**self.status, "state": "entries_paused_managing_exits"})

    def _loop(self):
        while not self._stop.is_set():
            self._wake.clear()
            try:
                self.cycle()
            except Exception:
                # A status-file failure must not silently kill the worker, or leave
                # entries authorised while persistence is unhealthy.
                with self._entry_lock:
                    self.entries_enabled = False
                logging.getLogger(__name__).exception('Paper cycle persistence failed; new entries disabled')
            self._wake.wait(self.interval)

    def shutdown(self):
        self._stop.set()
        self._wake.set()
        with self._entry_lock:
            self.entries_enabled = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=55)
            if self._thread.is_alive():
                self._write({"state": "shutdown_waiting", "message": "Waiting for an in-flight data or paper transaction"})
                return
        self._write({"state": "stopped", "message": "The local runner is stopped; keep it running during sessions to manage exits"})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--no-refresh', action='store_true')
    parser.add_argument('--interval', type=int, default=C.INTRADAY_POLL_SECONDS)
    args = parser.parse_args()
    runner = AutoTrader(args.interval)
    runner.entries_enabled = True
    if args.once:
        print(json.dumps(runner.cycle(refresh=not args.no_refresh), indent=2))
    else:
        try:
            while True:
                print(json.dumps(runner.cycle(refresh=not args.no_refresh)), flush=True)
                if runner._stop.wait(runner.interval):
                    break
        except KeyboardInterrupt:
            runner.shutdown()
