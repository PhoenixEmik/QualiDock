"""Actual BAM -> Picard RNA -> optional MultiQC; independent original CLI oracle."""
from dataclasses import replace
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
from qualidock import picard_rna as rna
from test_picard_real import JAVA,JAR,SAMTOOLS,auth,hashes
from test_picard_rna_qualification import STUDY
from test_workspace import wait

MULTIQC=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
if os.environ.get('QUALIDOCK_REQUIRE_PICARD_RNA_TESTS')=='1' and not all([SAMTOOLS,JAVA,JAR,MULTIQC,shutil.which('Rscript')]):
    raise RuntimeError('Actual Picard 3.5.0, Java17, SAMtools, R and MultiQC required')
pytestmark=pytest.mark.skipif(not all([SAMTOOLS,JAVA,JAR]),reason='Actual Picard RNA tools unavailable')


@pytest.fixture
def inputs(tmp_path):
    bam=STUDY.fixture(tmp_path/'inputs','categories')
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(bam.with_suffix('.sam'))],check=True,capture_output=True)
    config=Settings(roots=[bam.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',samtools=SAMTOOLS,java=JAVA,picard=JAR, multiqc=MULTIQC or 'multiqc',
        rna_refflat_annotations={'genes':str(bam.parent/'genes.refFlat')},rrna_intervals={'rrna':str(bam.parent/'rrna.interval_list')},cpus=1,memory_mb=1024,allow_root=True)
    return config,bam


def independent(cfg,bam,strand,rrna=None):
    output=cfg.output.parent/'independent.rna_metrics.txt'
    argv=[JAVA,'-Xms64m','-Xmx512m','-XX:ActiveProcessorCount=1','-jar',JAR,'CollectRnaSeqMetrics','INPUT='+str(bam),'OUTPUT='+str(output),
          'REF_FLAT='+cfg.rna_refflat_annotations['genes'],'STRAND_SPECIFICITY='+strand,'MINIMUM_LENGTH=500','END_BIAS_BASES=100','METRIC_ACCUMULATION_LEVEL=ALL_READS']
    if rrna:argv+=['RIBOSOMAL_INTERVALS='+cfg.rrna_intervals['rrna']]
    subprocess.run(argv,check=True,capture_output=True)
    return rna.parse(output)


def submit(c,bam,**options):
    response=c.post('/api/runs',json={'mode':'picard-rna','paths':[str(p) for p in (bam if isinstance(bam,list) else [bam])],'qc_options':{'annotation':'genes','strand':'NONE',**options}})
    assert response.status_code==201,response.text
    return wait(c,response.json()['id'],timeout=120)


@pytest.mark.parametrize('strand',STUDY.STRANDS)
@pytest.mark.parametrize('rrna',[None,'rrna'])
def test_genuine_categories_strand_rrna_original_reports_restart_and_rerun(inputs,strand,rrna):
    cfg,bam=inputs;before=hashes(bam.parent);expected=independent(cfg,bam,strand,rrna)
    with TestClient(create_app(cfg)) as c:
        assert c.get('/api/config').status_code==401
        auth(c,cfg);assert c.get('/api/config').json()['rna_refflat_annotations'][0]['available']
        run=submit(c,bam,strand=strand,rrna=rrna)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard']
        assert data['metrics']==expected['metrics'] and data['histogram']==expected['histogram']
        assert data['coverage_available'] is False and data['metrics']['rows'][0][24]=='0'
        assert run['qc']['options']['strand']==strand and run['qc']['annotation']['sha256']==STUDY.digest(bam.parent/'genes.refFlat')
        command=next(e for e in run['executions'] if e['tool']=='picard')
        assert command['exit_code']==0 and '-Xmx576m' in command['argv'] and 'STRAND_SPECIFICITY='+strand in command['argv']
        assert 'METRIC_ACCUMULATION_LEVEL=ALL_READS' in command['argv']
        assert not run['input_pairing'] and not Path(str(bam)+'.bai').exists()
        report=run['qc']['results'][0]['report']
        original=c.get(f'/api/runs/{run["id"]}/download',params={'path':report})
        assert original.status_code==200 and original.content==(cfg.output/run['id']/report).read_bytes()
        assert 'attachment' in original.headers['content-disposition']
        assert c.get('/api/history?mode=picard-rna').json()['total']==1
        # Only explicitly verified files are published, even if a nearby PDF looks valid.
        stray=cfg.output/run['id']/Path(report).parent/'unverified.pdf';stray.write_bytes(b'%PDF-1.5\n%%EOF')
        c.app.state.manager.refresh_reports(c.app.state.manager.runs[run['id']])
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':str(stray.relative_to(cfg.output/run['id']))}).status_code==403
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['qc']==run['qc']
        draft=c.get('/api/runs/'+run['id']+'/configuration').json()
        assert draft['qc_options']==run['qc']['options']
        again=c.post('/api/runs',json={k:draft[k] for k in ('mode','paths','qc_options','threads')})
        assert again.status_code==201,again.text
        assert wait(c,again.json()['id'],timeout=60)['state']=='completed'
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('kind',['flat-plus','flat-minus','bias-plus','bias-minus','boundary-spliced','empty'])
def test_original_101_points_and_eligible_bias_semantics(tmp_path,kind):
    bam=STUDY.fixture(tmp_path/'inputs',kind)
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(bam.with_suffix('.sam'))],check=True,capture_output=True)
    cfg=Settings(roots=[bam.parent],output=tmp_path/'runs',frontend=tmp_path/'frontend',samtools=SAMTOOLS,java=JAVA,picard=JAR,
                 rna_refflat_annotations={'genes':str(bam.parent/'genes.refFlat')},allow_root=True)
    before=hashes(bam.parent);expected=independent(cfg,bam,'NONE')
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,bam)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard']
        assert data['metrics']==expected['metrics'] and data['histogram']==expected['histogram']
        assert data['coverage_available']==kind.startswith(('flat','bias'))
        if data['coverage_available']:
            assert [r[0] for r in data['histogram']['rows']]==list(map(str,range(101)))
    assert before==hashes(bam.parent)


def test_genuine_original_pdf(inputs):
    if not shutil.which('Rscript'):pytest.skip('Rscript mandatory in provisioned CI')
    cfg,source=inputs
    bam=STUDY.fixture(source.parent/'eligible','bias-plus')
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(bam.with_suffix('.sam'))],check=True,capture_output=True)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,bam,histogram_pdf=True)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['picard'];assert data['plot_status']=='available'
        response=c.get(f'/api/runs/{run["id"]}/download',params={'path':data['reports']['coverage_pdf']})
        assert response.content.startswith(b'%PDF-') and b'%%EOF' in response.content[-1024:]
        assert data['rscript_version']


@pytest.mark.parametrize('fault',['missing','cram','unsorted','contig','interval','queued-change','symlink'])
def test_preflight_failures_never_execute_picard(inputs,fault,monkeypatch):
    cfg,bam=inputs
    if fault=='missing':Path(cfg.rna_refflat_annotations['genes']).unlink()
    elif fault=='cram':bam=bam.with_suffix('.cram');bam.write_bytes(b'CRAMunqualified')
    elif fault=='unsorted':
        sam=bam.with_suffix('.sam');lines=sam.read_text().splitlines()
        sam.write_text('\n'.join([*[l for l in lines if l.startswith('@')],*reversed([l for l in lines if not l.startswith('@')])])+'\n')
        subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(sam)],check=True,capture_output=True)
    elif fault=='contig':
        path=Path(cfg.rna_refflat_annotations['genes']);path.write_text(path.read_text().replace('chrRNA','other'))
    elif fault=='interval':
        path=Path(cfg.rrna_intervals['rrna']);path.write_text(path.read_text().replace('LN:3000','LN:3001'))
    elif fault=='symlink':
        path=Path(cfg.rna_refflat_annotations['genes']);path.unlink();path.symlink_to(bam)
    elif fault=='queued-change':
        from qualidock.manager import RunManager
        original=RunManager.execute
        async def changed(manager,run):
            path=Path(cfg.rna_refflat_annotations['genes']);path.write_text(path.read_text().replace('geneA','geneB'))
            await original(manager,run)
        monkeypatch.setattr(RunManager,'execute',changed)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);response=c.post('/api/runs',json={'mode':'picard-rna','paths':[str(bam)],'qc_options':{'annotation':'genes','strand':'NONE','rrna':'rrna' if fault=='interval' else None}})
        if response.status_code==201:
            run=wait(c,response.json()['id'],timeout=60)
            assert run['state']=='failed' and not any(e['tool']=='picard' for e in run['executions'])
        else:assert response.status_code in {400,403,422},response.text


@pytest.mark.parametrize('failure',[None,'exit','incomplete'])
def test_genuine_multiqc_mapping_missing_histogram_duplicate_basenames_and_failures(inputs,failure):
    if not MULTIQC:pytest.skip('Actual MultiQC required')
    cfg,bam=inputs
    other=STUDY.fixture(bam.parent/'other','flat-plus')
    subprocess.run([SAMTOOLS,'view','-b','-o',str(other),str(other.with_suffix('.sam'))],check=True,capture_output=True)
    # Both reports use the same approved model. Header INPUT basenames collide.
    if failure:
        wrapper=cfg.output.parent/'bad-multiqc'
        wrapper.write_text(f'#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\nif "--version" in sys.argv:os.execv({MULTIQC!r},[{MULTIQC!r},*sys.argv[1:]])\np=Path(sys.argv[sys.argv.index("--outdir")+1]);p.mkdir(exist_ok=True)\n(p/"multiqc_report.html").write_text("<h1>Incomplete</h1>")\nsys.exit({9 if failure=="exit" else 0})\n');wrapper.chmod(0o700);cfg=replace(cfg,multiqc=str(wrapper))
    before=hashes(bam.parent)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,[bam,other],multiqc=True)
        assert run['state']==('partial' if failure else 'completed'),run['error']
        assert run['sample_count']==2
        if failure:
            assert run['qc']['multiqc_status']=='invalid'
            assert not any(r['path'].startswith('multiqc/') for r in run['reports'])
        else:
            assert run['qc']['multiqc_status']=='available'
            assert len({r['multiqc_name'] for r in run['report_input_map'].values()})==2
        for row in run['qc']['results']:
            assert c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']}).status_code==200
        evidence=Path('validation/picard-rna-production')/(failure or 'success')
        shutil.copytree(cfg.output/run['id'],evidence,dirs_exist_ok=True)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['qc']==run['qc']
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancel_restart_and_immutability(inputs,interrupt):
    cfg,bam=inputs;before=hashes(bam.parent)
    wrapper=cfg.output.parent/'slow-java'
    wrapper.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "CollectRnaSeqMetrics" in sys.argv:time.sleep(30)\nos.execv({JAVA!r},[{JAVA!r},*sys.argv[1:]])\n');wrapper.chmod(0o700);cfg=replace(cfg,java=str(wrapper))
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);response=c.post('/api/runs',json={'mode':'picard-rna','paths':[str(bam)],'qc_options':{'annotation':'genes','strand':'NONE'}})
        assert response.status_code==201,response.text
        for _ in range(300):
            run=c.get('/api/runs/'+response.json()['id']).json()
            if any(e['tool']=='picard' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Did not reach actual Picard execution')
        if not interrupt:c.post('/api/runs/'+run['id']+'/cancel')
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']==restored['qc']['results'][0]['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(p['path'].startswith('qc/') for p in restored['reports'])
    assert before==hashes(bam.parent)


def test_optional_plot_failure_retains_only_verified_numeric_results(inputs,monkeypatch):
    cfg,source=inputs
    bam=STUDY.fixture(source.parent/'eligible','bias-plus')
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bam),str(bam.with_suffix('.sam'))],check=True,capture_output=True)
    before=hashes(bam.parent)
    runtime=cfg.output.parent/'runtime';runtime.mkdir()
    rscript=runtime/'Rscript'
    # Failure-only dependency probe; all scientific metrics come from the real JAR.
    rscript.write_text(f'#!{sys.executable}\nimport sys\nif "--version" in sys.argv:print("Rscript (R) version 4.4.1");sys.exit(0)\nsys.exit(7)\n')
    rscript.chmod(0o700)
    monkeypatch.setenv('PATH',str(runtime)+os.pathsep+os.environ['PATH'])
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,bam,histogram_pdf=True)
        assert run['state']=='partial',run['error']
        result=run['qc']['results'][0]
        assert result['state']=='completed' and result['exit_code']==1
        assert result['picard']['plot_status']=='unavailable'
        assert result['picard']['metrics']['rows'][0][0]=='803'
        assert 'coverage_pdf' not in result['picard']['reports']
        assert not any(r['path'].endswith('.pdf') for r in run['reports'])
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':result['report']}).status_code==200
        assert 'PDF' in run['error']
    assert before==hashes(bam.parent)


def test_partial_input_failure_and_literal_unsafe_sample_names(inputs):
    cfg,bam=inputs;other=bam.parent/'bad.bam';other.write_bytes(bam.read_bytes()[:-20])
    literal=bam.parent/'sample $(touch injected) <img>.bam';bam.rename(literal)
    before=hashes(bam.parent)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,[literal,other])
        assert run['state']=='partial' and run['sample_count']==1
        assert [r['state'] for r in run['qc']['results']]==['completed','failed']
        assert not (cfg.output/run['id']/'injected').exists()
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':run['qc']['results'][0]['report']}).status_code==200
    assert before==hashes(bam.parent)


def test_changed_annotation_during_real_execution_invalidates_results(inputs,monkeypatch):
    from qualidock.manager import RunManager
    cfg,bam=inputs
    original=RunManager.command
    async def changed(manager,run,tool,*args,**kwargs):
        code=await original(manager,run,tool,*args,**kwargs)
        if tool=='picard':
            path=Path(cfg.rna_refflat_annotations['genes'])
            path.write_text(path.read_text().replace('geneA','geneB'))
        return code
    monkeypatch.setattr(RunManager,'command',changed)
    with TestClient(create_app(cfg)) as c:
        auth(c,cfg);run=submit(c,bam)
        assert run['state']=='failed' and 'changed' in run['error']
        assert any(e['tool']=='picard' and e['exit_code']==0 for e in run['executions'])
        assert not any(r['path'].startswith('qc/') for r in run['reports'])
