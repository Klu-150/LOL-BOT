"""Download compatible Linux/Python 3.12 wheels concurrently, verifying lock hashes.

This reads fully pinned hash locks; it does not resolve or change dependencies.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'deployment/wheelhouse'
PLATFORMS=['manylinux_2_28_x86_64','manylinux2014_x86_64','manylinux_2_17_x86_64']
TAGS=set(cpython_tags((3,12),abis=['cp312'],platforms=PLATFORMS))|set(compatible_tags((3,12),interpreter='cp312',platforms=PLATFORMS))


def specifications():
    for lock in ['requirements-bootstrap.lock','requirements-cloud.lock']:
        text=(ROOT/lock).read_text().replace('\\\n','')
        for line in text.splitlines():
            match=re.match(r'^([\w.-]+)==([\w.+-]+)\s+(.*)$',line)
            if match:
                name,version,rest=match.groups();hashes=set(re.findall(r'--hash=sha256:([0-9a-f]{64})',rest))
                if not hashes:raise ValueError('Unhashed dependency: '+name)
                yield name,version,hashes


def fetch(spec):
    name,version,hashes=spec
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:metadata=json.load(response)
    candidates=[]
    for item in metadata['urls']:
        if item['packagetype']!='bdist_wheel' or item['digests']['sha256'] not in hashes:continue
        if parse_wheel_filename(item['filename'])[3]&TAGS:candidates.append(item)
    if not candidates:raise ValueError('No locked Linux/Python 3.12 wheel for '+name)
    wheel=min(candidates,key=lambda item:item['size'])
    target=DEST/wheel['filename'];digest=wheel['digests']['sha256']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:return target.name
    temporary=target.with_suffix('.part');hasher=hashlib.sha256()
    try:
        with urllib.request.urlopen(wheel['url'],timeout=60) as response,temporary.open('wb') as output:
            while chunk:=response.read(1024*128):output.write(chunk);hasher.update(chunk)
        if hasher.hexdigest()!=digest:raise ValueError('Wheel checksum mismatch: '+name)
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)
    return target.name


if __name__=='__main__':
    DEST.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for filename in pool.map(fetch,list(specifications())):print('Verified '+filename,flush=True)
