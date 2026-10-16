"""Actual nanoq 0.10.0, source validation, authorization and shared lifecycle."""
from dataclasses import replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

FIXTURE = Path(__file__).parent / 'fixtures/nanoq-0.10.0'
NANOQ = shutil.which(os.environ.get('QUALIDOCK_NANOQ', 'nanoq'))
if os.environ.get('QUALIDOCK_REQUIRE_OPTIONAL_QC_TESTS') == '1' and not NANOQ:
    raise RuntimeError('Actual nanoq required')
pytestmark = pytest.mark.skipif(not NANOQ, reason='Actual nanoq unavailable')


def settings(tmp_path):
    return Settings(roots=[FIXTURE.resolve(), tmp_path.resolve()], output=tmp_path/'results', frontend=tmp_path/'frontend',
                    token='optional-qc-test', nanoq=NANOQ, cpus=1, memory_mb=2048, allow_root=True)


def auth(client, config):
    client.headers.update({'Authorization': 'Bearer '+config.token, 'X-QualiDock-Request': '1'})


@pytest.mark.parametrize('compressed', [True, False])
def test_actual_nanoq_json_sources_download_restart(tmp_path, compressed):
    config=settings(tmp_path)
    source=tmp_path/'source $(touch INJECTED).fastq'
    source.write_bytes(gzip.decompress((FIXTURE/'ont.fastq.gz').read_bytes()))
    if compressed: source=FIXTURE/'ont.fastq.gz'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'nanoq','paths':[str(source.resolve())]})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id']);assert run['state']=='completed',run['error']
        row=run['qc']['results'][0]
        assert row['summary']==json.loads((FIXTURE/'nanoq.json').read_text())
        assert row['source_sha256']==before and run['sample_count']==1
        assert run['tools']['nanoq']['version']=='0.10.0'
        assert not run.get('derived_datasets') and not (config.output/run['id']/'INJECTED').exists()
        argv=next(e['argv'] for e in run['executions'] if e['tool']=='nanoq')
        assert '--stats' in argv and '--json' in argv and '--fast' not in argv
        download=client.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']})
        assert download.status_code==200 and download.json()==row['summary']
        assert 'attachment' in download.headers['content-disposition']
        assert not any(r['path'].startswith('qc/private/') for r in run['reports'])
        assert client.post('/api/runs',json={'mode':'nanoq','paths':['/etc/passwd']}).status_code==403
        assert client.get('/api/history?mode=nanoq').json()['total']==1
    with TestClient(create_app(config)) as client:
        auth(client,config)
        restored=client.get(f'/api/runs/{run["id"]}').json()
        assert restored['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/metrics').json()['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/configuration').json()['mode']=='nanoq'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('content', [b'', b'@x\nACGT\n+\nI\n', b'not gzip'])
def test_actual_invalid_input_does_not_publish(tmp_path, content):
    config=settings(tmp_path);source=tmp_path/'broken.fastq.gz'
    source.write_bytes(content if content==b'not gzip' else gzip.compress(content))
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'nanoq','paths':[str(source)]})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'])
        assert run['state']=='failed' and run['sample_count']==0
        assert run['qc']['results'][0]['summary'] is None
        assert not any(e['tool']=='nanoq' for e in run['executions'])
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


def test_actual_partial_collisions_and_unauthenticated(tmp_path):
    config=settings(tmp_path);paths=[]
    for folder in ('a','b'):
        root=tmp_path/folder;root.mkdir();path=root/'same.fastq.gz'
        shutil.copyfile(FIXTURE/'ont.fastq.gz',path);paths.append(str(path))
    bad=tmp_path/'bad.fastq';bad.write_bytes(b'broken');paths.append(str(bad))
    with TestClient(create_app(config)) as client:
        assert client.post('/api/runs',headers={'X-QualiDock-Request':'1'},json={'mode':'nanoq','paths':paths}).status_code==401
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'nanoq','paths':paths})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'])
        assert run['state']=='partial' and run['sample_count']==2
        completed=[r for r in run['qc']['results'] if r['state']=='completed']
        assert len({r['report'] for r in completed})==2
        assert all(r['report'] in run['report_input_map'] for r in completed)


def test_actual_validation_cancellation_and_restart(tmp_path):
    config=settings(tmp_path);source=tmp_path/'large.fastq.gz'
    with gzip.open(source,'wb') as output:
        chunk=gzip.decompress((FIXTURE/'ont.fastq.gz').read_bytes())
        for _ in range(2000): output.write(chunk)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'nanoq','paths':[str(source)]});assert response.status_code==201,response.text
        identifier=response.json()['id'];deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            run=client.get(f'/api/runs/{identifier}').json()
            if run['executions']: break
            time.sleep(.01)
        assert run['state']=='running' and run['executions']
        assert client.post(f'/api/runs/{identifier}/cancel').status_code==200
        run=wait(client,identifier);assert run['state']=='cancelled'
        assert not any(row['state']=='completed' for row in run['qc']['results'])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        assert client.get(f'/api/runs/{identifier}').json()['state']=='cancelled'


@pytest.mark.skipif(not shutil.which('fastp'), reason='Actual fastp required for derived reuse')
def test_nanoq_registered_derived_authority_and_provenance(tmp_path):
    fixture=(FIXTURE.parent/'fastqc-0.13.0').resolve()
    config=replace(settings(tmp_path), roots=[fixture])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'fastp','paths':[str(fixture/'coverage_R1.fastq.gz')],
                                             'processing_options':{'compare_qc':False}})
        assert response.status_code==201,response.text
        parent=wait(client,response.json()['id']);assert parent['state']=='completed',parent['error']
        dataset=parent['derived_datasets'][0];path=str(config.output/parent['id']/dataset['path'])
        payload={'mode':'nanoq','paths':[path]}
        assert client.post('/api/runs',json=payload).status_code==403
        payload['input_datasets']=[{'run_id':parent['id'],'dataset_id':dataset['id']}]
        response=client.post('/api/runs',json=payload);assert response.status_code==201,response.text
        child=wait(client,response.json()['id']);assert child['state']=='completed',child['error']
        assert child['qc']['results'][0]['summary']['reads']==dataset['records']
        assert child['input_provenance'][0]['run_id']==parent['id']
