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
    if not paired:
        # Genuine fixture bytes, adversarial filename; never a fabricated tool result.
        odd=tmp_path/'sample $(touch INJECTED) ;.fastq.gz'
        shutil.copyfile(paths[0],odd);paths=[odd]
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',paths,{'compare_qc':False,'gzip':paired})
        assert run['state']=='completed',client.get(f"/api/runs/{run['id']}/logs").json()
        assert len(run['processing']['units'])==1
        assert not (config.output/run['id']/'INJECTED').exists()
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
        assert len(run['processing']['units'])==(1 if mode=='seqkit-sample' else 2)
        if mode=='seqkit-stats':
            assert all(unit['statistics'][0]['num_seqs']=='400' for unit in run['processing']['units'])
            assert run['derived_datasets']==[]
        else:
            assert len(run['derived_datasets'])==2
            assert all(row['paired']==(mode=='seqkit-sample') for row in run['derived_datasets'])
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


@pytest.mark.parametrize('mode',['fastp','seqkit-sample'])
def test_mismatched_mate_ids_never_publish(tmp_path,mode):
    if not (FASTP if mode=='fastp' else SEQKIT): pytest.skip('Actual tool unavailable')
    config=settings(tmp_path)
    paths=[]
    for i in (1,2):
        path=tmp_path/f'wrong_R{i}_001.fastq'
        path.write_text(f'@different{i}\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n');paths.append(path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,mode,paths,{'compare_qc':False} if mode=='fastp' else {})
        assert run['state']=='failed' and run['derived_datasets']==[]
        assert 'identifiers' in run['error']
        assert all(execution['tool'] not in {'fastp','seqkit'} for execution in run['executions'])


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


@pytest.mark.skipif(not FASTP,reason='Actual fastp unavailable')
def test_fastp_quality_toggle_controls_n_filter(tmp_path):
    # Explicit synthetic edge case, actual fastp reports and FASTQ outputs.
    source=tmp_path/'n_filter.fastq';source.write_text('@n_filter\n'+'N'*20+'\n+\n'+'I'*20+'\n')
    config=settings(tmp_path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        filtered=submit(client,'fastp',[source],{'compare_qc':False,'adapter_trimming':False})
        retained=submit(client,'fastp',[source],{'compare_qc':False,'adapter_trimming':False,'quality_filtering':False})
        assert filtered['state']==retained['state']=='completed'
        assert filtered['derived_datasets'][0]['records']==0
        assert retained['derived_datasets'][0]['records']==1
        assert source.read_text()=='@n_filter\n'+'N'*20+'\n+\n'+'I'*20+'\n'


@pytest.mark.skipif(not (FASTP and FASTQC and MULTIQC),reason='Actual fastp, FastQC and MultiQC required')
def test_manual_pair_identical_basenames_retains_independent_fastqc_results(tmp_path):
    config=settings(tmp_path);paths=[]
    for source,name in zip(sorted(FIXTURE.glob('*.fastq.gz')),('left','right')):
        folder=tmp_path/name;folder.mkdir();path=folder/'reads.fastq.gz';shutil.copyfile(source,path);paths.append(str(path))
    pairing=[{'path':path,'read':f'R{i+1}','pair_key':'manual:reads','paired':True,'mate':paths[1-i],'source':'manual','assignment':'paired'} for i,path in enumerate(paths)]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'fastp','paths':paths,'input_pairing':pairing,'sample_groups':[{'id':'manual:sample','display_name':'Reviewed pair','files':paths,'source':'manual'}], 'processing_options':{'multiqc':True}})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'],timeout=180)
        assert run['state']=='completed',client.get(f"/api/runs/{run['id']}/logs").json()
        raw=run['processing']['units'][0]['raw_qc']
        assert len({row['report'] for row in raw})==2
        samples=client.get(f"/api/runs/{run['id']}/metrics").json()['samples']
        assert len(samples)==len({sample['id'] for sample in samples})==4
        assert {run['report_input_map'][sample['id']]['path'] for sample in samples if run['report_input_map'][sample['id']]['processing_stage']=='raw'}==set(paths)
        assert all(sample['name']=='reads.fastq.gz' for sample in samples if sample['id'] in {record['report'] for record in raw})
        names=[row['multiqc_name'] for row in run['report_input_map'].values() if row.get('processing_stage')]
        assert len(names)==len(set(names))==4


@pytest.mark.skipif(not all((FASTP, FASTQC)), reason='Actual fastp and FastQC required')
def test_actual_derived_reuse_outside_roots_restart_and_tampering(tmp_path):
    config=replace(settings(tmp_path),roots=[FIXTURE.resolve()])
    paths=sorted(FIXTURE.glob('*.fastq.gz'))
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with TestClient(create_app(config)) as client:
        auth(client,config)
        parent=submit(client,'fastp',paths,{'compare_qc':False})
        assert parent['state']=='completed'
        base=f"/api/runs/{parent['id']}"
        draft=client.get(base+'/datasets').json()
        assert len(draft['entries'])==2 and len(draft['input_datasets'])==2
        assert all(r['paired'] for r in draft['input_pairing'])
        assert all(r['source']=='confirmed' for r in draft['input_pairing'])
        assert all(client.get('/api/files',params={'path':str(Path(p).parent)}).status_code==403 for p in draft['paths'])
        no_auth=TestClient(create_app(config))
        assert no_auth.get(base+'/datasets').status_code==401
        # An unregistered output path is never authorized by knowing its location.
        forged={**draft,'mode':'fastqc','input_datasets':[]}
        assert client.post('/api/runs',json=forged).status_code==403
        for ids,status in [(['unknown'],403),([parent['derived_datasets'][0]['id']]*2,400)]:
            assert client.post(base+'/reuse',json={'dataset_ids':ids}).status_code==status
        one=client.post(base+'/reuse',json={'dataset_ids':[parent['derived_datasets'][0]['id']]}).json()
        assert not one['input_pairing'][0]['paired'] and one['input_pairing'][0]['mate'] is None
        created=client.post('/api/runs',json={**draft,'mode':'fastqc'})
        assert created.status_code==201,created.text
        child=wait(client,created.json()['id'],timeout=120)
        assert child['state']=='completed',child.get('error')
        assert child['inputs']==draft['paths']
        assert child['input_datasets']==[{k:r[k] for k in ('run_id','dataset_id')} for r in draft['input_datasets']]
        assert {r['sha256'] for r in child['input_provenance']}=={d['sha256'] for d in parent['derived_datasets']}
        assert len(client.get(f"/api/runs/{child['id']}/metrics").json()['samples'])==2
        assert not any(p.suffix in {'.fq','.gz'} for p in (config.output/child['id']/'inputs').rglob('*'))
        saved=client.get(f"/api/runs/{child['id']}/configuration").json()
        assert saved['paths']==draft['paths'] and saved['input_datasets']==draft['input_datasets']
    with TestClient(create_app(config)) as client:
        auth(client,config)
        restored=client.get(f"/api/runs/{child['id']}/configuration")
        assert restored.status_code==200
        rerun=client.post('/api/runs',json={**restored.json(),'mode':'fastqc'})
        assert rerun.status_code==201,rerun.text
        assert wait(client,rerun.json()['id'],timeout=120)['state']=='completed'
        derived=Path(draft['paths'][0]);before=derived.read_bytes()
        derived.write_bytes(before+b'changed')
        assert client.get(base+'/datasets').status_code==403
        assert client.post('/api/runs',json={**draft,'mode':'fastqc'}).status_code==403
        derived.unlink()
        assert client.get(base+'/datasets').status_code==403
        assert client.post('/api/runs',json={**draft,'mode':'fastqc'}).status_code==403
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.skipif(not all((FASTP,SEQKIT)),reason='Actual fastp and SeqKit required')
def test_actual_fastp_to_seqkit_derived_chain(tmp_path):
    config=replace(settings(tmp_path),roots=[FIXTURE.resolve()])
    with TestClient(create_app(config)) as client:
        auth(client,config)
        parent=submit(client,'fastp',sorted(FIXTURE.glob('*.fastq.gz')),{'compare_qc':False})
        draft=client.get(f"/api/runs/{parent['id']}/datasets").json()
        response=client.post('/api/runs',json={**draft,'mode':'seqkit-sample','processing_options':{'fraction':0.5,'seed':19}})
        assert response.status_code==201,response.text
        result=wait(client,response.json()['id'],timeout=120)
        assert result['state']=='completed',result.get('error')
        assert result['inputs']==draft['paths'] and len(result['derived_datasets'])==2
        assert all(d['paired'] for d in result['derived_datasets'])
        assert result['processing']['units'][0]['output_validation']['pairs'][0]['state']=='passed'
        for d in result['derived_datasets']:
            assert d['source'] in draft['paths']
            assert d['sha256']==hashlib.sha256((config.output/result['id']/d['path']).read_bytes()).hexdigest()


@pytest.mark.skipif(not SEQKIT,reason='Actual SeqKit required')
def test_seqkit_sampling_preserves_full_pair_ids_and_reproducibility(tmp_path):
    config=settings(tmp_path);paths=sorted(FIXTURE.glob('*.fastq.gz'))
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    def ids(run, index):
        with gzip.open(config.output/run['id']/run['derived_datasets'][index]['path'],'rt') as stream:
            return [line.split()[0].removesuffix('/1').removesuffix('/2') for n,line in enumerate(stream) if n%4==0]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        first=submit(client,'seqkit-sample',paths,{'fraction':0.35,'seed':73})
        repeat=submit(client,'seqkit-sample',paths,{'fraction':0.35,'seed':73})
        changed=submit(client,'seqkit-sample',paths,{'fraction':0.35,'seed':74})
        assert all(r['state']=='completed' for r in (first,repeat,changed))
        assert ids(first,0)==ids(first,1)==ids(repeat,0)==ids(repeat,1)
        assert ids(first,0)!=ids(changed,0)
        assert 0<len(ids(first,0))<400
        assert all(d['paired'] for d in first['derived_datasets'])
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.skipif(not FASTP,reason='Actual fastp required')
def test_measured_streaming_validation_io(tmp_path):
    import resource,time
    config=replace(settings(tmp_path),roots=[FIXTURE.resolve()])
    paths=sorted(FIXTURE.glob('*.fastq.gz'))
    cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    started=time.perf_counter()
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',paths,{'compare_qc':False})
        assert run['state']=='completed',run.get('error')
    elapsed=time.perf_counter()-started
    cpu_after=resource.getrusage(resource.RUSAGE_CHILDREN)
    scans=[run['processing']['input_validation'],*[u['output_validation'] for u in run['processing']['units']]]
    source_bytes=sum(row['compressed_bytes_read'] for row in scans[0]['files'])
    output_bytes=sum(row['compressed_bytes_read'] for scan in scans[1:] for row in scan['files'])
    assert source_bytes==sum(p.stat().st_size for p in paths)
    assert output_bytes==sum((config.output/run['id']/d['path']).stat().st_size for d in run['derived_datasets'])
    assert all(row['coverage']=='full' and row['checksum_status']=='computed_source_not_transfer_verified' for scan in scans for row in scan['files'])
    evidence={'fixture':'genuine FastQC 0.13.0 paired inputs; 400 reads/file',
        'source_validation_bytes_read':source_bytes,'output_validation_bytes_read':output_bytes,
        'full_validation_file_scans':sum(len(scan['files']) for scan in scans),'wall_seconds':elapsed,
        'waited_children_cpu_seconds':(cpu_after.ru_utime+cpu_after.ru_stime)-(cpu_before.ru_utime+cpu_before.ru_stime),
        'external_tool_io_bytes':None,
        'children_maxrss_raw':cpu_after.ru_maxrss,
        'memory_scope':'OS RUSAGE_CHILDREN maximum single waited child in this test process; not aggregate process-group peak; bytes on macOS, KiB on Linux',
        'execution_observations':[e.get('resources') for e in run['executions']] if os.sys.platform=='linux' else None,
        'observer_note':'Linux uses the actual process-group RSS sampler; managed macOS harness substitutes the denied ps sampler, so its readings are omitted'}
    destination=Path('validation');destination.mkdir(exist_ok=True)
    (destination/'core-processing-io.json').write_text(json.dumps(evidence,indent=2))


@pytest.mark.skipif(not all((FASTP,FASTQC,MULTIQC)),reason='Actual fastp, FastQC and MultiQC required')
@pytest.mark.parametrize('mode',['both','fastp'])
def test_actual_multiqc_cli_failure_preserves_successful_results(tmp_path,mode):
    """Inject an invalid flag into the real CLI; never substitute scientific output."""
    config=settings(tmp_path);paths=sorted(FIXTURE.glob('*.fastq.gz'))
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with TestClient(create_app(config)) as client:
        auth(client,config)
        manager=client.app.state.manager;command=manager.command
        async def invalid_cli(run,tool,argv,directory):
            if tool=='multiqc':argv=[*argv,'--qualidock-test-invalid-option']
            return await command(run,tool,argv,directory)
        manager.command=invalid_cli
        result=submit(client,mode,paths,{'multiqc':True} if mode=='fastp' else {})
        assert result['state']=='partial' and 'MultiQC exited with code' in result['error']
        data=client.get(f"/api/runs/{result['id']}/metrics").json()
        assert len(data['samples'])==(4 if mode=='fastp' else 2)
        assert all(client.get(f"/api/runs/{result['id']}/download",params={'path':sample['id']}).status_code==200 for sample in data['samples'])
        if mode=='fastp':
            assert len(result['derived_datasets'])==2 and all(d['paired'] for d in result['derived_datasets'])
            assert result['processing']['units'][0]['output_validation']['pairs'][0]['state']=='passed'
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
