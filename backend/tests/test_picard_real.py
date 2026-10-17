"""Actual Picard JAR, Java, SAMtools; numeric rows compared with independent CLI."""
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
from qualidock import picard
from qualidock.tools import locate_tool
from test_workspace import wait

SAMTOOLS=shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
JAVA=shutil.which(os.environ.get('QUALIDOCK_JAVA','java'))
JAR=locate_tool('picard',os.environ.get('QUALIDOCK_PICARD','picard.jar'))
if os.environ.get('QUALIDOCK_REQUIRE_PICARD_TESTS')=='1' and (not all([SAMTOOLS,JAVA,JAR]) or not shutil.which('Rscript')):
    raise RuntimeError('Actual Picard, Java17, SAMtools and PDF Rscript required')
pytestmark=pytest.mark.skipif(not all([SAMTOOLS,JAVA,JAR]),reason='Actual Picard unavailable')
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('prepare_insert',ROOT/'scripts/prepare-insert-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def auth(client,config):client.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})
def hashes(directory):return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}


@pytest.fixture
def inputs(tmp_path):
    bam=fixture.prepare(tmp_path/'inputs',SAMTOOLS)
    config=Settings(roots=[bam.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',samtools=SAMTOOLS,java=JAVA,picard=JAR,cpus=1,memory_mb=1024,allow_root=True)
    return config,bam


def standalone(config,bam,options):
    output=config.output.parent/'standalone.metrics.txt';temporary=config.output.parent/'standalone-tmp';temporary.mkdir(exist_ok=True)
    argv=[JAVA,'-Xms64m','-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.io.tmpdir='+str(temporary),'-jar',JAR,'CollectInsertSizeMetrics',
          'INPUT='+str(bam),'OUTPUT='+str(output),'TMP_DIR='+str(temporary),'MINIMUM_PCT=0.05','DEVIATIONS=10',
          'INCLUDE_DUPLICATES='+str(options.get('include_duplicates',False)).lower(),'METRIC_ACCUMULATION_LEVEL=ALL_READS','ASSUME_SORTED=false','VALIDATION_STRINGENCY=STRICT','CREATE_INDEX=false','CREATE_MD5_FILE=false']
    if options.get('by_library'):argv+=['METRIC_ACCUMULATION_LEVEL=LIBRARY']
    env=os.environ.copy()
    for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'):env.pop(key,None)
    subprocess.run(argv,check=True,capture_output=True,env=env)
    return picard.parse(output)


@pytest.mark.parametrize('options',[{}, {'by_library':True}, {'include_duplicates':True}])
def test_actual_orientation_metrics_precision_histogram_and_restart(inputs,options):
    config,bam=inputs
    if options.get('by_library'):fixture.prepare(bam.parent,SAMTOOLS,libraries=True)
    before=hashes(bam.parent);expected=standalone(config,bam,options)
    with TestClient(create_app(config)) as client:
        assert client.get('/api/config').status_code==401
        auth(client,config)
        response=client.post('/api/runs',json={'mode':'picard','paths':[str(bam)],'qc_options':options})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'],timeout=60)
        assert run['state']=='completed',(run['error'],(config.output/run['id']/'analysis.log').read_text())
        result=run['qc']['results'][0]['picard']
        assert result['metrics']==expected['metrics'] and result['histogram']==expected['histogram']
        assert run['tools']['picard']['version']=='3.5.0' and run['tools']['picard']['version_probe_exit_code']==1
        assert run['tools']['java']['version'].startswith('17.')
        assert not run['input_pairing'] and not run.get('derived_datasets')
        assert result['heap_mb']==576
        command=next(e for e in run['executions'] if e['tool']=='picard')
        assert command['exit_code']==0 and '-Xmx576m' in command['argv'] and '-XX:ActiveProcessorCount=1' in command['argv']
        assert all(command['environment'][key]=='' for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'))
        metrics=result['reports']['metrics'];original=(config.output/run['id']/metrics).read_bytes()
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':metrics}).content==original
        assert client.get('/api/history?mode=picard').json()['total']==1
        draft=client.get('/api/runs/'+run['id']+'/configuration').json()
        assert draft['qc_options']==run['qc']['options']
        private=config.output/run['id']/f'qc/{run["qc"]["results"][0]["id"]}/private/secret.txt';private.write_text('not an artifact')
        unregistered=private.parent.parent/'unregistered.pdf';unregistered.write_bytes((ROOT/'backend/tests/fixtures/picard-3.5.0/paired.histogram.pdf').read_bytes())
        client.app.state.manager.refresh_reports(client.app.state.manager.runs[run['id']])
        for path in (private,unregistered):
            assert client.get(f'/api/runs/{run["id"]}/download',params={'path':str(path.relative_to(config.output/run['id']))}).status_code==403
        shutil.copytree(config.output/run['id'],Path('validation/picard')/('library' if options.get('by_library') else 'duplicates' if options else 'all-reads'),dirs_exist_ok=True)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        assert client.get('/api/runs/'+run['id']).json()['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':metrics}).content==original
    assert before==hashes(bam.parent)


def test_original_pdf_is_verified_downloadable_and_reports_r_version(inputs):
    if not shutil.which('Rscript'):pytest.skip('Rscript is optional locally; required in genuine CI')
    config,bam=inputs;before=hashes(bam.parent)
    with TestClient(create_app(config)) as c:
        auth(c,config);response=c.post('/api/runs',json={'mode':'picard','paths':[str(bam)],'qc_options':{'histogram_pdf':True}})
        assert response.status_code==201,response.text
        run=wait(c,response.json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard'];path=data['reports']['histogram_pdf']
        assert data['rscript_version']
        content=c.get(f'/api/runs/{run["id"]}/download',params={'path':path})
        assert content.status_code==200 and 'attachment' in content.headers['content-disposition']
        assert content.content.startswith(b'%PDF-') and b'%%EOF' in content.content[-1024:]
        saved=config.output/run['id']/path;saved.unlink();saved.symlink_to(bam)
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':path}).status_code==403
    assert before==hashes(bam.parent)


def test_single_end_is_explicitly_unavailable_without_invented_zero_metrics(inputs):
    config,bam=inputs;fixture.prepare(bam.parent,SAMTOOLS,single=True);before=hashes(bam.parent)
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'picard','paths':[str(bam)]}).json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard']
        assert data['status']=='unavailable' and data['mapped_pairs_reported']=='0.0'
        assert data['metrics']['rows']==data['histogram']['rows']==[] and 'metrics' not in data['reports']
    assert before==hashes(bam.parent)


def test_java_environment_cannot_override_owned_heap_and_temporary_paths(inputs,monkeypatch):
    config,bam=inputs
    for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'):monkeypatch.setenv(key,'-Xmx8g')
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'picard','paths':[str(bam)]}).json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        execution=next(e for e in run['executions'] if e['tool']=='picard')
        assert '-Xmx576m' in execution['argv'] and '-Xmx8g' not in execution['argv']
        assert all(execution['environment'][k]=='' for k in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'))
        assert Path(execution['environment']['TMPDIR']).is_relative_to(config.output/run['id'])


def test_original_tail_trimming_is_not_reinterpreted_as_the_full_population(inputs):
    config,bam=inputs;sam=bam.with_suffix('.sam')
    content=sam.read_text().replace('LN:10000','LN:30000')
    for flag,pos,mate,span in [(99,10000,19950,10000),(147,19950,10000,-10000)]:
        content+=f'outlier\t{flag}\tchrDNA\t{pos}\t60\t50M\t=\t{mate}\t{span}\t'+ 'A'*50+'\t'+'I'*50+'\tRG:Z:dna\n'
    # Test-only construction is sorted; application never sorts or rewrites BAM.
    lines=content.splitlines();header=[l for l in lines if l.startswith('@')]
    records=sorted((l for l in lines if not l.startswith('@')),key=lambda l:int(l.split('\t')[3]))
    sam.write_text('\n'.join(header+records)+'\n')
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(sam)],check=True,capture_output=True)
    before=hashes(bam.parent);expected=standalone(config,bam,{})
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'picard','paths':[str(bam)]}).json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard'];assert data['metrics']==expected['metrics'] and data['histogram']==expected['histogram']
        fr=next(r for r in data['metrics']['rows'] if r[8]=='FR')
        assert fr[7]=='4' and fr[4]=='10000' and fr[5]=='250'
        assert sum(int(r[1]) for r in data['histogram']['rows'])==3
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('fault',['cram','fastq','corrupt','missing','unsorted','missing-library'])
def test_invalid_or_unqualified_alignment_inputs_fail_truthfully(inputs,fault):
    config,bam=inputs;options={}
    if fault=='cram':bam=bam.with_suffix('.cram');bam.write_bytes(b'CRAMunqualified')
    if fault=='fastq':bam=bam.with_suffix('.fastq');bam.write_text('@read\nA\n+\nI\n')
    if fault=='corrupt':bam.write_bytes(b'not a BAM')
    if fault=='missing':bam.unlink()
    if fault in {'unsorted','missing-library'}:
        sam=bam.with_suffix('.sam');lines=sam.read_text().splitlines()
        if fault=='unsorted':lines=[*[l for l in lines if l.startswith('@')],*reversed([l for l in lines if not l.startswith('@')])]
        else:
            options={'by_library':True};lines=[l.replace('\tLB:library-A','') for l in lines]
        sam.write_text('\n'.join(lines)+'\n');subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(sam)],check=True,capture_output=True)
    with TestClient(create_app(config)) as c:
        auth(c,config);response=c.post('/api/runs',json={'mode':'picard','paths':[str(bam)],'qc_options':options})
        if response.status_code==201:
            run=wait(c,response.json()['id'],timeout=60)
            assert run['state']=='failed' and not any(e['tool']=='picard' for e in run['executions'])
        else:assert response.status_code in {400,403,422},response.text


def test_duplicate_basename_literal_paths_and_partial_success(inputs):
    config,bam=inputs;second=bam.parent/'other'/bam.name;second.parent.mkdir();shutil.copyfile(bam,second)
    special=bam.parent/'sample $(touch injected) <img>.bam';bam.rename(special)
    bad=bam.parent/'corrupt.bam';bad.write_bytes(second.read_bytes()[:-20]);before=hashes(bam.parent)
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'picard','paths':[str(special),str(second),str(bad)]}).json()['id'],timeout=60)
        assert run['state']=='partial' and run['sample_count']==2
        assert len({r['id'] for r in run['qc']['results']})==3
        assert not (config.output/run['id']/'injected').exists()
    assert before==hashes(bam.parent)


def test_zero_exit_without_metrics_or_a_real_zero_pair_diagnostic_is_failure(inputs):
    config,bam=inputs
    wrapper=config.output.parent/'incomplete-java'
    wrapper.write_text(f'#!{sys.executable}\nimport os,sys\nif "--version" in sys.argv:os.execv({JAVA!r},[{JAVA!r},*sys.argv[1:]])\nprint("incomplete report",file=sys.stderr)\n');wrapper.chmod(0o700)
    config=replace(config,java=str(wrapper))
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'picard','paths':[str(bam)]}).json()['id'],timeout=60)
        assert run['state']=='failed' and 'without metrics' in run['error']
        assert not any(p['path'].startswith('qc/') for p in run['reports'])


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancellation_and_restart_never_publish_unfinished_insert_outputs(inputs,interrupt):
    config,bam=inputs;before=hashes(bam.parent)
    wrapper=config.output.parent/'slow-java'
    wrapper.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "CollectInsertSizeMetrics" in sys.argv and "--version" not in sys.argv:time.sleep(30)\nos.execv({JAVA!r},[{JAVA!r},*sys.argv[1:]])\n');wrapper.chmod(0o700)
    config=replace(config,java=str(wrapper))
    with TestClient(create_app(config)) as c:
        auth(c,config);response=c.post('/api/runs',json={'mode':'picard','paths':[str(bam)]})
        assert response.status_code==201,response.text
        for _ in range(300):
            run=c.get('/api/runs/'+response.json()['id']).json()
            if any(e['tool']=='picard' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Genuine Java/Picard probe and SAM preflight did not reach insert execution')
        if not interrupt:assert c.post('/api/runs/'+run['id']+'/cancel').status_code==200
    with TestClient(create_app(config)) as c:
        auth(c,config);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']==restored['qc']['results'][0]['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(p['path'].startswith('qc/') for p in restored['reports'])
    assert before==hashes(bam.parent)
