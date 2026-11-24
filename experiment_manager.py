"""Supervisor for one fixed paper experiment; no arbitrary jobs or broker access."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from data import ROOT
from operations import atomic_json
from paper_experiment import POLICY,DB_NAME,CONTROL_NAME,STATUS_NAME


class ExperimentManager:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.db=self.directory/DB_NAME
        self.control=self.directory/CONTROL_NAME
        self.process=None
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.thread=None
        self.last_launch=0

    @contextmanager
    def control_lock(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        with (self.directory/'experiment25-control.lock').open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)

    def configured(self):
        return self.control.exists() or self.db.exists()

    def enabled(self):
        if not self.control.exists():return False
        value=json.loads(self.control.read_text())
        if not isinstance(value,dict) or type(value.get('enabled')) is not bool:raise ValueError('Invalid experiment control')
        return value['enabled']

    def ensure(self):
        with self.lock:
            if self.stop.is_set():raise RuntimeError('Experiment supervisor is stopping')
            if self.process and self.process.poll() is None:
                # An alive process can still be hung. Feed-error heartbeats are
                # healthy liveness; only missing/invalid/stale heartbeats recycle.
                if time.monotonic()-self.last_launch < 120:return
                value=self.status()
                try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(value.get('checked_at'))).total_seconds()
                except (ValueError,TypeError):age=float('inf')
                if -60 <= age <= 300:return
                logging.getLogger(__name__).error('Recycling paper experiment with invalid or stale heartbeat')
                self.process.terminate()
                try:self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            if time.monotonic()-self.last_launch<15:return
            env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TZ','PYTHONPATH','SSL_CERT_FILE','SSL_CERT_DIR')}
            env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLCONFIGDIR='/tmp/league-experiment-mpl',PYTHONUNBUFFERED='1')
            self.process=subprocess.Popen([sys.executable,str(ROOT/'paper_experiment.py'),'worker','--state-dir',str(self.directory)],
                cwd=ROOT,env=env,stdin=subprocess.DEVNULL)
            self.last_launch=time.monotonic()

    def start(self):
        with self.control_lock():
            atomic_json(self.control,{'enabled':True,'profile':POLICY['id']})
        self.ensure()
        return self.status()

    def pause(self):
        # Acknowledgement waits for an in-flight entry transaction, not a timer.
        with self.control_lock():
            atomic_json(self.control,{'enabled':False,'profile':POLICY['id']})
        if self.db.exists():self.ensure()
        return self.status()

    def status(self):
        path=self.directory/STATUS_NAME
        try:
            value=json.loads(path.read_text()) if path.exists() else {'state':'starting' if self.configured() else 'experiment_not_started'}
            if not isinstance(value,dict):raise ValueError('Invalid experiment status')
            enabled=self.enabled()
        except (OSError,ValueError,TypeError):
            value={'state':'error','error':'Experiment state needs operator review'};enabled=False
        alive=bool(self.process and self.process.poll() is None)
        return {**value,'enabled':enabled,'profile':POLICY,'mode':'paper','orders_submitted':False,
                'worker_alive':alive,'configured':self.configured()}

    def restore(self):
        if self.configured():
            try:self.ensure()
            except Exception:logging.getLogger(__name__).exception('Paper experiment could not resume')
        def supervise():
            while not self.stop.wait(5):
                if self.configured():
                    try:self.ensure()
                    except Exception:logging.getLogger(__name__).exception('Paper experiment restart failed')
        self.thread=threading.Thread(target=supervise,name='league-experiment-supervisor',daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=20)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
