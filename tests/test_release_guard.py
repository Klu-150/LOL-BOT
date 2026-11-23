import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def test_failed_candidate_build_never_stops_or_replaces_existing_engine(tmp_path):
    root=tmp_path/'server';root.mkdir();(root/'releases').mkdir();(root/'source').mkdir();(root/'source'/'old').write_text('running release')
    upload=tmp_path/'upload';upload.mkdir();archive=upload/'league-engine-source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        value=b'FROM python:3.12-slim\n';member=tarfile.TarInfo('Dockerfile');member.size=len(value);tar.addfile(member,io.BytesIO(value))
    commands=tmp_path/'bin';commands.mkdir();log=tmp_path/'docker.log'
    scripts={'docker':'#!/bin/sh\nprintf "%s\\n" "$*" >> "$RELEASE_TEST_LOG"\nexit 42\n',
             'flock':'#!/bin/sh\nexit 0\n',
             'sha256sum':f'#!{sys.executable}\nimport hashlib,sys\nprint(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()+"  "+sys.argv[1])\n'}
    for name,body in scripts.items():
        p=commands/name;p.write_text(body);p.chmod(0o700)
    script=Path(__file__).resolve().parents[1]/'deployment/install-production-release.sh'
    result=subprocess.run(['bash',str(script),'20261122T100000Z',hashlib.sha256(archive.read_bytes()).hexdigest(),'1.2.0'],
        env={**os.environ,'PATH':str(commands)+os.pathsep+os.environ['PATH'],'LEAGUE_DEPLOY_ROOT':str(root),
             'LEAGUE_DEPLOY_UPLOAD':str(upload),'RELEASE_TEST_LOG':str(log)},capture_output=True,text=True)
    assert result.returncode==42,result.stderr
    calls=log.read_text().splitlines();assert len(calls)==1 and calls[0].startswith('build ')
    assert (root/'source'/'old').read_text()=='running release'
    assert not (root/'state').exists()
