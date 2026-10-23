"""Small safe malformed inputs and genuine patched decoder lifecycle checks."""
from dataclasses import replace
from pathlib import Path
import sys
import time

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_alignment_real import inputs, auth, digest, TOOL
from test_workspace import wait

pytestmark=pytest.mark.skipif(not TOOL,reason='Genuine patched SAMtools required; mandatory in provisioned CI')


@pytest.mark.parametrize('kind,fault',[('cram','truncated'),('cram','unsupported-version'),('bam','empty-body')])
def test_safe_malformed_data_never_publishes_completed_evidence(inputs,kind,fault):
    config,bam,cram,ref=inputs
    source=cram if kind=='cram' else bam
    raw=source.read_bytes()
    if fault=='truncated':raw=raw[:30]
    elif fault=='unsupported-version':raw=raw[:4]+b'\x04\x00'+raw[6:]
    else:raw=raw[:int.from_bytes(raw[16:18],'little')+1]
    malformed=source.with_name('safe-malformed.'+kind);malformed.write_bytes(raw)
    before=digest(malformed)
    with TestClient(create_app(config)) as c:
        auth(c,config)
        response=c.post('/api/runs',json={'mode':'samtools','paths':[str(malformed)],'qc_options':{'reference':'test' if kind=='cram' else None}})
        assert response.status_code in {201,400},response.text
        if response.status_code==201:
            run=wait(c,response.json()['id'])
            assert run['state']=='failed' and run['sample_count']==0
            assert not any(r['path'].startswith('qc/') for r in run['reports'])
            for execution in run['executions']:
                if execution.get('stdout'):
                    assert c.get(f'/api/runs/{run["id"]}/download',params={'path':execution['stdout']}).status_code==403
    assert digest(malformed)==before


@pytest.mark.parametrize('changed',['fasta','fai','removed'])
def test_reference_identity_change_during_genuine_cram_decode_fails_closed(inputs,changed):
    config,bam,cram,ref=inputs
    marker=ref.parent/'waiting-for-decoder'
    release=ref.parent/'release-decoder'
    launcher=ref.parent/'held-samtools'
    interpreter=sys.executable
    launcher.write_text(f'#!{interpreter}\nimport os,sys,time\nfrom pathlib import Path\nif "stats" in sys.argv:\n Path({str(marker)!r}).touch()\n while not Path({str(release)!r}).exists():time.sleep(.02)\nos.execv({TOOL!r},[{TOOL!r},*sys.argv[1:]])\n')
    launcher.chmod(0o700);config=replace(config,samtools=str(launcher))
    with TestClient(create_app(config)) as c:
        auth(c,config)
        response=c.post('/api/runs',json={'mode':'samtools','paths':[str(cram)],'qc_options':{'reference':'test'}})
        assert response.status_code==201,response.text
        for _ in range(300):
            if marker.exists():break
            time.sleep(.02)
        else:raise AssertionError('Genuine CRAM decoder stages not reached')
        if changed=='removed':ref.unlink()
        else:
            target=ref if changed=='fasta' else Path(str(ref)+'.fai')
            target.write_bytes(target.read_bytes()+b'\n')
        release.touch()
        run=wait(c,response.json()['id'])
        assert run['state']=='failed' and not run['sample_count']
        assert not any(r['path'].startswith('qc/') for r in run['reports'])
