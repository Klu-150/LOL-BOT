"""Last of Our League local terminal: automatic PAPER trading and research."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import secrets
import threading
from urllib.parse import urlsplit
import uuid

from dashboard_data import build_snapshot, export_snapshot
from data import ROOT
from auto_trader import AutoTrader
from operations import atomic_json

STATIC = ROOT / "dashboard" / "dist"


class TerminalRuntime:
    def __init__(self, state_dir=None):
        self.token = secrets.token_urlsafe(32)
        self.trader = AutoTrader(db=state_dir / 'intraday_500k.sqlite3') if state_dir else AutoTrader()
        self.jobs_path = (state_dir or ROOT / 'paper') / 'research_jobs.json'
        self.jobs = json.loads(self.jobs_path.read_text()) if self.jobs_path.exists() else {}
        for job in self.jobs.values():
            if job.get('status') == 'running':
                job.update(status='interrupted', error='Server restarted; this research job was not replayed')
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="league-research")
        self.lock = threading.Lock()
        self.closed = False
        self.process = None

    def _persist_jobs(self):
        while len(self.jobs) > 20:
            oldest = next((key for key, value in self.jobs.items() if value['status'] != 'running'), None)
            if oldest is None:
                break
            del self.jobs[oldest]
        atomic_json(self.jobs_path, self.jobs)

    def jobs_snapshot(self):
        with self.lock:
            return [dict(job) for job in self.jobs.values()]

    def backtest(self):
        with self.lock:
            if self.closed:
                raise RuntimeError('The research worker is shutting down')
            running = next((job for job in self.jobs.values() if job["status"] == "running"), None)
            if running:
                return running
            job = {"id": uuid.uuid4().hex, "status": "running", "kind": "intraday_backtest"}
            self.jobs[job["id"]] = job
            self._persist_jobs()
        def execute():
            try:
                # The automatic trader reads module-level settings: do not run research
                # cost sensitivity overrides in the same interpreter as the paper worker.
                import subprocess, sys
                with self.lock:
                    if self.closed:
                        job.update(status='interrupted');self._persist_jobs();return
                    self.process = subprocess.Popen([sys.executable, str(ROOT / 'intraday_backtest.py')],
                                                     cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    process = self.process
                try:
                    stdout, stderr = process.communicate(timeout=180)
                except subprocess.TimeoutExpired:
                    process.kill();process.communicate();raise
                if process.returncode:
                    raise ValueError((stderr or stdout)[-1500:])
                with self.lock:
                    job.update(status="completed", result=json.loads(stdout));self._persist_jobs()
            except Exception as exc:
                logging.getLogger(__name__).exception('Research backtest failed')
                with self.lock:
                    job.update(status="failed", error=type(exc).__name__ + ': research job failed');self._persist_jobs()
            finally:
                with self.lock:
                    self.process = None
        self.pool.submit(execute)
        return job

    def close(self):
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.terminate()
        self.trader.shutdown()
        self.pool.shutdown(wait=True, cancel_futures=True)


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def _json(self, data, status=200):
        body = json.dumps(data, allow_nan=False, separators=(",", ":"), default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _local_host(self):
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/') and not self._local_host():
            self._json({"error": "The terminal API is available only on loopback"}, 403)
            return
        try:
            if path == "/api/health":
                self._json({"status": "ok", "mode": "paper", "session_token": self.server.runtime.token,
                            "automation": self.server.runtime.trader.status})
                return
            if path == "/api/status":
                self._json({"automation": self.server.runtime.trader.status, "jobs": list(self.server.runtime.jobs.values())})
                return
            if path == "/api/dashboard":
                self._json(build_snapshot())
                return
        except Exception as exc:
            self._json({"error": str(exc)}, 500)
            return
        super().do_GET()

    def do_POST(self):
        origin = self.headers.get("Origin")
        expected = "http://" + self.headers.get("Host", "")
        token = self.headers.get("X-Terminal-Token", "")
        if not self._local_host() or origin != expected or not secrets.compare_digest(token, self.server.runtime.token):
            self._json({"error": "This action requires the local terminal session"}, 403)
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/automation/start":
                self._json(self.server.runtime.trader.start())
            elif path == "/api/automation/pause":
                self._json(self.server.runtime.trader.pause())
            elif path == "/api/backtest/run":
                self._json(self.server.runtime.backtest(), 202)
            else:
                self._json({"error": "Unsupported paper/research action"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        # Reload scripts after reconnecting to a restarted terminal.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--auto-paper", action="store_true", help="automatically manage the intraday virtual account")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    payload = export_snapshot(STATIC / "data.json")
    print(f"Loaded {len(payload['reports'])} report sets.", flush=True)
    if args.export:
        return
    runtime = TerminalRuntime()
    try:
        with ThreadingHTTPServer((args.host, args.port), DashboardHandler) as server:
            server.runtime = runtime
            if args.auto_paper:
                runtime.trader.start()
            print(f"Last of Our League: http://{args.host}:{args.port} — PAPER ONLY", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
