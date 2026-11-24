"""Bounded API guards, private operational records, and verified SQLite backups."""
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import shutil
import threading
import time

LOG = logging.getLogger('league.operations')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as file:
        os.chmod(temporary, 0o600)
        json.dump(value, file, allow_nan=False, default=str)
        file.flush();os.fsync(file.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        try:
            value = json.loads(record.getMessage())
            if not isinstance(value, dict):
                value = {'message': record.getMessage()}
        except (ValueError, TypeError):
            value = {'message': record.getMessage()}
        value.update(level=record.levelname, logger=record.name)
        if record.exc_info:
            value['exception'] = self.formatException(record.exc_info)
        return json.dumps(value, default=str)


def configure_logging():
    logger = logging.getLogger()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def emit(event, **fields):
    LOG.info(json.dumps({'event': event, 'at': datetime.now(timezone.utc).isoformat(), **fields}, separators=(',', ':')))


class RateLimiter:
    def __init__(self, max_keys=4096, clock=time.monotonic):
        self.entries, self.lock = OrderedDict(), threading.Lock()
        self.max_keys, self.clock = max_keys, clock

    def allow(self, key, limit, seconds=60):
        now = self.clock()
        with self.lock:
            count, reset = self.entries.pop(key, (0, now + seconds))
            if now >= reset:
                count, reset = 0, now + seconds
            allowed = count < limit
            self.entries[key] = (count + int(allowed), reset)
            while len(self.entries) > self.max_keys:
                self.entries.popitem(last=False)
            return allowed, max(1, int(reset - now + 0.999))


class SnapshotCache:
    """A single cached JSON response; simultaneous cache misses share one build."""
    def __init__(self, ttl=5, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.lock, self.body, self.expires = threading.Lock(), None, 0
        self.hits, self.builds = 0, 0

    def get(self, build):
        with self.lock:
            now = self.clock()
            if self.body is not None and now < self.expires:
                self.hits += 1
                return self.body
            body = json.dumps(build(), allow_nan=False, default=str, separators=(',', ':')).encode()
            self.body, self.expires = body, self.clock() + self.ttl
            self.builds += 1
            return body

    def invalidate(self):
        with self.lock:
            self.expires = 0


class OperationsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT, action TEXT NOT NULL, status INTEGER NOT NULL, request_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS audit_at ON audit(at);
                CREATE TABLE IF NOT EXISTS requests(actor TEXT NOT NULL, key TEXT NOT NULL, signature TEXT NOT NULL, at REAL NOT NULL, status INTEGER, body TEXT, PRIMARY KEY(actor,key));
            ''')
        self.path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def audit(self, actor, action, status, request_id):
        with self.connect() as conn:
            conn.execute('INSERT INTO audit(at,actor,action,status,request_id) VALUES(?,?,?,?,?)',
                         (datetime.now(timezone.utc).isoformat(), actor, action, status, request_id))
            # Bound disk usage; keep the latest 20,000 operational events.
            conn.execute('DELETE FROM audit WHERE id <= (SELECT COALESCE(MAX(id),0)-20000 FROM audit)')

    def claim(self, actor, key, signature):
        digest = hashlib.sha256(key.encode()).hexdigest()
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM requests WHERE at < ? AND status IS NOT NULL', (time.time() - 7*86400,))
            row = conn.execute('SELECT signature,status,body FROM requests WHERE actor=? AND key=?', (actor, digest)).fetchone()
            if row:
                if row[0] != signature:
                    return 'conflict', None
                return ('pending', None) if row[1] is None else ('replay', (row[1], json.loads(row[2])))
            if conn.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= 10000:
                return 'full', None
            conn.execute('INSERT INTO requests(actor,key,signature,at) VALUES(?,?,?,?)', (actor, digest, signature, time.time()))
        return 'new', None

    def finish(self, actor, key, status, body):
        with self.connect() as conn:
            conn.execute('UPDATE requests SET status=?,body=? WHERE actor=? AND key=?',
                         (status, json.dumps(body, allow_nan=False, default=str), actor, hashlib.sha256(key.encode()).hexdigest()))


def backup_database(source, target):
    source, target = Path(source).resolve(), Path(target)
    if source == target.resolve():
        raise ValueError('Backup destination must differ from the account')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10)) as src, closing(sqlite3.connect(temporary)) as dst:
            src.backup(dst, pages=128, sleep=0.01)
            dst.commit()
            dst.execute('PRAGMA journal_mode=DELETE')
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity verification failed')
        temporary.chmod(0o600)
        with temporary.open('rb') as file:
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'file': target.name, 'bytes': target.stat().st_size,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}


class BackupManager:
    def __init__(self, source, directory, interval=3600, keep=24):
        self.source, self.directory = Path(source), Path(directory)
        self.interval, self.keep = interval, keep
        self.stop = threading.Event()
        self.thread = None
        self.status = {'state': 'not_started', 'off_host': False}

    def run_once(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        sources = [path for path in (self.source, self.source.parent / 'operations.sqlite3',self.source.parent/'intraday_experiment25.sqlite3') if path.exists()]
        estimated = sum(path.stat().st_size + (Path(str(path)+'-wal').stat().st_size if Path(str(path)+'-wal').exists() else 0)
                        for path in sources)
        if shutil.disk_usage(self.directory).free < estimated + 1024**3:
            raise OSError('Insufficient free space for a backup while retaining trading headroom')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        manifests = []
        for source in sources:
            if source.exists():
                manifests.append(backup_database(source, self.directory / (stamp + '-' + source.name)))
        if not manifests:
            raise ValueError('No database available to back up')
        manifest = self.directory / (stamp + '.json')
        self.status = {'state': 'ok', 'at': datetime.now(timezone.utc).isoformat(),
                       'files': manifests, 'off_host': False}
        atomic_json(manifest, self.status)
        for old in sorted(self.directory.glob('*.json'), reverse=True)[self.keep:]:
            old_data = json.loads(old.read_text())
            for item in old_data['files']:
                (self.directory / Path(item['file']).name).unlink(missing_ok=True)
            old.unlink()
        return self.status

    def start(self):
        self.thread = threading.Thread(target=self._loop, name='league-backups', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.run_once()
                emit('backup_complete')
            except Exception:
                self.status = {'state': 'error', 'off_host': False}
                LOG.exception('Database backup failed')
            self.stop.wait(self.interval)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=15)


class WorkerWatchdog:
    """Recycle a failed application worker through its existing supervisor.

    This checks worker liveness/heartbeat, not market freshness: weekends, a feed
    outage, paused entries and a risk halt must never create restart loops.
    """
    def __init__(self, trader, restart, grace=120, stale=300, clock=time.monotonic):
        self.trader, self.restart, self.grace, self.stale, self.clock = trader, restart, grace, stale, clock
        self.began = clock()
        self.stop = threading.Event()
        self.thread = None
        self.triggered = False

    def check(self, now=None):
        if self.stop.is_set() or self.triggered or self.clock() - self.began < self.grace:
            return None
        worker = getattr(self.trader, '_thread', None)
        reason = 'worker_not_running' if worker is None or not worker.is_alive() else None
        try:
            checked = datetime.fromisoformat(self.trader.status.get('checked_at'))
            age = ((now or datetime.now(timezone.utc)) - checked).total_seconds()
        except (TypeError, ValueError):
            age = float('inf')
        if reason is None and age > self.stale:
            reason = 'heartbeat_stale'
        if reason:
            self.triggered = True
            emit('worker_restart_requested', reason=reason)
            self.restart()
        return reason

    def start(self):
        def run():
            while not self.stop.wait(30):
                self.check()
        self.thread = threading.Thread(target=run, name='league-watchdog', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
