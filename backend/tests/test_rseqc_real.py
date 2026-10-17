"""Actual upstream RSeQC, explicit RNA geometry, and unchanged source bytes."""
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

SAMTOOLS=shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
INFER=shutil.which(os.environ.get('QUALIDOCK_RSEQC_INFER','infer_experiment.py'))
DISTRIBUTION=shutil.which(os.environ.get('QUALIDOCK_RSEQC_DISTRIBUTION','read_distribution.py'))
if os.environ.get('QUALIDOCK_REQUIRE_RNA_TESTS')=='1' and not all([SAMTOOLS,INFER,DISTRIBUTION]):
    raise RuntimeError('Actual SAMtools and both RSeQC executables required')
pytestmark=pytest.mark.skipif(not all([SAMTOOLS,INFER,DISTRIBUTION]),reason='Actual RSeQC unavailable')
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('prepare_rna',ROOT/'scripts/prepare-rna-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def auth(client,config):
    client.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})


def hashes(directory):
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}


@pytest.fixture
def inputs(tmp_path):
    bam,bed=fixture.prepare(tmp_path/'inputs',SAMTOOLS)
    config=Settings(roots=[bam.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',samtools=SAMTOOLS,
                    rseqc_infer=INFER,rseqc_distribution=DISTRIBUTION,rna_annotations={'genes':str(bed)},cpus=1,memory_mb=2048,allow_root=True)
    return config,bam,bed


@pytest.mark.parametrize('mode',['rseqc-infer','rseqc-distribution'])
def test_actual_reports_downloads_provenance_restart_and_rerun(inputs,mode):
    config,bam,bed=inputs;before=hashes(bam.parent)
    tool=INFER if mode=='rseqc-infer' else DISTRIBUTION
    args=['-s','200000','-q','30'] if mode=='rseqc-infer' else []
    expected=subprocess.run([tool,'-i',str(bam),'-r',str(bed),*args],check=True,capture_output=True).stdout
    with TestClient(create_app(config)) as client:
        assert client.get('/api/config').status_code==401
        auth(client,config)
        created=client.post('/api/runs',json={'mode':mode,'paths':[str(bam)],'qc_options':{'annotation':'genes'}})
        assert created.status_code==201,created.text
        run=wait(client,created.json()['id'],timeout=60)
        assert run['state']=='completed',(run['error'],(config.output/run['id']/'analysis.log').read_text())
        result=run['qc']['results'][0]['rseqc']
        assert not run['input_pairing'] and not run['sample_groups'] and not run.get('derived_datasets')
        assert run['qc']['annotation']['sha256']==before[str(bed)]
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':result['reports']['stdout']}).content==expected
        assert all(e['exit_code']==0 for e in run['executions'])
        assert not any(e['argv'][1] in {'index','sort','view'} for e in run['executions'])
        if mode=='rseqc-infer':
            assert result['sampled_alignments']=='10' and [r[1] for r in result['rows']]==['0.2000','0.6000','0.2000']
            assert 'Total 10 usable reads were sampled' in (config.output/run['id']/'analysis.log').read_text()
        else:
            assert result['totals']==[['Total Reads','10'],['Total Tags','11'],['Total Assigned Tags','11']]
            assert result['rows'][0]==['CDS_Exons','3000','7','2.33'] and result['rows'][3]==['Introns','6000','4','0.67']
        assert client.get('/api/history',params={'mode':mode}).json()['total']==1
        draft=client.get('/api/runs/'+run['id']+'/configuration').json()
        assert draft['qc_options']['annotation']=='genes'
        saved=Path('validation/rseqc')/mode
        shutil.copytree(config.output/run['id'],saved,dirs_exist_ok=True)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        assert client.get('/api/runs/'+run['id']).json()['qc']==run['qc']
        assert client.get(f'/api/runs/{run["id"]}/download',params={'path':result['reports']['stdout']}).status_code==200
        rerun=client.post('/api/runs',json={'mode':mode,'paths':[str(bam)],'qc_options':draft['qc_options'],'rerun_of':run['id']})
        assert rerun.status_code==201 and rerun.json()['id']!=run['id']
        assert wait(client,rerun.json()['id'],timeout=60)['state']=='completed'
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('population,expected',[('stranded',['0.0000','1.0000','0.0000']),('unstranded',['0.0000','0.5000','0.5000'])])
def test_independently_defined_orientations_are_not_protocol_thresholds(inputs,population,expected):
    config,bam,bed=inputs;bam,bed=fixture.prepare(bam.parent,SAMTOOLS,population)
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='completed',run['error']
        assert [r[1] for r in run['qc']['results'][0]['rseqc']['rows']]==expected


def test_actual_single_end_and_zero_usable_records(inputs):
    config,bam,bed=inputs;fixture.prepare(bam.parent,SAMTOOLS,single=True)
    with TestClient(create_app(config)) as c:
        auth(c,config)
        run=wait(c,c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='completed' and run['qc']['results'][0]['rseqc']['layout']=='SingleEnd'
        empty=wait(c,c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes','mapq':61}}).json()['id'])
        result=empty['qc']['results'][0]['rseqc']
        assert empty['state']=='completed' and result['sampled_alignments']=='0' and result['rows']==[] and result['status']=='unavailable'


@pytest.mark.parametrize('fault',['contig','bounds','case','cram','invalid-bed','missing-source','pairing'])
def test_bad_inputs_are_not_scientific_success(inputs,fault):
    config,bam,bed=inputs
    if fault=='contig':bed.write_text(bed.read_text().replace('chrRNA','chrOther'))
    if fault=='bounds':bed.write_text(bed.read_text().replace('24000','34000').replace('1000,1000,\t0,3000,','1000,1000,\t0,13000,'))
    if fault=='case':bed.write_text(bed.read_text().replace('chrRNA','CHRRNA'))
    if fault=='invalid-bed':bed.write_text('chrRNA\t0\t100\n')
    if fault=='missing-source':bam.unlink()
    if fault=='cram':bam=bam.with_suffix('.cram');bam.write_bytes(b'CRAM'+b'not-qualified')
    payload={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}}
    if fault=='pairing':payload['input_pairing']=[{'path':str(bam),'paired':False}]
    with TestClient(create_app(config)) as c:
        auth(c,config);response=c.post('/api/runs',json=payload)
        if response.status_code==201:
            run=wait(c,response.json()['id'])
            assert run['state']=='failed' and not any(e['tool'].startswith('rseqc_') for e in run['executions'])
        else:assert response.status_code in {400,403,422},response.text


def test_paths_with_shell_and_html_characters_are_literal_and_collision_safe(inputs):
    config,bam,bed=inputs
    other=bam.parent/'other';other.mkdir();second=other/bam.name;shutil.copyfile(bam,second)
    renamed=bam.parent/'sample $(touch injected) <script>.bam';bam.rename(renamed)
    before=hashes(bam.parent)
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'rseqc-distribution','paths':[str(renamed),str(second)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='completed' and run['sample_count']==2
        assert len({r['id'] for r in run['qc']['results']})==2
        assert not (config.output/run['id']/'injected').exists()
        path=run['qc']['results'][0]['rseqc']['reports']['stdout']
        saved=config.output/run['id']/path;saved.unlink();saved.symlink_to(bed)
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':path}).status_code==403
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancel_and_restart_do_not_register_unfinished_reports(inputs,interrupt):
    config,bam,bed=inputs;before=hashes(bam.parent)
    launcher=config.output.parent/'slow-infer'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "--version" not in sys.argv:time.sleep(30)\nos.execv({INFER!r},[{INFER!r},*sys.argv[1:]])\n');launcher.chmod(0o700)
    config=replace(config,rseqc_infer=str(launcher))
    with TestClient(create_app(config)) as c:
        auth(c,config);response=c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}})
        assert response.status_code==201,response.text
        for _ in range(300):
            run=c.get('/api/runs/'+response.json()['id']).json()
            if any(e['tool']=='rseqc_infer' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Actual RNA stage not reached')
        if not interrupt:assert c.post('/api/runs/'+run['id']+'/cancel').status_code==200
    with TestClient(create_app(config)) as c:
        auth(c,config);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']==restored['qc']['results'][0]['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(p['path'].startswith('qc/') for p in restored['reports'])
    assert before==hashes(bam.parent)


def test_partial_success_and_zero_exit_malformed_report(inputs):
    config,bam,bed=inputs;other=bam.parent/'bad.bam';other.write_bytes(bam.read_bytes()[:-20])
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'rseqc-distribution','paths':[str(bam),str(other)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='partial' and run['sample_count']==1
        assert sum(r['state']=='completed' for r in run['qc']['results'])==1
    launcher=config.output.parent/'malformed-infer'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys\nif "--version" in sys.argv:os.execv({INFER!r},[{INFER!r},*sys.argv[1:]])\nprint("incomplete upstream report")\n');launcher.chmod(0o700)
    config=replace(config,rseqc_infer=str(launcher))
    with TestClient(create_app(config)) as c:
        auth(c,config);run=wait(c,c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='failed' and not any(p['path'].startswith('qc/') for p in run['reports'])


def test_queued_annotation_change_is_not_reinterpreted_as_saved_provenance(inputs):
    config,bam,bed=inputs
    with TestClient(create_app(config)) as c:
        auth(c,config);manager=c.app.state.manager
        c.portal.call(manager.slot.acquire)
        try:
            response=c.post('/api/runs',json={'mode':'rseqc-infer','paths':[str(bam)],'qc_options':{'annotation':'genes'}})
            assert response.status_code==201,response.text
            old=bed.stat();bed.write_text(bed.read_text().replace('plus','xxxx'))
            os.utime(bed,ns=(old.st_atime_ns,old.st_mtime_ns))
        finally:c.portal.call(manager.slot.release)
        run=wait(c,response.json()['id'])
        assert run['state']=='failed' and 'annotation changed' in run['error']
        assert not any(e['tool'].startswith('rseqc_') for e in run['executions'])


@pytest.mark.parametrize('mode',['rseqc-infer','rseqc-distribution'])
def test_public_galaxy_hg19_rnaseq_matches_independent_upstream_and_original_fixture(inputs,mode):
    from qualidock import rseqc
    config,bam,bed=inputs
    golden=Path(__file__).parent/'fixtures/rseqc-5.0.5/galaxy'
    shutil.copyfile(golden/'input.bam',bam);shutil.copyfile(golden/'genes.bed12',bed)
    before=hashes(bam.parent)
    tool=INFER if mode=='rseqc-infer' else DISTRIBUTION
    args=['-s','200000','-q','30'] if mode=='rseqc-infer' else []
    original=subprocess.run([tool,'-i',str(bam),'-r',str(bed),*args],capture_output=True,check=True)
    with TestClient(create_app(config)) as c:
        auth(c,config)
        run=wait(c,c.post('/api/runs',json={'mode':mode,'paths':[str(bam)],'qc_options':{'annotation':'genes'}}).json()['id'])
        assert run['state']=='completed',run['error']
        result=run['qc']['results'][0]['rseqc']
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':result['reports']['stdout']}).content==original.stdout
        if mode=='rseqc-infer':
            assert [r[1] for r in result['rows']]==['0.0000','1.0000','0.0000']
        else:
            assert result['totals']==[['Total Reads','40'],['Total Tags','44'],['Total Assigned Tags','38']]
            assert result['rows']==rseqc.distribution(golden/'upstream.read_distribution.txt')['rows']
        shutil.copytree(config.output/run['id'],Path('validation/rseqc')/('galaxy-'+mode),dirs_exist_ok=True)
    assert before==hashes(bam.parent)
