"""Package only deployment inputs, excluding account databases and access keys."""
import hashlib
import argparse
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / 'deployment/league-engine-source.tar.gz'
INPUTS = ['Dockerfile', 'requirements.txt', 'requirements-cloud.txt', 'requirements-cloud.lock', 'requirements-bootstrap.lock', 'deployment/wheelhouse', 'events.csv',
          'TRADING_PLAN.md', 'deployment/recovery-drill.sh', 'research', 'tools', 'data', 'results', 'dashboard/dist']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-wheels',action='store_true',help='Operator supplies a verified VM wheel cache to the installer')
    args=parser.parse_args()
    inputs=[name for name in INPUTS if not args.without_wheels or name!='deployment/wheelhouse']
    with tarfile.open(ARCHIVE, 'w:gz') as archive:
        for item in [*ROOT.glob('*.py'), *(ROOT / name for name in inputs)]:
            archive.add(item, arcname=str(item.relative_to(ROOT)),
                        filter=lambda entry: None if '__pycache__' in Path(entry.name).parts else entry)
    with tarfile.open(ARCHIVE) as archive:
        names = set(archive.getnames())
        assert 'events.csv' in names and 'TRADING_PLAN.md' in names
        assert not any(name.startswith('paper/') or name.endswith('.sqlite3') for name in names)
    print(f'{ARCHIVE.name}: {hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()}')
