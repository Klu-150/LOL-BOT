"""Private Azure Blob recovery copies, using the VM's managed identity.

This standalone job uploads ONLY verified database snapshots and their manifest.
It never exports credentials, changes the live ledger, or accepts an arbitrary URL.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import email.utils
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from operations import atomic_json,sha256_file

MAX_BYTES = 64 * 1024**2  # compressed archive/network bound
MAX_RESTORE_BYTES = 512 * 1024**2  # aggregate uncompressed database bound
VERSION = '2023-11-03'
SNAPSHOT_SUFFIXES = ('-intraday_500k.sqlite3', '-operations.sqlite3', '-intraday_experiment25.sqlite3')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Backup endpoint redirect refused')


def status(path, required=False, now=None):
    if not required:
        return {'state': 'not_configured', 'off_host': False}
    try:
        value = json.loads(Path(path).read_text())
        timestamp = datetime.fromisoformat(value['last_success_at'])
        age = ((now or datetime.now(timezone.utc))-timestamp).total_seconds()
        if timestamp.tzinfo is None or age < -60 or age > 5400:
            return {'state': 'stale', 'off_host': False}
        return {key: value.get(key) for key in ('state', 'last_success_at', 'snapshot_at', 'bytes', 'sha256', 'restore_verified')} | {'off_host': value.get('state') == 'ok'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'missing', 'off_host': False}


def package_snapshot(directory, destination):
    directory = Path(directory).resolve()
    candidates = sorted(directory.glob('*.json'))
    if not candidates:
        raise ValueError('No verified backup manifest exists')
    manifest = candidates[-1]
    if manifest.stat().st_size > 65536:
        raise ValueError('Oversized backup manifest')
    metadata = json.loads(manifest.read_text())
    if metadata.get('state') != 'ok' or not 1 <= len(metadata.get('files', [])) <= 3:
        raise ValueError('Invalid backup manifest')
    stamp = datetime.fromisoformat(metadata['at'])
    if stamp.tzinfo is None or not -60 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 5400:
        raise ValueError('Refuse stale or future-dated backup snapshot')
    paths, total = [], 0
    for item in metadata['files']:
        name = item['file']
        path = directory/name
        if not isinstance(name, str) or Path(name).name != name or path.is_symlink() or path.resolve().parent != directory:
            raise ValueError('Unsafe backup filename')
        if not name.endswith(SNAPSHOT_SUFFIXES):
            raise ValueError('Only paper and operations snapshots may leave the VM')
        size = path.stat().st_size
        total += size
        if total > MAX_RESTORE_BYTES or size != item['bytes']:
            raise ValueError('Backup size limit or manifest mismatch')
        if sha256_file(path) != item['sha256']:
            raise ValueError('Backup checksum mismatch')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup database integrity failure')
        paths.append(path)
    with tarfile.open(destination, 'w:gz') as archive:
        for path in [manifest, *paths]:
            archive.add(path, arcname=path.name, recursive=False)
    os.chmod(destination, 0o600)
    if Path(destination).stat().st_size > MAX_BYTES:
        raise ValueError('Compressed backup exceeds configured limit')
    return metadata, manifest.stem+'.tar.gz'


def managed_token():
    url = 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(urllib.request.Request(url, headers={'Metadata': 'true'}), timeout=10) as response:
        result = json.loads(response.read(65536))
    return result['access_token']


class BlobStore:
    def __init__(self, account, container='paper-recovery', token=None):
        if not re.fullmatch(r'[a-z0-9]{3,24}', account) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])', container):
            raise ValueError('Invalid private Azure storage destination')
        self.origin = f'https://{account}.blob.core.windows.net/{container}'
        self.token = token or managed_token()
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, name, data=None, extra=None):
        if not re.fullmatch(r'accounts/\d{4}/\d{2}/\d{2}/[A-Za-z0-9-]+\.tar\.gz', name):
            raise ValueError('Invalid backup object name')
        headers = {'Authorization': 'Bearer '+self.token, 'x-ms-version': VERSION,
                   'x-ms-date': email.utils.format_datetime(datetime.now(timezone.utc), usegmt=True), **(extra or {})}
        for attempt in range(4):
            try:
                return self.opener.open(urllib.request.Request(self.origin+'/'+name, data=data, headers=headers, method=method), timeout=30)
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                if code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f'Azure backup request failed: HTTP {code}') from None
            except urllib.error.URLError:
                if attempt == 3:
                    raise RuntimeError('Azure backup connection failed') from None
            time.sleep(2**attempt)

    def upload(self, name, payload, digest):
        # Deterministic names make retries overwrite the SAME verified archive;
        # no ledger operation is ever retried or coupled to this job.
        with self.request('PUT', name, payload, {'x-ms-blob-type': 'BlockBlob', 'x-ms-meta-sha256': digest,
                                                'Content-Type': 'application/gzip'}) as response:
            if response.status != 201:
                raise RuntimeError('Unexpected Azure backup upload response')
        with self.request('GET', name) as response:
            stored = response.read(MAX_BYTES+1)
        if len(stored) != len(payload) or hashlib.sha256(stored).hexdigest() != digest:
            raise ValueError('Remote backup round-trip checksum mismatch')
        return stored


def verify_restore(payload):
    if len(payload)>MAX_BYTES:raise ValueError('Compressed recovery archive exceeds limit')
    with tempfile.TemporaryDirectory(prefix='league-restore-check-') as root:
        root = Path(root)
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
            members = archive.getmembers()
            if not 2 <= len(members) <= 4 or sum(m.size for m in members) > MAX_RESTORE_BYTES or len({m.name for m in members}) != len(members):
                raise ValueError('Invalid recovery archive size')
            if shutil.disk_usage(root).free < sum(m.size for m in members)+1024**3:
                raise OSError('Insufficient space for isolated restore with trading headroom')
            for member in members:
                if not member.isfile() or Path(member.name).name != member.name:
                    raise ValueError('Unsafe recovery archive member')
                with archive.extractfile(member) as source:
                    with (root/member.name).open('wb') as target:
                        shutil.copyfileobj(source,target,length=1024*1024)
        manifests = list(root.glob('*.json'))
        if len(manifests) != 1:
            raise ValueError('Missing recovery manifest')
        if manifests[0].stat().st_size > 65536:
            raise ValueError('Oversized recovery manifest')
        metadata = json.loads(manifests[0].read_text())
        files = metadata.get('files', [])
        if metadata.get('state') != 'ok' or not 1 <= len(files) <= 3:
            raise ValueError('Invalid recovery manifest')
        names = [item['file'] for item in files]
        if len(set(names)) != len(names) or set(names) | {manifests[0].name} != {m.name for m in members}:
            raise ValueError('Recovery manifest members mismatch')
        for item in metadata['files']:
            name = item['file']
            if not isinstance(name,str) or Path(name).name != name or not name.endswith(SNAPSHOT_SUFFIXES):
                raise ValueError('Unsafe recovery manifest')
            path = root/name
            if path.stat().st_size != item['bytes'] or sha256_file(path) != item['sha256']:
                raise ValueError('Restored snapshot checksum mismatch')
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Restored snapshot integrity failure')
    return True


def run(directory, status_path, store):
    with tempfile.TemporaryDirectory(prefix='league-offhost-') as temp:
        output = Path(temp)/'account.tar.gz'
        metadata, name = package_snapshot(directory, output)
        payload = output.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        stamp = datetime.fromisoformat(metadata['at'])
        object_name = stamp.strftime('accounts/%Y/%m/%d/')+name
        restored = store.upload(object_name, payload, digest)
        verify_restore(restored)
        value = {'state': 'ok', 'off_host': True, 'last_success_at': datetime.now(timezone.utc).isoformat(),
                 'snapshot_at': metadata['at'], 'bytes': len(payload), 'sha256': digest, 'restore_verified': True}
        atomic_json(status_path, value)
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--state', type=Path, default=Path('/srv/league/state/paper'))
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True)
    status_path = args.state/'offhost-backup.json'
    with (args.state/'offhost-backup.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = run(args.state/'backups', status_path, BlobStore(args.account))
            print(json.dumps(result, allow_nan=False))
        except Exception as error:
            try:
                old = json.loads(status_path.read_text())
            except (ValueError, OSError):
                old = {}
            atomic_json(status_path, {'state': 'error', 'off_host': False, 'last_success_at': old.get('last_success_at'),
                                      'error_kind': type(error).__name__})
            raise SystemExit('Off-host backup failed; inspect private VM service logs.') from None


if __name__ == '__main__':
    main()
