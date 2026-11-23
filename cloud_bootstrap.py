"""Seed an empty persistent volume, preserving every existing account/data file."""
from pathlib import Path
import os
import shutil

ROOT = Path(__file__).resolve().parent
def seed_storage(state, root=ROOT):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    for name in ('paper', 'data', 'results'):
        target = state / name
        target.mkdir(exist_ok=True)
        seed = root / ('seed-' + name)
        if seed.exists():
            for item in seed.rglob('*'):
                relative = item.relative_to(seed)
                destination = target / relative
                if item.is_dir():
                    destination.mkdir(exist_ok=True)
                elif not destination.exists():
                    shutil.copy2(item, destination)

if __name__ == '__main__':
    seed_storage('/state')
    # New mounted disks may be root-owned. Drop privileges before serving HTTP.
    if os.getuid() == 0:
        for directory, folders, files in os.walk('/state'):
            os.chown(directory, 10001, 10001, follow_symlinks=False)
            for name in folders + files:
                os.chown(Path(directory) / name, 10001, 10001, follow_symlinks=False)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:' + os.environ.get('PORT', '8765'),
                           '--workers', '1', '--threads', '4', '--timeout', '120', '--graceful-timeout', '70',
                           '--limit-request-line', '2048', '--limit-request-fields', '30', '--limit-request-field_size', '4096',
                           'cloud_server:create_app()'])
