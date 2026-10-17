"""Actual SAMtools; source SAM is explicit synthetic metadata, not invented QC."""
from dataclasses import replace
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

TOOL = shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS', 'samtools'))
if os.environ.get('QUALIDOCK_REQUIRE_ALIGNMENT_TESTS') == '1' and not TOOL:
    raise RuntimeError('Actual SAMtools required')
pytestmark = pytest.mark.skipif(not TOOL, reason='Actual SAMtools unavailable')
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_alignment', ROOT/'scripts/prepare-alignment-test.py')
fixture = importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


@pytest.fixture
def inputs(tmp_path):
    bam, cram, ref = fixture.prepare(tmp_path/'inputs', TOOL)
    config = Settings(roots=[tmp_path/'inputs'], output=tmp_path/'results', frontend=tmp_path/'frontend', token='alignment-test',
                      samtools=TOOL, alignment_references={'test': str(ref)}, cpus=1, memory_mb=2048, allow_root=True)
    return config, bam, cram, ref


def auth(c, config):
    c.headers.update({'Authorization': 'Bearer '+config.token, 'X-QualiDock-Request': '1'})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('kind', ['bam', 'cram'])
def test_actual_reports_metrics_multicq_provenance_and_restart(inputs, kind):
    config, bam, cram, ref = inputs
    source = bam if kind == 'bam' else cram
    # Test-only index generation verifies existing sidecars also remain unchanged.
    subprocess.run([TOOL, 'index', str(source)], check=True, capture_output=True)
    hashes = {p: digest(p) for p in source.parent.iterdir()}
    expected = subprocess.run([TOOL, 'flagstat', str(source)], check=True, capture_output=True).stdout
    with TestClient(create_app(config)) as c:
        auth(c, config)
        listing = c.get('/api/files', params={'path': str(source.parent)}).json()
        entry = next(e for e in listing['entries'] if e['name'] == source.name)
        assert entry['kind'] == 'alignment' and entry['read'] is None and not entry['paired']
        created = c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(source)], 'qc_options': {'reference': 'test' if kind == 'cram' else None, 'multiqc': bool(shutil.which(config.multiqc))}})
        assert created.status_code == 201, created.text
        run = wait(c, created.json()['id'], timeout=60)
        assert run['state'] == 'completed', run['error']
        assert run['tools']['samtools']['version'] == run['tools']['samtools']['htslib_version'] == '1.22.1'
        assert not run['input_pairing'] and not run['sample_groups'] and not run.get('derived_datasets')
        row = run['qc']['results'][0]; data = row['alignment']
        assert data['quickcheck'] == 'passed (header/EOF only)'
        assert data['flagstat']['rows'][0] == ['in total (QC-passed reads + QC-failed reads)', '7', '1']
        stats = dict((r[0], r[1]) for r in data['stats']['rows'])
        assert stats['raw total sequences:'] == '6' and stats['reads mapped:'] == '5' and stats['total length:'] == '40'
        downloaded = c.get(f'/api/runs/{run["id"]}/download', params={'path': data['reports']['flagstat']})
        assert downloaded.status_code == 200 and downloaded.content == expected
        assert not any(e['argv'][1] in {'index', 'sort', 'view', 'faidx'} for e in run['executions'] if e['tool'] == 'samtools')
        assert all(e['environment']['REF_PATH'] == '/dev/null' and e['environment']['REF_CACHE'] == '/dev/null' for e in run['executions'] if e['tool'] == 'samtools')
        if 'multiqc' in run['tools']:
            assert all(v.get('multiqc_name') for v in run['report_input_map'].values())
            assert len(set(v['multiqc_name'] for v in run['report_input_map'].values())) == 1
        assert c.get(f'/api/runs/{run["id"]}/configuration').json()['mode'] == 'samtools'
        assert c.get('/api/history?mode=samtools').json()['total'] == 1
        retained = Path('validation/alignment')/kind
        shutil.copytree(config.output/run['id'], retained, dirs_exist_ok=True)
    with TestClient(create_app(config)) as c:
        auth(c, config)
        assert c.get(f'/api/runs/{run["id"]}').json()['qc'] == run['qc']
        assert c.get(f'/api/runs/{run["id"]}/download', params={'path': data['reports']['stats']}).status_code == 200
    assert hashes == {p: digest(p) for p in source.parent.iterdir()}


def test_bad_reference_and_missing_reference(inputs):
    config, bam, cram, ref = inputs
    with TestClient(create_app(config)) as c:
        auth(c, config)
        assert c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(cram)]}).status_code == 400
    wrong = ref.parent/'wrong.fa'
    wrong.write_text(ref.read_text().replace('A', 'T'))
    subprocess.run([TOOL, 'faidx', str(wrong)], check=True)
    config = replace(config, alignment_references={'wrong': str(wrong)})
    before = {p: digest(p) for p in ref.parent.iterdir()}
    with TestClient(create_app(config)) as c:
        auth(c, config)
        r = c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(cram)], 'qc_options': {'reference': 'wrong'}})
        assert r.status_code == 201, r.text
        run = wait(c, r.json()['id'])
        assert run['state'] == 'failed' and 'stats exited' in run['error']
        assert not any(p['path'].startswith('qc/') for p in run['reports'])
    assert before == {p: digest(p) for p in ref.parent.iterdir()}


def test_truncated_bam_partial_and_security(inputs):
    config, bam, cram, ref = inputs
    bad = bam.parent/'truncated.bam';bad.write_bytes(bam.read_bytes()[:-28])
    escaped = bam.parent/'escape.bam';escaped.symlink_to('/etc/passwd')
    renamed = bam.parent/'text.bam';renamed.write_text('not BAM')
    with TestClient(create_app(config)) as c:
        assert c.get('/api/config').status_code == 401
        auth(c, config)
        for path in (escaped, renamed, bam.parent/'..'/'outside.bam'):
            assert c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(path)]}).status_code in {400, 403}
        assert c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(bam)], 'input_pairing': [{'path': str(bam), 'assignment': 'single'}]}).status_code == 400
        r = c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(bam), str(bad)]})
        assert r.status_code == 201, r.text
        run = wait(c, r.json()['id'])
        assert run['state'] == 'partial' and run['sample_count'] == 1
        failed = next(row for row in run['qc']['results'] if row['state'] == 'failed')
        assert 'quickcheck' in failed['error']
        assert c.get(f'/api/runs/{run["id"]}/download', params={'path': failed['report']}).status_code == 403
        assert c.get(f'/api/runs/{run["id"]}/download', params={'path': '../input.bam'}).status_code == 403


def test_cancellation_does_not_publish_partial_reports(inputs):
    config, bam, cram, ref = inputs
    launcher = bam.parent/'slow-samtools'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "stats" in sys.argv: time.sleep(30)\nos.execv({TOOL!r}, [{TOOL!r},*sys.argv[1:]])\n')
    launcher.chmod(0o700);config = replace(config, samtools=str(launcher))
    with TestClient(create_app(config)) as c:
        auth(c, config)
        r = c.post('/api/runs', json={'mode': 'samtools', 'paths': [str(bam)]})
        assert r.status_code == 201, r.text
        for _ in range(200):
            run = c.get('/api/runs/'+r.json()['id']).json()
            if any(e['argv'][1] == 'stats' for e in run['executions']):
                break
            time.sleep(.02)
        else:
            raise AssertionError('Actual SAMtools stages not reached')
        assert c.post(f'/api/runs/{run["id"]}/cancel').status_code == 200
        stopped = wait(c, run['id'])
        assert stopped['state'] == 'cancelled'
        assert not any(p['path'].startswith('qc/') for p in stopped['reports'])


def test_internal_corruption_is_not_proved_valid_by_quickcheck(inputs):
    config,bam,cram,ref=inputs
    content=bytearray(bam.read_bytes())
    # Preserve the initial header block and final EOF, corrupt the body block.
    first=int.from_bytes(content[16:18],'little')+1
    assert content[first:first+2]==b'\x1f\x8b'
    content[first+20]^=255
    broken=bam.parent/'internal-corruption.bam';broken.write_bytes(content)
    assert subprocess.run([TOOL,'quickcheck',str(broken)],capture_output=True).returncode==0
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'samtools','paths':[str(broken)]})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and not run['sample_count']
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


def test_cram_does_not_use_remote_search_or_write_reference_cache(inputs,monkeypatch):
    import http.server
    import threading
    config,bam,cram,ref=inputs
    requests=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path);self.send_response(404);self.end_headers()
        def log_message(self,*args):pass
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        remote=f'http://127.0.0.1:{server.server_port}/%s'
        monkeypatch.setenv('REF_PATH',remote)
        cache=ref.parent/'unwanted-cache'
        monkeypatch.setenv('REF_CACHE',str(cache/'%2s/%2s/%s'))
        try:
            with TestClient(create_app(config)) as c:
                auth(c,config)
                created=c.post('/api/runs',json={'mode':'samtools','paths':[str(cram)],'qc_options':{'reference':'test'}})
                run=wait(c,created.json()['id'])
                assert run['state']=='completed',run['error']
            assert requests==[] and not cache.exists()
        finally:
            server.shutdown();thread.join()


def test_interrupted_alignment_restores_truthfully(inputs):
    config,bam,cram,ref=inputs
    launcher=bam.parent/'slow-samtools'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "stats" in sys.argv: time.sleep(30)\nos.execv({TOOL!r}, [{TOOL!r},*sys.argv[1:]])\n')
    launcher.chmod(0o700);config=replace(config,samtools=str(launcher))
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'samtools','paths':[str(bam)]})
        for _ in range(200):
            run=c.get('/api/runs/'+created.json()['id']).json()
            if any(e['argv'][1]=='stats' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Real stages not reached')
    with TestClient(create_app(config)) as c:
        auth(c,config)
        restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']=='interrupted'
        assert restored['qc']['results'][0]['state']=='interrupted'
        assert not any(r['path'].startswith('qc/') for r in restored['reports'])


def test_hostile_and_colliding_filenames_preserve_multiqc_sources(inputs):
    config,bam,cram,ref=inputs
    if not shutil.which(config.multiqc):
        pytest.skip('Actual MultiQC unavailable; required compatibility CI installs it')
    names=[]
    for directory in ('one','two'):
        folder=bam.parent/directory;folder.mkdir()
        p=folder/'reads $(touch INJECTED) <sample>.bam';shutil.copyfile(bam,p);names.append(str(p))
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'samtools','paths':names,'qc_options':{'multiqc':True}})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        mappings=run['report_input_map']
        assert len(mappings)==4 and len({r['multiqc_name'] for r in mappings.values()})==2
        assert {r['path'] for r in mappings.values()}==set(names)
        # Private/failed namespaces and arbitrary paths never become attachments.
        artifact=next(r['path'] for r in run['reports'] if r['path'].endswith('.stats.txt'))
        result=config.output/run['id']/artifact;result.unlink();result.symlink_to(bam)
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':artifact}).status_code==403
        assert c.post(f'/api/runs/{run["id"]}/integrity',json={'mode':'full'}).status_code==400
    assert not list(bam.parent.rglob('INJECTED'))
