"""Collect notices from the exact hash-locked cloud wheels, without executing them."""
import hashlib
import json
import re
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect():
    locks = '\n'.join((ROOT / name).read_text() for name in
                      ('requirements-cloud.lock', 'requirements-bootstrap.lock'))
    pinned = {(name.lower().replace('_', '-'), version) for name, version in
              re.findall(r'^([A-Za-z0-9_-]+)==([^\s\\]+)', locks, re.M)}
    allowed = set(re.findall(r'--hash=sha256:([a-f0-9]{64})', locks))
    records, notices, found = [], [], set()
    for wheel in sorted((ROOT / 'deployment/wheelhouse').glob('*.whl')):
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest not in allowed:
            raise ValueError('Unpinned wheel: ' + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            metadata_paths = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(metadata_paths) != 1:
                raise ValueError('Ambiguous metadata: ' + wheel.name)
            metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
            name, version = metadata['Name'], metadata['Version']
            identity = (name.lower().replace('_', '-'), version)
            if identity not in pinned or identity in found:
                raise ValueError('Unexpected or duplicated package: ' + wheel.name)
            found.add(identity)
            license_files = [item for item in archive.infolist() if not item.is_dir() and
                             re.search(r'(^|/)(license|licence|copying|notice)([._-]|$)', item.filename, re.I)]
            if not license_files:
                raise ValueError('No bundled license found: ' + wheel.name)
            if sum(item.file_size for item in license_files) > 20 * 1024**2:
                raise ValueError('License text bound exceeded')
            records.append({'name': name, 'version': version, 'wheel': wheel.name,
                            'sha256': digest, 'license_expression': metadata.get('License-Expression'),
                            'license_classifiers': [v for v in metadata.get_all('Classifier', []) if v.startswith('License ::')],
                            'license_files': [item.filename for item in license_files]})
            notices.append('\n' + '=' * 72 + f'\n{name} {version}\nWheel SHA256: {digest}\n')
            for item in license_files:
                notices.extend(['\n--- ' + item.filename + ' ---\n',
                                archive.read(item).decode('utf-8', errors='replace')])
    if pinned != found:
        raise ValueError('Missing pinned wheels: ' + str(sorted(pinned - found)))
    document = {'checked_on': '2026-11-23', 'scope': 'Locked cloud and bootstrap wheels only',
                'legal_approval': False, 'packages': records,
                'excluded': ['Container/OS components', 'Hosting agreements', 'Market-data rights',
                             'Application/dissertation/brand ownership']}
    (ROOT / 'legal/dependency-inventory.json').write_text(json.dumps(document, indent=2) + '\n')
    header = ('Last of Our League — third-party Python wheel notices\n'
              'Generated from hash-locked deployment wheels on 23 November 2026.\n'
              'Licenses belong to their respective authors. Includes bundled notices where supplied.\n'
              'Inventory is not legal approval and excludes OS/container and service agreements.\n')
    (ROOT / 'dashboard/dist/third-party-notices.txt').write_text(header + '\n'.join(notices))
    print(f'Verified hashes and retained license notices for {len(records)} pinned wheels.')


if __name__ == '__main__':
    collect()
