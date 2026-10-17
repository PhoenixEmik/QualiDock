"""Genuine NanoPlot 1.48.0; no mocked successful scientific outputs."""
from dataclasses import replace
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import sys

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

TOOL=shutil.which(os.environ.get('QUALIDOCK_NANOPLOT','NanoPlot'))
if os.environ.get('QUALIDOCK_REQUIRE_NANOPLOT_TESTS')=='1' and not TOOL:
    raise RuntimeError('Actual NanoPlot required')
pytestmark=pytest.mark.skipif(not TOOL,reason='Actual NanoPlot unavailable')
FIXTURE=Path(__file__).parent/'fixtures/nanoq-0.10.0/ont.fastq.gz'
STATS=Path(__file__).parent/'fixtures/nanoplot-1.48.0/NanoStats.txt'


def settings(tmp_path):
    return Settings(roots=[FIXTURE.parent.resolve(),tmp_path.resolve()],output=tmp_path/'results',
                    frontend=tmp_path/'frontend',token='nanoplot-test',nanoplot=TOOL,cpus=1,memory_mb=2048,allow_root=True)


def auth(client,config):
    client.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})


@pytest.mark.parametrize('compressed',[True,False])
def test_genuine_stats_report_immutable_sources_and_restart(tmp_path,compressed):
    config=settings(tmp_path)
    source=FIXTURE.resolve()
    if not compressed:
        source=tmp_path/'reads $(touch INJECTED) & <sample>.fastq'
        source.write_bytes(gzip.decompress(FIXTURE.read_bytes()))
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    with TestClient(create_app(config)) as client:
        auth(client,config)
        created=client.post('/api/runs',json={'mode':'nanoplot','paths':[str(source)]})
        assert created.status_code==201,created.text
        run=wait(client,created.json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        row=run['qc']['results'][0];assert row['source_sha256']==digest
        assert row['summary'] is None and not run.get('derived_datasets')
        assert row['nanoplot']['rows']==[line.split('\t') for line in STATS.read_text().splitlines()[1:]]
        assert run['tools']['nanoplot']['version']=='1.48.0'
        execution=next(e for e in run['executions'] if e['tool']=='nanoplot')
        assert '--fastq' in execution['argv'] and '--no_static' in execution['argv']
        assert '--include-js' in execution['argv'] and 'embedded' in execution['argv']
        assert not {'--downsample','--fastq_rich','--raw','--store'} & set(execution['argv'])
        assert execution['exit_code']==0 and execution['finished_at']
        for path in [row['report'],row['nanoplot']['html']]:
            response=client.get(f'/api/runs/{run["id"]}/download',params={'path':path})
            assert response.status_code==200 and response.content==(config.output/run['id']/path).read_bytes()
            assert 'attachment' in response.headers['content-disposition']
        html=client.get('/api/report-preview',params={'run_id':run['id'],'path':row['nanoplot']['html']})
        assert html.status_code==200 and 'text/html' in html.headers['content-type']
        assert 'sandbox allow-scripts' in html.headers['content-security-policy']
        assert 'allow-same-origin' not in html.headers['content-security-policy']
        assert b'Plotly.newPlot' in html.content and b'src="https://cdn.plot.ly' not in html.content
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':'../outside.html'}).status_code==403
        assert not any(r['path'].startswith('qc/private/') for r in run['reports'])
        assert client.get('/api/history?mode=nanoplot').json()['total']==1
        assert client.get(f'/api/runs/{run["id"]}/configuration').json()['qc_options']=={'loglength':False,'individual_plots':False}
        # Retain real report/observations for CI review; no source copies.
        retained=Path('validation/nanoplot')/('gzip' if compressed else 'plain')
        shutil.copytree(config.output/run['id'],retained,dirs_exist_ok=True)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        restored=client.get(f'/api/runs/{run["id"]}').json()
        assert restored['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/metrics').json()['qc']==run['qc']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    assert not list(tmp_path.rglob('INJECTED'))


@pytest.mark.parametrize('content',[b'',b'not gzip',gzip.compress(b'@x\nACGT\n+\nI\n')])
def test_genuine_malformed_inputs_never_invoke_nanoplot(tmp_path,content):
    config=settings(tmp_path);source=tmp_path/'broken.fastq.gz';source.write_bytes(content)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=client.post('/api/runs',json={'mode':'nanoplot','paths':[str(source)]})
        assert run.status_code==201,run.text
        run=wait(client,run.json()['id'],timeout=30)
        assert run['state']=='failed' and not run['sample_count']
        assert not any(e['tool']=='nanoplot' for e in run['executions'])
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


def test_genuine_invocation_failure_retains_no_scientific_artifacts(tmp_path):
    config=settings(tmp_path)
    # Intentionally ask the real executable to reject an invalid upstream flag.
    wrapper=tmp_path/'invalid-NanoPlot'
    header=Path(TOOL).read_text().splitlines()[0]
    wrapper.write_text(header+'\nimport sys\nfrom nanoplot.NanoPlot import main\nsys.argv.insert(1,"--invalid-qualidock-test-flag")\nmain()\n')
    wrapper.chmod(0o700);config=replace(config,nanoplot=str(wrapper))
    with TestClient(create_app(config)) as client:
        auth(client,config)
        created=client.post('/api/runs',json={'mode':'nanoplot','paths':[str(FIXTURE.resolve())]})
        assert created.status_code==201,created.text
        run=wait(client,created.json()['id'],timeout=60)
        assert run['state']=='failed' and run['qc']['results'][0]['exit_code']==2
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


def test_actual_successful_tool_with_truncated_html_is_not_published(tmp_path,monkeypatch):
    from qualidock import nanoplot
    original=nanoplot.stats
    def damage_report(path,source):
        result=original(path,source)
        html=path.with_name('NanoPlot-report.html')
        assert html.stat().st_size>1000  # A genuine completed tool report exists.
        html.write_bytes(b'<html><head></head><body>')
        return result
    monkeypatch.setattr(nanoplot,'stats',damage_report)
    config=settings(tmp_path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        created=client.post('/api/runs',json={'mode':'nanoplot','paths':[str(FIXTURE.resolve())]})
        assert created.status_code==201,created.text
        run=wait(client,created.json()['id'],timeout=60)
        assert run['state']=='failed' and run['qc']['results'][0]['exit_code']==0
        assert 'HTML document' in run['error']
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


@pytest.mark.parametrize('interrupt',[False,True])
def test_actual_nanoplot_cancellation_and_interrupted_restart(tmp_path,interrupt):
    config=settings(tmp_path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        created=client.post('/api/runs',json={'mode':'nanoplot','paths':[str(FIXTURE.resolve())]})
        assert created.status_code==201,created.text
        identifier=created.json()['id'];deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            run=client.get(f'/api/runs/{identifier}').json()
            if any(e['tool']=='nanoplot' and e['finished_at'] is None for e in run['executions']):break
            time.sleep(.01)
        assert run['state']=='running' and run['executions'][-1]['tool']=='nanoplot'
        if not interrupt:
            assert client.post(f'/api/runs/{identifier}/cancel').status_code==200
            assert wait(client,identifier)['state']=='cancelled'
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=client.get(f'/api/runs/{identifier}').json()
        assert run['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(row['state']=='completed' for row in run['qc']['results'])
        assert not any(r['path'].startswith('qc/') for r in run['reports'])


@pytest.mark.skipif(not shutil.which('fastp'),reason='Actual fastp required for derived reuse')
def test_actual_derived_authority(tmp_path):
    fixture=(FIXTURE.parent.parent/'fastqc-0.13.0').resolve()
    config=replace(settings(tmp_path),roots=[fixture])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        parent=client.post('/api/runs',json={'mode':'fastp','paths':[str(fixture/'coverage_R1.fastq.gz')],
                                           'processing_options':{'compare_qc':False}})
        assert parent.status_code==201,parent.text
        parent=wait(client,parent.json()['id'],timeout=60);assert parent['state']=='completed',parent['error']
        dataset=parent['derived_datasets'][0];path=str(config.output/parent['id']/dataset['path'])
        payload={'mode':'nanoplot','paths':[path]}
        assert client.post('/api/runs',json=payload).status_code==403
        payload['input_datasets']=[{'run_id':parent['id'],'dataset_id':dataset['id']}]
        created=client.post('/api/runs',json=payload);assert created.status_code==201,created.text
        child=wait(client,created.json()['id'],timeout=60);assert child['state']=='completed',child['error']
        assert dict(child['qc']['results'][0]['nanoplot']['rows'])['number_of_reads']==str(dataset['records'])
        assert child['input_provenance'][0]['run_id']==parent['id']


def test_actual_partial_collision_and_missing_artifact(tmp_path):
    config=settings(tmp_path);paths=[]
    for folder in ['a','b']:
        root=tmp_path/folder;root.mkdir();source=root/'same.fastq.gz'
        shutil.copyfile(FIXTURE,source);paths.append(str(source))
    bad=tmp_path/'bad.fastq';bad.write_text('broken');paths.append(str(bad))
    with TestClient(create_app(config)) as client:
        assert client.post('/api/runs',headers={'X-QualiDock-Request':'1'},json={'mode':'nanoplot','paths':paths}).status_code==401
        auth(client,config)
        created=client.post('/api/runs',json={'mode':'nanoplot','paths':paths})
        assert created.status_code==201,created.text
        run=wait(client,created.json()['id'],timeout=60)
        assert run['state']=='partial' and run['sample_count']==2
        rows=[r for r in run['qc']['results'] if r['state']=='completed']
        assert len({r['report'] for r in rows})==2
        assert {r['report'] for r in rows}==set(run['report_input_map'])
        path=rows[0]['nanoplot']['html'];(config.output/run['id']/path).unlink()
        assert client.get('/api/report-preview',params={'run_id':run['id'],'path':path}).status_code==404
        arbitrary=config.output/run['id']/'qc/unregistered.html';arbitrary.write_text('<html>not registered</html>')
        assert client.get('/api/report-preview',params={'run_id':run['id'],'path':'qc/unregistered.html'}).status_code==403


@pytest.mark.parametrize('advanced',[False,True])
def test_actual_plotting_overhead_benchmark(tmp_path,monkeypatch,advanced):
    script=Path(__file__).resolve().parents[2]/'scripts/benchmark-analysis.py'
    spec=importlib.util.spec_from_file_location('nanoplot_benchmark',script)
    benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)
    monkeypatch.setenv('QUALIDOCK_NANOPLOT',TOOL)
    if sys.platform!='linux':monkeypatch.setattr(benchmark,'usage',lambda group:{})
    output=tmp_path/'benchmark'
    argv=['--input',str(FIXTURE.resolve()),'--output',str(output),'--mode','nanoplot','--threads','1','--hash-inputs']
    if advanced:argv+=['--nanoplot-loglength','--nanoplot-individual-plots']
    benchmark.main(benchmark.parser().parse_args(argv))
    evidence=json.loads((output/'benchmark.json').read_text())
    assert evidence['status']=='measured' and evidence['terminal_state']=='completed'
    assert evidence['input_integrity_unchanged'] and evidence['derived_bytes']==0
    assert not evidence['unpublished_fastqs'] and evidence['registered_report_bytes']>0
    assert evidence['waited_child_cpu_seconds']>0
    assert evidence['validation_scans'][0]['bytes_read']==FIXTURE.stat().st_size
    assert evidence['validation_scans'][0]['coverage']=='full'
    row=evidence['run']['qc']['results'][0]
    assert bool(row['nanoplot']['plots'])==advanced
    assert all(p.endswith('.html') for p in row['nanoplot']['plots'])
    assert not list(output.rglob('*.png'))
    retained=Path('validation/nanoplot')/('advanced' if advanced else 'baseline')
    shutil.copytree(output,retained,dirs_exist_ok=True)
