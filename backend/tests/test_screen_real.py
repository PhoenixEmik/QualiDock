"""Genuine FastQ Screen and Bowtie2; only the labeled input/reference DNA is synthetic."""
from dataclasses import replace
import gzip
import hashlib
import json
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

FIXTURE=Path(__file__).parent/'fixtures/fastq-screen-0.16.0'
SCREEN=shutil.which(os.environ.get('QUALIDOCK_FASTQ_SCREEN','fastq_screen'))
BOWTIE=shutil.which(os.environ.get('QUALIDOCK_BOWTIE2','bowtie2'))
BUILDER=shutil.which(os.environ.get('QUALIDOCK_BOWTIE2_BUILD','bowtie2-build'))
if os.environ.get('QUALIDOCK_REQUIRE_SCREEN_TESTS')=='1' and not all((SCREEN,BOWTIE,BUILDER)):
    raise RuntimeError('Actual FastQ Screen, Bowtie2 and bowtie2-build required')
pytestmark=pytest.mark.skipif(not all((SCREEN,BOWTIE,BUILDER)),reason='Actual FastQ Screen and Bowtie2 required')


@pytest.fixture
def config(tmp_path):
    script=Path(__file__).resolve().parents[2]/'scripts/prepare-screen-test.py'
    subprocess.run([sys.executable,str(script),'--output',str(tmp_path/'references'),'--builder',BUILDER],check=True,capture_output=True)
    return Settings(roots=[FIXTURE.resolve(),tmp_path.resolve()],output=tmp_path/'results',frontend=tmp_path/'frontend',token='screen-tests',
                    cpus=1,memory_mb=2048,fastq_screen=SCREEN,bowtie2=BOWTIE,screen_panels={'test-panel':str(tmp_path/'references/panel.conf')},allow_root=True)


def auth(client,config):
    client.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})


def submit(client,paths,**options):
    response=client.post('/api/runs',json={'mode':'fastq-screen','paths':list(map(str,paths)), 'qc_options':{'panel':'test-panel','subset':10,**options}})
    assert response.status_code==201,response.text
    return wait(client,response.json()['id'],timeout=180)


@pytest.mark.parametrize('compressed',[True,False])
def test_actual_screen_counts_reports_immutability_restart(config,tmp_path,compressed):
    source=tmp_path/"source ' $(touch INJECTED) <sample>.fastq"
    data=(FIXTURE/'reads.fastq.gz').read_bytes()
    source.write_bytes(data if compressed else gzip.decompress(data))
    if compressed:
        renamed=source.with_name(source.name+'.gz');source.rename(renamed);source=renamed
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with TestClient(create_app(config)) as client:
        auth(client,config)
        assert client.get('/api/config').json()['screen_panels'][0]['available']
        run=submit(client,[source]);assert run['state']=='completed',run['error']
        row=run['qc']['results'][0];assert row['screen']['processed_reads']==20
        assert row['screen']['rows'][0][0:6]==['alpha','20','8','40.00','12','60.00']
        assert row['screen']['rows'][1][0:6]==['beta','20','14','70.00','6','30.00']
        assert row['screen']['no_genome_percent']=='10.00'
        assert row['source_sha256']==before and all(e['exit_code']==0 for e in row['aligner_executions'])
        official=client.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']})
        assert official.status_code==200 and official.content==(FIXTURE/'reads_screen.txt').read_bytes()
        assert any(r['path'].endswith('_screen.html') for r in run['reports'])
        html=row['report'].replace('.txt','.html')
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':html}).status_code==200
        assert not any(r['path'].startswith('qc/private/') or 'subset.fastq' in r['path'] for r in run['reports'])
        assert not list((config.output/run['id']).rglob('INJECTED'))
        assert not run.get('derived_datasets')
        assert run['tools']['fastq_screen']['version']=='0.16.0'
        assert run['qc']['reference_panel']['sha256']
        assert client.get(f'/api/runs/{run["id"]}/configuration').json()['qc_options']==run['qc']['options']
    with TestClient(create_app(config)) as client:
        auth(client,config)
        restored=client.get(f'/api/runs/{run["id"]}').json()
        assert restored['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']}).content==official.content
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.skipif(not shutil.which('multiqc'),reason='Actual MultiQC required')
def test_actual_screen_multiqc_source_mapping_and_independent_mates(config,tmp_path):
    paths=[]
    for n in (1,2):
        folder=tmp_path/str(n);folder.mkdir();p=folder/'same.fastq.gz';shutil.copyfile(FIXTURE/'reads.fastq.gz',p);paths.append(p)
    with TestClient(create_app(config)) as client:
        auth(client,config);run=submit(client,paths,multiqc=True)
        assert run['state']=='completed',run['error']
        assert run['sample_count']==2 and len(run['qc']['results'])==2
        metrics=client.get(f'/api/runs/{run["id"]}/metrics').json()
        assert metrics['multiqc']['rows']==[]  # Upstream module does not contribute General Statistics.
        structured=json.loads((config.output/run['id']/'multiqc/multiqc_data/multiqc_data.json').read_text())
        actual=structured['report_saved_raw_data']['multiqc_fastq_screen']
        assert len(actual)==2 and all(row['total_reads']==20 and row['alpha counts']==12 for row in actual.values())
        configuration=json.loads((config.output/run['id']/'multiqc-config.json').read_text())
        assert configuration['preserve_module_raw_data'] is True
        assert len({mapping['multiqc_name'] for mapping in run['report_input_map'].values()})==2


def test_named_mates_with_reordered_ids_are_explicitly_independent(config,tmp_path):
    lines=gzip.decompress((FIXTURE/'reads.fastq.gz').read_bytes()).splitlines(keepends=True)
    records=[b''.join(lines[i:i+4]) for i in range(0,len(lines),4)]
    paths=[]
    for number,data in [(1,b''.join(records)),(2,b''.join(reversed(records)))]:
        p=tmp_path/f'screen_R{number}_001.fastq.gz';p.write_bytes(gzip.compress(data));paths.append(p)
    with TestClient(create_app(config)) as client:
        auth(client,config);run=submit(client,paths)
        assert run['state']=='completed',run['error']
        assert len(run['qc']['results'])==2 and all(row['screen']['processed_reads']==20 for row in run['qc']['results'])
        assert len(run['input_pairing'])==2 and all(row['paired'] for row in run['input_pairing'])
        assert all('--paired' not in e['argv'] for e in run['executions'] if e['tool']=='fastq_screen')


def test_actual_corrupt_index_exit_is_not_an_unmapped_result(config,tmp_path):
    # All six files exist, so only the actual aligner's failure can catch corruption.
    (tmp_path/'references/alpha.1.bt2').write_bytes(b'corrupt index')
    with TestClient(create_app(config)) as client:
        auth(client,config);run=submit(client,[FIXTURE.resolve()/'reads.fastq.gz'])
        assert run['state']=='failed' and run['sample_count']==0
        assert 'alignment failed' in run['error']
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


def test_actual_ambiguous_reference_hits_are_not_unique_assignments(config,tmp_path):
    # Deliberately overlapping references: 12 alpha reads map to both labels.
    (tmp_path/'references/panel.conf').write_text(''.join(f'DATABASE {name} {tmp_path/"references/alpha"}\n' for name in ('alpha','alpha_copy')))
    with TestClient(create_app(config)) as client:
        auth(client,config);run=submit(client,[FIXTURE.resolve()/'reads.fastq.gz'])
        assert run['state']=='completed',run['error']
        summary=run['qc']['results'][0]['screen']
        assert summary['no_genome_percent']=='40.00'
        assert all(row[4]=='0' and row[8]=='12' and row[9]=='60.00' for row in summary['rows'])


@pytest.mark.parametrize('content',[b'',b'not gzip',gzip.compress(b'@wrapped\nAC\nGT\n+\nIIII\n')])
def test_actual_invalid_or_wrapped_input_is_not_screened(config,tmp_path,content):
    source=tmp_path/'bad.fastq.gz';source.write_bytes(content)
    with TestClient(create_app(config)) as client:
        auth(client,config);run=submit(client,[source])
        assert run['state']=='failed' and not any(e['tool']=='fastq_screen' for e in run['executions'])


def test_panel_restrictions_and_partial_results(config,tmp_path):
    with TestClient(create_app(config)) as client:
        auth(client,config)
        for opts in [{'panel':'/etc/passwd'}, {'panel':'test-panel','subset':0}, {'panel':'test-panel','paired':True}, {'panel':'test-panel','subset':True}]:
            assert client.post('/api/runs',json={'mode':'fastq-screen','paths':[str(FIXTURE.resolve()/'reads.fastq.gz')], 'qc_options':opts}).status_code==400
        assert client.post('/api/runs',json={'mode':'fastq-screen','paths':['/etc/passwd'],'qc_options':{'panel':'test-panel'}}).status_code==403
        bad=tmp_path/'broken.fastq';bad.write_bytes(b'broken')
        run=submit(client,[FIXTURE.resolve()/'reads.fastq.gz',bad])
        assert run['state']=='partial' and run['sample_count']==1
        (tmp_path/'references/beta.rev.2.bt2').unlink()
        assert not client.get('/api/config').json()['screen_panels'][0]['available']
        assert client.post('/api/runs',json={'mode':'fastq-screen','paths':[str(FIXTURE.resolve()/'reads.fastq.gz')],'qc_options':{'panel':'test-panel'}}).status_code==400


@pytest.mark.parametrize('interrupt',[False,True])
def test_actual_screen_process_cancellation_and_interruption(config,tmp_path,interrupt):
    source=tmp_path/'cancellable.fastq.gz'
    chunk=gzip.decompress((FIXTURE/'reads.fastq.gz').read_bytes())
    with gzip.open(source,'wb') as output:
        for _ in range(2000):output.write(chunk)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'fastq-screen','paths':[str(source)],'qc_options':{'panel':'test-panel','subset':1000000}})
        assert response.status_code==201,response.text
        identifier=response.json()['id'];deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            run=client.get(f'/api/runs/{identifier}').json()
            if run['executions'] and run['executions'][-1]['tool']=='fastq_screen' and identifier in client.app.state.manager.executor.processes:
                break
            assert run['state'] in {'queued','running'},run
            time.sleep(.005)
        assert run['executions'][-1]['tool']=='fastq_screen' and run['state']=='running'
        if not interrupt:
            assert client.post(f'/api/runs/{identifier}/cancel').status_code==200
    with TestClient(create_app(config)) as client:
        auth(client,config);run=client.get(f'/api/runs/{identifier}').json()
        assert run['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(row['state']=='completed' for row in run['qc']['results'])
        assert not any(r['path'].startswith('qc/') for r in run['reports'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.skipif(not shutil.which('fastp'),reason='Actual fastp required for derived screening')
def test_screen_registered_derived_authority(config,tmp_path):
    fixture=(FIXTURE.parent/'fastqc-0.13.0').resolve()
    config=replace(config,roots=[fixture])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'fastp','paths':[str(fixture/'coverage_R1.fastq.gz')],'processing_options':{'compare_qc':False}})
        assert response.status_code==201,response.text
        parent=wait(client,response.json()['id']);assert parent['state']=='completed',parent['error']
        dataset=parent['derived_datasets'][0];path=str(config.output/parent['id']/dataset['path'])
        payload={'mode':'fastq-screen','paths':[path],'qc_options':{'panel':'test-panel'}}
        assert client.post('/api/runs',json=payload).status_code==403
        payload['input_datasets']=[{'run_id':parent['id'],'dataset_id':dataset['id']}]
        response=client.post('/api/runs',json=payload);assert response.status_code==201,response.text
        child=wait(client,response.json()['id']);assert child['state']=='completed',child['error']
        assert child['qc']['results'][0]['screen']['processed_reads']==dataset['records']
        assert child['input_provenance'][0]['run_id']==parent['id']
