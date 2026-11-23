"""Verify the normalized Sites publication archive against the checked build inventory."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def check(archive_path, audit_path):
    audit = json.loads(Path(audit_path).read_text())
    with tarfile.open(archive_path) as archive:
        files = {}
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or any(p.startswith('._') for p in path.parts):
                raise ValueError('Unsafe path or metadata sidecar in publication archive')
            if not member.isdir() and not member.isfile():
                raise ValueError('Links and special archive members are forbidden')
            if member.isfile():
                name = str(path)
                if name in files:
                    raise ValueError('Duplicate archive member')
                files[name] = member
        # Sites' helper normalizes supported static source directories to dist.
        expected = {'dist/.openai/hosting.json', *('dist/' + row['file'] for row in audit['files'])}
        if set(files) != expected:
            raise ValueError('Publication archive differs from the approved file inventory')
        manifest = json.load(archive.extractfile(files['dist/.openai/hosting.json']))
        source_manifest = json.loads((Path(audit_path).parent / '.openai/hosting.json').read_text())
        if manifest.get('project_id') != source_manifest.get('project_id') or manifest.get('static') != {'directory': 'dist'}:
            raise ValueError('Publication manifest is not for the expected static Site')
        for row in audit['files']:
            member = files['dist/' + row['file']]
            if member.size != row['bytes'] or member.size > 32 * 1024**2:
                raise ValueError('Publication size differs from checked build')
            digest = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            if digest != row['sha256']:
                raise ValueError('Publication bytes differ from checked build')
    print(f'Publication archive verified: manifest + {len(audit["files"])} approved files; matching hashes, no sidecars or private paths.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--audit', default=str(Path(__file__).resolve().parents[1] / 'dashboard/release-audit.json'))
    args = parser.parse_args()
    check(args.archive, args.audit)
