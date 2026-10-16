"""Actual fastp/SeqKit integration; no manufactured scientific tool outputs."""
from dataclasses import replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

FIXTURE = Path(__file__).parent/'fixtures/fastqc-0.13.0'
FASTP = shutil.which(os.environ.get('QUALIDOCK_FASTP','fastp'))
SEQKIT = shutil.which(os.environ.get('QUALIDOCK_SEQKIT','seqkit'))
FASTQC = shutil.which(os.environ.get('QUALIDOCK_FASTQC','fastqc'))
MULTIQC = shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
if os.environ.get('QUALIDOCK_REQUIRE_PROCESSING_TESTS')=='1' and not all((FASTP,SEQKIT,FASTQC,MULTIQC)):
    raise RuntimeError('Processing acceptance requires actual fastp, SeqKit, FastQC and MultiQC')


def settings(tmp_path):
    return Settings(roots=[FIXTURE.resolve(),tmp_path.resolve()],output=tmp_path/'results',frontend=tmp_path/'frontend',token='processing-test',cpus=1,memory_mb=2048,fastp=FASTP or 'missing-fastp',seqkit=SEQKIT or 'missing-seqkit',fastqc=FASTQC or 'missing-fastqc',multiqc=MULTIQC or 'missing-multiqc',allow_root=True)


def auth(client,config):
    client.headers.update({'Authorization':f'Bearer {config.token}','X-QualiDock-Request':'1'})


def submit(client,mode,paths,options=None):
    response=client.post('/api/runs',json={'mode':mode,'paths':[str(p.resolve()) for p in paths],'processing_options':options or {}})
    assert response.status_code==201,response.text
    return wait(client,response.json()['id'],timeout=180)


@pytest.mark.skipif(not FASTP,reason='Actual fastp unavailable')
@pytest.mark.parametrize('paired',[False,True])
def test_actual_fastp_sources_provenance_and_restart(tmp_path,paired):
    config=settings(tmp_path)
    paths=sorted(FIXTURE.glob('*.fastq.gz'))[:2 if paired else 1]
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',paths,{'compare_qc':False,'gzip':paired})
        assert run['state']=='completed',client.get(f"/api/runs/{run['id']}/logs").json()
        assert len(run['processing']['units'])==1
        unit=run['processing']['units'][0]
        official=json.loads((config.output/run['id']/f"processing/{unit['id']}/fastp.json").read_text())
        assert unit['fastp']['summary']==official['summary']
        assert len(run['derived_datasets'])==len(paths)
        assert sum(d['records'] for d in run['derived_datasets'])==official['summary']['after_filtering']['total_reads']
        for entry in run['derived_datasets']:
            response=client.get(f"/api/runs/{run['id']}/download",params={'path':entry['path']})
            assert response.status_code==200 and 'attachment' in response.headers['content-disposition']
            assert hashlib.sha256(response.content).hexdigest()==entry['sha256']
        assert all(not report['path'].startswith('processing/private/') for report in run['reports'])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        restored=client.get(f"/api/runs/{run['id']}").json()
        assert restored['derived_datasets']==run['derived_datasets']
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':run['derived_datasets'][0]['path']}).status_code==200
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.skipif(not (FASTP and FASTQC and MULTIQC),reason='Actual fastp/FastQC/MultiQC required')
def test_actual_before_after_and_multiqc(tmp_path):
    config=settings(tmp_path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',sorted(FIXTURE.glob('*.fastq.gz')),{'multiqc':True})
        assert run['state']=='completed',client.get(f"/api/runs/{run['id']}/logs").json()
        data=client.get(f"/api/runs/{run['id']}/metrics").json()
        assert len(data['samples'])==4
        assert {row['processing_stage'] for row in run['report_input_map'].values() if row.get('processing_stage')}=={'raw','processed'}
        assert data['multiqc']['status']=='available'
        native_sources=[row for row in run['report_input_map'].values() if row.get('processing_stage')]
        assert len(native_sources)==4 and all(row.get('multiqc_name') for row in native_sources), run['warnings']
        assert len({row['multiqc_name'] for row in native_sources})==4
        assert any(row['path']=='multiqc/multiqc_report.html' for row in run['reports'])
        from qualidock.metrics import parse_report
        for sample in data['samples']:
            assert sample==parse_report(config.output/run['id']/sample['id'],sample['id'])


@pytest.mark.skipif(not SEQKIT,reason='Actual SeqKit unavailable')
@pytest.mark.parametrize('mode,options',[('seqkit-stats',{}),('seqkit-sample',{'fraction':0.3,'seed':17}),('seqkit-filter',{'min_length':151}),('seqkit-extract',{'identifiers':['not-present']})])
def test_actual_seqkit(tmp_path,mode,options):
    config=settings(tmp_path)
    paths=sorted(FIXTURE.glob('*.fastq.gz'))
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,mode,paths,options)
        assert run['state']=='completed',client.get(f"/api/runs/{run['id']}/logs").json()
        assert len(run['processing']['units'])==2
        if mode=='seqkit-stats':
            assert all(unit['statistics'][0]['num_seqs']=='400' for unit in run['processing']['units'])
            assert run['derived_datasets']==[]
        else:
            assert len(run['derived_datasets'])==2
            assert all(not row['paired'] for row in run['derived_datasets'])
            if mode=='seqkit-extract': assert all(row['records']==0 for row in run['derived_datasets'])
            if mode=='seqkit-sample':
                again=submit(client,mode,paths,options)
                def content(record):
                    p=config.output/record['id']/record['derived_datasets'][0]['path']
                    return gzip.open(p,'rb').read()
                assert content(run)==content(again)


@pytest.mark.skipif(not FASTP,reason='Actual fastp unavailable')
def test_partial_inputs_and_unauthorized_derived_download(tmp_path):
    config=settings(tmp_path)
    bad=tmp_path/'bad ; $(touch NEVER).fastq';bad.write_text('@broken\nACGT\n+\nI\n')
    good=sorted(FIXTURE.glob('*.fastq.gz'))[0]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',[good,bad],{'compare_qc':False})
        assert run['state']=='partial' and len(run['derived_datasets'])==1
        assert [unit['state'] for unit in run['processing']['units']]==['completed','failed']
        path=run['derived_datasets'][0]['path']
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':'processing/u0002/fastp.json'}).status_code==403
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':'../manifest.json'}).status_code==403
        local=config.output/run['id']/path
        stored=local.read_bytes();local.unlink();local.symlink_to(good)
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':path}).status_code==403
        local.unlink();local.write_bytes(stored+b'changed')
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':path}).status_code==403
        client.headers.pop('Authorization')
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':path}).status_code==401
        assert not (config.output/run['id']/'NEVER').exists()


@pytest.mark.skipif(not FASTP,reason='Actual fastp unavailable')
def test_fastp_mismatched_mate_ids_never_publish(tmp_path):
    config=settings(tmp_path)
    paths=[]
    for i in (1,2):
        path=tmp_path/f'wrong_R{i}_001.fastq'
        path.write_text(f'@different{i}\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n');paths.append(path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',paths,{'compare_qc':False})
        assert run['state']=='failed' and run['derived_datasets']==[]
        assert 'identifiers' in run['error']
        assert all(execution['tool']!='fastp' for execution in run['executions'])


@pytest.mark.skipif(not SEQKIT,reason='Actual SeqKit unavailable')
def test_seqkit_exact_extraction_and_length_boundaries(tmp_path):
    config=settings(tmp_path)
    source=sorted(FIXTURE.glob('*.fastq.gz'))[0]
    with gzip.open(source,'rt') as stream: identifier=stream.readline().split()[0][1:]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'seqkit-extract',[source],{'identifiers':[identifier]})
        assert run['state']=='completed' and run['derived_datasets'][0]['records']==1
        entry=run['derived_datasets'][0]
        with gzip.open(config.output/run['id']/entry['path'],'rt') as stream:
            assert stream.readline().split()[0][1:]==identifier
        filtered=submit(client,'seqkit-filter',[source],{'min_length':151,'max_length':151})
        assert filtered['state']=='completed'
        with gzip.open(source,'rt') as stream: expected=sum(len(line.strip())==151 for index,line in enumerate(stream) if index%4==1)
        assert filtered['derived_datasets'][0]['records']==expected
