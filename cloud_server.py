"""Authenticated, bounded API for one hosted PAPER engine. No broker orders."""
import atexit
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import resource
import signal
import shutil
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from dashboard import TerminalRuntime
from dashboard_data import build_snapshot
from data import ROOT
import ledger_store
from operations import BackupManager, OperationsStore, RateLimiter, SnapshotCache, WorkerWatchdog, atomic_json, configure_logging, emit
from feed_transport import transport
from offhost_backup import status as offhost_status

VERSION = '1.2.2'
LOG = logging.getLogger(__name__)


@dataclass
class Settings:
    users: dict
    origins: set
    auto_start: bool = False
    trust_proxy: bool = False

    @classmethod
    def from_env(cls):
        users = json.loads(os.environ.get('LEAGUE_USERS_JSON', '{}'))
        origins = set(filter(None, os.environ.get('LEAGUE_ORIGINS', '').split(',')))
        if not isinstance(users, dict) or not users or not origins:
            raise ValueError('Configure LEAGUE_USERS_JSON and LEAGUE_ORIGINS before starting the cloud engine')
        for name, user in users.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name) or not isinstance(user, dict) or user.get('role') not in ('viewer', 'trader'):
                raise ValueError('Each cloud user needs a valid name and viewer/trader role')
            if not re.fullmatch(r'[0-9a-f]{64}', user.get('sha256', '')):
                raise ValueError('Cloud access keys must be stored as SHA256 hashes')
            if user.get('expires_at'):
                expiry = datetime.fromisoformat(user['expires_at'].replace('Z', '+00:00'))
                if expiry.tzinfo is None:
                    raise ValueError('Key expiry must include a timezone')
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError('LEAGUE_ORIGINS must contain exact HTTPS origins without paths')
        return cls(users, origins, os.environ.get('LEAGUE_AUTO_START', 'false').lower() == 'true',
                   os.environ.get('LEAGUE_TRUST_PROXY', 'false').lower() == 'true')


class CloudApp:
    def __init__(self, settings, runtime, control_path):
        self.settings, self.runtime, self.control_path = settings, runtime, Path(control_path)
        self.control_lock = threading.Lock()
        self.limiter, self.cache = RateLimiter(), SnapshotCache()
        self.store = OperationsStore(self.control_path.parent / 'operations.sqlite3')
        self.backups = None
        self.started = time.monotonic()
        self.counter_lock = threading.Lock()
        self.counters = {'requests': 0, 'rejected': 0, 'errors': 0}

    def identity(self, header):
        if not isinstance(header, str) or len(header) > 320 or not header.startswith('Bearer '):
            return None
        name, separator, key = header[7:].partition('.')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name) or not 24 <= len(key) <= 256:
            return None
        user = self.settings.users.get(name)
        actual = hashlib.sha256(key.encode()).hexdigest()
        if not user or user.get('disabled') or not hmac.compare_digest(user['sha256'], actual):
            return None
        if user.get('expires_at') and datetime.now(timezone.utc) >= datetime.fromisoformat(user['expires_at'].replace('Z', '+00:00')):
            return None
        return {'name': name, 'role': user['role']}

    def client_ip(self, env):
        raw = env.get('HTTP_X_LEAGUE_CLIENT_IP', env.get('REMOTE_ADDR')) if self.settings.trust_proxy else env.get('REMOTE_ADDR')
        try:
            return str(ipaddress.ip_address(raw))
        except (ValueError, TypeError):
            return 'unknown'

    def monitor(self):
        status = self.runtime.trader.status
        issues = []
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(status.get('checked_at'))).total_seconds()
        except (ValueError, TypeError):
            age = None
        thread = getattr(self.runtime.trader, '_thread', None)
        if hasattr(self.runtime.trader, '_thread') and (thread is None or not thread.is_alive()):
            issues.append('worker_not_running')
        if age is None or age > max(180, 3 * status.get('poll_seconds', 60)):
            issues.append('heartbeat_stale')
        if status.get('state') in ('error', 'data_error', 'awaiting_data', 'square_off_waiting_for_data', 'stopped', 'migrated_to_cloud', 'shutdown_waiting', 'storage_guard', 'calendar_unverified'):
            issues.append(status['state'])
        if status.get('state') == 'awaiting_fresh_market_data':
            issues.append('market_data_stale')
        backup = self.backups.status if self.backups else {'state': 'not_configured', 'off_host': False}
        if backup['state'] == 'error':
            issues.append('backup_failed')
        offhost = offhost_status(self.control_path.parent / 'offhost-backup.json', (self.control_path.parent / 'offhost-required').exists())
        if offhost['state'] not in ('ok', 'not_configured'):
            issues.append('offhost_backup_' + offhost['state'])
        free = shutil.disk_usage(self.control_path.parent).free
        if free < 1024 ** 3:
            issues.append('disk_space_low')
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if sys.platform == 'darwin' else peak * 1024
        return {'ready': not issues, 'alerts': issues, 'heartbeat_age_seconds': round(age, 1) if age is not None else None,
                'uptime_seconds': round(time.monotonic() - self.started), 'version': VERSION,
                'backup': backup, 'offhost_backup': offhost, 'snapshot_cache': {'hits': self.cache.hits, 'builds': self.cache.builds, 'ttl_seconds': self.cache.ttl},
                'storage_free_bytes': free, 'process_peak_rss_bytes': peak_bytes,
                'counters': dict(self.counters), 'feed_circuits': transport.status(),
                'execution_workers': 1, 'broker_execution': False}

    def __call__(self, env, start_response):
        origin, request_id, user = env.get('HTTP_ORIGIN', ''), uuid.uuid4().hex, None
        method, raw_path = env.get('REQUEST_METHOD', 'GET'), env.get('PATH_INFO', '/')
        path = '/api/' + raw_path[len('/api/v1/'):] if raw_path.startswith('/api/v1/') else raw_path
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff'), ('Vary', 'Origin'), ('X-Request-ID', request_id),
                   ('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'"),
                   ('X-Frame-Options', 'DENY'), ('Referrer-Policy', 'no-referrer'),
                   ('Strict-Transport-Security', 'max-age=31536000')]
        if origin in self.settings.origins:
            headers += [('Access-Control-Allow-Origin', origin), ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
                        ('Access-Control-Allow-Headers', 'Authorization, Content-Type, Idempotency-Key'),
                        ('Access-Control-Expose-Headers', 'X-Request-ID, Retry-After'), ('Access-Control-Max-Age', '300')]

        def respond(code, payload, extra=()):
            labels = {200: 'OK', 202: 'Accepted', 204: 'No Content', 400: 'Bad Request', 401: 'Unauthorized',
                      403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed', 409: 'Conflict',
                      413: 'Content Too Large', 429: 'Too Many Requests', 500: 'Internal Server Error', 503: 'Service Unavailable'}
            body = b'' if code == 204 else payload if isinstance(payload, bytes) else json.dumps(payload, allow_nan=False, default=str).encode()
            with self.counter_lock:
                self.counters['requests'] += 1
                self.counters['rejected'] += int(400 <= code < 500)
                self.counters['errors'] += int(code >= 500)
            if method == 'POST' or code >= 400:
                action = path if path in ('/api/automation/start', '/api/automation/pause', '/api/backtest/run') else 'api_request'
                if code != 429:  # Rejected floods must not turn into a database-write flood.
                    try:
                        self.store.audit(user['name'] if user else None, action, code, request_id)
                    except Exception:
                        LOG.exception('Operational audit write failed')
                emit('api_response', actor=user['name'] if user else None, action=action, status=code, request_id=request_id)
            start_response(f'{code} {labels[code]}', headers + list(extra) + [('Content-Length', str(len(body)))])
            return [body]

        def limited(key, limit):
            allowed, wait = self.limiter.allow(key, limit)
            return None if allowed else respond(429, {'error': 'Too many requests; wait before retrying'}, [('Retry-After', str(wait))])

        if path == '/healthz' and method == 'GET':
            return respond(200, {'status': 'ok', 'mode': 'paper'})
        result = limited(('ingress', self.client_ip(env)), 240)
        if result is not None:
            return result
        if origin and origin not in self.settings.origins:
            return respond(403, {'error': 'This app origin is not allowed'})
        if method == 'OPTIONS':
            result = limited(('preflight', self.client_ip(env)), 120)
            return result if result is not None else respond(204, {})
        if path == '/readyz' and method == 'GET':
            ready = self.monitor()['ready']
            return respond(200 if ready else 503, {'status': 'ready' if ready else 'degraded', 'mode': 'paper'})
        user = self.identity(env.get('HTTP_AUTHORIZATION', ''))
        if not user:
            result = limited(('authentication', self.client_ip(env)), 15)
            return result if result is not None else respond(401, {'error': 'Sign in to the hosted paper engine with your own access key'})
        result = limited(('user', user['name']), 180)
        if result is not None:
            return result
        try:
            if method == 'GET':
                if path == '/api/health':
                    return respond(200, {'status': 'ok', 'mode': 'paper', 'execution': 'cloud', 'version': VERSION,
                                         'user': user, 'permissions': {'control': user['role'] == 'trader'},
                                         'capabilities': {'idempotency': True, 'operations': True},
                                         'automation': self.runtime.trader.status, 'operations': self.monitor()})
                if path == '/api/status':
                    jobs = self.runtime.jobs_snapshot() if hasattr(self.runtime, 'jobs_snapshot') else list(self.runtime.jobs.values())
                    return respond(200, {'automation': self.runtime.trader.status, 'jobs': jobs, 'operations': self.monitor()})
                if path == '/api/operations':
                    return respond(200, self.monitor())
                if path == '/api/dashboard':
                    return respond(200, self.cache.get(build_snapshot))
                if path in ('/api/history/trades', '/api/history/events'):
                    try:
                        query = env.get('QUERY_STRING', '')
                        if len(query) > 256:
                            raise ValueError()
                        params = parse_qs(query, strict_parsing=True, max_num_fields=2)
                        if set(params) - {'limit', 'cursor'} or any(len(v) != 1 for v in params.values()):
                            raise ValueError()
                        page = ledger_store.history(getattr(self.runtime.trader, 'db', ROOT/'paper/intraday_500k.sqlite3'),
                                                    path.rsplit('/', 1)[-1], int(params.get('limit', ['50'])[0]), params.get('cursor', [None])[0])
                    except (ValueError, OverflowError):
                        return respond(400, {'error': 'Use limit=1..200 and the next_cursor returned by the previous page'})
                    return respond(200, page)
                return respond(404, {'error': 'Unsupported paper API path'})
            if method != 'POST':
                return respond(405, {'error': 'Use GET or POST'}, [('Allow', 'GET, POST, OPTIONS')])
            if path not in ('/api/automation/start', '/api/automation/pause', '/api/backtest/run'):
                return respond(404, {'error': 'Unsupported paper action'})
            if user['role'] != 'trader':
                return respond(403, {'error': 'This account can view results but cannot control the paper engine'})
            result = limited(('control', user['name']), 10)
            if result is not None:
                return result
            if env.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                return respond(400, {'error': 'Use an application/json request'})
            try:
                length = int(env.get('CONTENT_LENGTH') or 0)
                if not 0 <= length <= 1024:
                    return respond(413, {'error': 'Request is too large'})
                raw = env['wsgi.input'].read(length) if length else b'{}'
                if length and len(raw) != length:
                    raise ValueError()
                payload = json.loads(raw)
                if not isinstance(payload, dict) or payload:
                    raise ValueError()
            except (ValueError, KeyError, UnicodeError):
                return respond(400, {'error': 'Send an empty JSON object: {}'})
            key = env.get('HTTP_IDEMPOTENCY_KEY') or request_id
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', key):
                return respond(400, {'error': 'Invalid Idempotency-Key'})
            claim, previous = self.store.claim(user['name'], key, method + ' ' + path)
            if claim == 'replay':
                return respond(*previous)
            if claim in ('pending', 'conflict'):
                return respond(409, {'error': 'This action key is pending or was used for another action. Check status before retrying.'})
            if claim == 'full':
                return respond(503, {'error': 'Action records are full; operator review required'})
            with self.control_lock:
                if path in ('/api/automation/start', '/api/automation/pause'):
                    enabled = path.endswith('/start')
                    atomic_json(self.control_path, {'enabled': enabled})
                    value = self.runtime.trader.start() if enabled else self.runtime.trader.pause()
                    code = 200
                else:
                    value, code = self.runtime.backtest(), 202
                self.store.finish(user['name'], key, code, value)
            self.cache.invalidate()
            return respond(code, value)
        except Exception:
            LOG.exception('Hosted paper operation failed; request_id=%s', request_id)
            return respond(500, {'error': 'The hosted paper engine could not complete this operation. Check its server logs.', 'request_id': request_id})


def create_app(settings=None, runtime=None, control_path=None):
    configure_logging()
    settings = settings or Settings.from_env()
    control_path = Path(control_path or ROOT / 'paper/cloud_control.json')
    if runtime is not None:
        return CloudApp(settings, runtime, control_path)
    control_path.parent.mkdir(parents=True, exist_ok=True)
    lock = (control_path.parent / 'cloud_engine.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Only one hosted paper engine may use this account. Set Gunicorn workers=1.')
    try:
        db = control_path.parent / 'intraday_500k.sqlite3'
        backups = BackupManager(db, control_path.parent / 'backups')
        if db.exists():
            backups.run_once()
            ledger_store.migrate(db)
        runtime = TerminalRuntime(state_dir=control_path.parent)
        enabled = settings.auto_start
        if control_path.exists():
            restored = json.loads(control_path.read_text())
            if type(restored.get('enabled')) is not bool:
                raise ValueError('Invalid persisted paper control state')
            enabled = restored['enabled']
        app = CloudApp(settings, runtime, control_path)
        app.backups = backups
        runtime.trader.start() if enabled else runtime.trader.pause()
        backups.start()
        watchdog = WorkerWatchdog(runtime.trader, lambda: os.kill(os.getpid(), signal.SIGTERM))
        watchdog.start()
    except Exception:
        if runtime is not None:
            runtime.close()
        lock.close()
        raise
    app.engine_lock = lock
    app.watchdog = watchdog
    def close():
        watchdog.close()
        runtime.close()
        backups.close()
        lock.close()
    atexit.register(close)
    return app
