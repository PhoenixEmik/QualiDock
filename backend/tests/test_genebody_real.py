"""Real RSeQC 5.0.5 + SAMtools; assertions inspect the original coverage bytes."""
from dataclasses import replace
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

ROOT=Path(__file__).resolve().parents[2]
SAM=shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
TOOL=shutil.which(os.environ.get('QUALIDOCK_RSEQC_GENEBODY','geneBody_coverage.py'))
if os.environ.get('QUALIDOCK_REQUIRE_GENEBODY_TESTS')=='1' and not all([SAM,TOOL]):
    raise RuntimeError('Actual RSeQC geneBody_coverage and SAMtools are required')
pytestmark=pytest.mark.skipif(not all([SAM,TOOL]),reason='Genuine gene-body tools not installed')
spec=importlib.util.spec_from_file_location('gene_fixture',ROOT/'scripts/prepare-rna-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def hashes(root):return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
def auth(c,s):c.headers.update({'Authorization':'Bearer '+s.token,'X-QualiDock-Request':'1'})


@pytest.fixture
def inputs(tmp_path):
    bam,bed=fixture.prepare(tmp_path/'inputs',SAM)
    subprocess.run([SAM,'index',str(bam)],check=True)
    settings=Settings(roots=[bam.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',samtools=SAM,
        rseqc_genebody=TOOL,rna_annotations={'genes':str(bed)},cpus=1,memory_mb=2048,allow_root=True)
    return settings,bam,bed


def launch(c,bam,**options):
    response=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(bam)],'qc_options':{'annotation':'genes',**options}})
    assert response.status_code==201,response.text
    return wait(c,response.json()['id'],timeout=60)


@pytest.mark.parametrize('index_format',['bai','csi','stem-bai'])
def test_genuine_original_profile_restart_rerun_and_source_index_immutability(inputs,index_format,tmp_path):
    s,bam,bed=inputs
    if index_format=='csi':
        Path(str(bam)+'.bai').unlink();subprocess.run([SAM,'index','-c',str(bam)],check=True)
    if index_format=='stem-bai':Path(str(bam)+'.bai').rename(bam.with_suffix('.bai'))
    before=hashes(bam.parent)
    expected=tmp_path/'independent'
    subprocess.run([TOOL,'-i',str(bam),'-r',str(bed),'-o',str(expected),'--skip-plot'],capture_output=True,cwd=tmp_path)
    # Upstream discovery only accepts .bam.bai: independently expose the same
    # authorized CSI/stem BAI under its required companion name in a test directory.
    if index_format!='bai':
        alias=tmp_path/'input.bam';alias.symlink_to(bam)
        Path(str(alias)+'.bai').symlink_to(Path(str(bam)+'.csi') if index_format=='csi' else bam.with_suffix('.bai'))
        subprocess.run([TOOL,'-i',str(alias),'-r',str(bed),'-o',str(expected),'--skip-plot'],check=True,capture_output=True,cwd=tmp_path)
    original=Path(str(expected)+'.geneBodyCoverage.txt').read_text().splitlines()[1].split('\t')[1:]
    with TestClient(create_app(s)) as c:
        assert c.get('/api/config').status_code==401;auth(c,s)
        run=launch(c,bam)
        assert run['state']=='completed',(run['error'],(s.output/run['id']/'analysis.log').read_text())
        row=run['qc']['results'][0];data=row['rseqc']
        assert [r[1] for r in data['rows']]==original
        assert data['sample']==row['id'] and data['source_sha256']==before[str(bam)]
        assert data['index']['sha256']==before[data['index']['path']]
        report=data['reports']['percentile_table']
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':report}).status_code==200
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':report},headers={'Authorization':''}).status_code==401
        assert not any(e['tool']=='samtools' and e['argv'][1] in {'index','sort'} for e in run['executions'])
        assert not run['input_pairing'] and not run.get('derived_datasets')
        private=f'qc/{row["id"]}/private/references.bed'
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':private}).status_code==403
        draft=c.get('/api/runs/'+run['id']+'/configuration').json()
        assert draft['qc_options']['minimum_length']==100
        saved=ROOT/'validation/genebody'/index_format;shutil.copytree(s.output/run['id'],saved,dirs_exist_ok=True,ignore=shutil.ignore_patterns('private'))
    with TestClient(create_app(s)) as c:
        auth(c,s);assert c.get('/api/runs/'+run['id']).json()['qc']==run['qc']
        assert launch(c,bam,**draft['qc_options'])['state']=='completed'
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('fault',['missing-index','corrupt-index','truncated-index','foreign-index','annotation','unsorted','escape-index'])
def test_invalid_alignment_annotation_or_index_never_publish(inputs,fault,tmp_path):
    s,bam,bed=inputs;index=Path(str(bam)+'.bai')
    if fault=='missing-index':index.unlink()
    elif fault=='corrupt-index':index.write_bytes(b'not-an-index')
    elif fault=='truncated-index':index.write_bytes(b'BAI\x01')
    elif fault=='foreign-index':
        empty=bam.parent/'empty.sam';empty.write_text('@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chrRNA\tLN:30000\n')
        other=bam.parent/'empty.bam';subprocess.run([SAM,'view','-b','-o',str(other),str(empty)],check=True)
        subprocess.run([SAM,'index','-o',str(index),str(other)],check=True)
    elif fault=='escape-index':
        outside=tmp_path/'outside.bai';index.rename(outside);index.symlink_to(outside)
    elif fault=='annotation':bed.write_text(bed.read_text().replace('chrRNA','wrong'))
    elif fault=='unsorted':
        sam=bam.with_suffix('.sam');lines=sam.read_text().splitlines();head=[l for l in lines if l.startswith('@')];body=[l for l in lines if not l.startswith('@')]
        sam.write_text('\n'.join(head+list(reversed(body)))+'\n');subprocess.run([SAM,'view','-b','-o',str(bam),str(sam)],check=True)
    before=hashes(bam.parent)
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam)
        assert run['state']=='failed',run
        assert not any(r['path'].endswith('.geneBodyCoverage.txt') for r in run['reports'])
    assert before==hashes(bam.parent)


def test_short_transcript_unavailable_and_partial_inputs(inputs):
    s,bam,bed=inputs
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam,minimum_length=100000)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['rseqc'];assert data['status']=='unavailable' and data['rows']==[]
        missing=bam.parent/'missing-index.bam';shutil.copyfile(bam,missing)
        result=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(bam),str(missing)],'qc_options':{'annotation':'genes'}})
        partial=wait(c,result.json()['id'])
        assert partial['state']=='partial' and [r['state'] for r in partial['qc']['results']]==['completed','failed']


def test_unsafe_names_use_safe_alias_and_optional_plot_is_truthful(inputs):
    s,bam,bed=inputs
    strange=bam.with_name('comma, quote\" $(touch bad).bam');bam.rename(strange);Path(str(bam)+'.bai').rename(Path(str(strange)+'.bai'))
    before=hashes(bam.parent)
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,strange,original_plot=True)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['rseqc'];plot=data['plot']
        if shutil.which('Rscript'):
            assert plot['status']=='completed',plot
            from qualidock.rseqc import checked_png
            checked_png(s.output/run['id']/data['reports']['original_png'])
        else:assert plot['status'].startswith('unavailable')
        assert not (s.output/run['id']/'bad').exists()
    assert before==hashes(bam.parent)


def test_zero_signal_preserves_original_zeros_without_meaningful_curve(inputs):
    s,bam,bed=inputs
    bed.write_text('chrRNA\t0\t500\tuncovered\t0\t+\t0\t500\t0\t1\t500\t0\n')
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['rseqc'];assert data['status']=='unavailable'
        assert len(data['rows'])==100 and all(float(v)==0 for _,v in data['rows'])


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancellation_and_restart_preserve_sources_without_publishing_partial_outputs(inputs,interrupt):
    import sys
    s,bam,bed=inputs;before=hashes(bam.parent)
    launcher=bam.parent.parent/'slow-genebody'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "--version" not in sys.argv:time.sleep(30)\nos.execv({TOOL!r},[{TOOL!r},*sys.argv[1:]])\n');launcher.chmod(0o700)
    s=replace(s,rseqc_genebody=str(launcher))
    with TestClient(create_app(s)) as c:
        auth(c,s);response=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(bam)],'qc_options':{'annotation':'genes'}})
        assert response.status_code==201,response.text
        for _ in range(500):
            run=c.get('/api/runs/'+response.json()['id']).json()
            if any(e['tool']=='rseqc_genebody' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Gene-body stage not reached')
        if not interrupt:assert c.post('/api/runs/'+run['id']+'/cancel').status_code==200
    with TestClient(create_app(s)) as c:
        auth(c,s);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']==restored['qc']['results'][0]['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(r['path'].startswith('qc/') for r in restored['reports'])
    assert before==hashes(bam.parent)


def test_failed_original_r_plot_preserves_numeric_report_but_never_registers_png(inputs,monkeypatch,tmp_path):
    import sys
    fake=tmp_path/'Rscript';fake.write_text(f'#!{sys.executable}\nimport sys\nif "--version" in sys.argv:print("Test-only failing R runtime");sys.exit(0)\nfrom pathlib import Path\nPath(sys.argv[-1].removesuffix(".r")+".curves.png").write_bytes(b"partial PNG")\nsys.exit(9)\n');fake.chmod(0o700)
    monkeypatch.setenv('PATH',str(tmp_path)+os.pathsep+os.environ.get('PATH',''))
    s,bam,bed=inputs
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam,original_plot=True)
        assert run['state']=='completed',run['error']
        row=run['qc']['results'][0];data=row['rseqc']
        assert data['status']=='available' and data['plot']['status'].startswith('unavailable')
        path=f'qc/{row["id"]}/{row["id"]}.geneBodyCoverage.curves.png'
        assert (s.output/run['id']/path).exists()
        assert path not in {r['path'] for r in run['reports']}
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':path}).status_code==403
    with TestClient(create_app(s)) as c:
        auth(c,s);assert c.get(f'/api/runs/{run["id"]}/download',params={'path':path}).status_code==403


def test_missing_executable_and_cram_are_explicit(inputs):
    s,bam,bed=inputs
    with TestClient(create_app(replace(s,rseqc_genebody='/missing/geneBody_coverage.py'))) as c:
        auth(c,s)
        response=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(bam)],'qc_options':{'annotation':'genes'}})
        assert response.status_code==400
    cram=bam.with_suffix('.cram');cram.write_bytes(b'CRAM'+b'\0'*32)
    with TestClient(create_app(s)) as c:
        auth(c,s)
        response=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(cram)],'qc_options':{'annotation':'genes'}})
        assert response.status_code==400 and 'BAM only' in response.text


@pytest.mark.skipif(not shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc')),reason='Genuine MultiQC required')
def test_actual_multibam_duplicate_basenames_remain_traceable(inputs):
    s,bam,bed=inputs
    s=replace(s,multiqc=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc')))
    other=bam.parent/'other';other.mkdir();second=other/bam.name;shutil.copyfile(bam,second)
    shutil.copyfile(Path(str(bam)+'.bai'),Path(str(second)+'.bai'))
    with TestClient(create_app(s)) as c:
        auth(c,s)
        response=c.post('/api/runs',json={'mode':'rseqc-genebody','paths':[str(bam),str(second)],'qc_options':{'annotation':'genes','multiqc':True}})
        assert response.status_code==201,response.text
        run=wait(c,response.json()['id'],timeout=120)
        assert run['state']=='completed',run['error']
        names=[run['report_input_map'][r['report']]['multiqc_name'] for r in run['qc']['results']]
        assert len(set(names))==2
        assert all(r['rseqc']['sample']==name for r,name in zip(run['qc']['results'],names))


def test_uniform_positive_profile_retains_exact_native_curve_without_fake_r_normalization(inputs):
    s,bam,bed=inputs
    bed.write_text('chrRNA\t1000\t1500\tuniform\t0\t+\t1000\t1500\t0\t1\t500\t0\n')
    sam=bam.with_suffix('.sam');sam.write_text('@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chrRNA\tLN:30000\n'+
        'uniform\t0\tchrRNA\t1001\t60\t500M\t*\t0\t0\t'+'A'*500+'\t'+'I'*500+'\n')
    subprocess.run([SAM,'view','-b','-o',str(bam),str(sam)],check=True)
    subprocess.run([SAM,'index',str(bam)],check=True)
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam,original_plot=True)
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['rseqc'];assert data['status']=='available'
        assert len(data['rows'])==100 and all(float(v)==1 for _,v in data['rows'])
        assert 'undefined' in data['plot']['status'] and 'original_png' not in data['reports']


@pytest.mark.parametrize('target',['bam','index','annotation'])
def test_changed_input_identity_rejects_even_an_original_complete_table(inputs,target):
    import sys
    s,bam,bed=inputs
    changed={'bam':bam,'index':Path(str(bam)+'.bai'),'annotation':bed}[target]
    launcher=bam.parent.parent/'mutation-test-only'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,subprocess\nfrom pathlib import Path\nif "--version" in sys.argv:os.execv({TOOL!r},[{TOOL!r},*sys.argv[1:]])\nr=subprocess.run([{TOOL!r},*sys.argv[1:]])\nwith Path({str(changed)!r}).open("ab") as f:f.write(b"\\n")\nsys.exit(r.returncode)\n');launcher.chmod(0o700)
    s=replace(s,rseqc_genebody=str(launcher))
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam)
        assert run['state']=='failed' and not any(r['path'].startswith('qc/') for r in run['reports'])
        assert 'changed' in run['error'].lower()


def test_public_galaxy_hg19_profile_matches_independent_upstream(inputs,tmp_path):
    s,bam,bed=inputs
    golden=ROOT/'backend/tests/fixtures/rseqc-5.0.5/galaxy'
    subprocess.run([SAM,'sort','-o',str(bam),str(golden/'input.bam')],check=True)
    shutil.copyfile(golden/'genes.bed12',bed)
    subprocess.run([SAM,'index',str(bam)],check=True)
    before=hashes(bam.parent);prefix=tmp_path/'galaxy-original'
    subprocess.run([TOOL,'-i',str(bam),'-r',str(bed),'-o',str(prefix),'--skip-plot'],check=True,capture_output=True,cwd=tmp_path)
    expected=Path(str(prefix)+'.geneBodyCoverage.txt').read_text().splitlines()[1].split('\t')[1:]
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam)
        assert run['state']=='completed',run['error']
        assert [v for _,v in run['qc']['results'][0]['rseqc']['rows']]==expected
        shutil.copytree(s.output/run['id'],ROOT/'validation/genebody/galaxy',dirs_exist_ok=True,ignore=shutil.ignore_patterns('private'))
    assert before==hashes(bam.parent)


@pytest.mark.parametrize('fault',['identity','nan','duplicate-percentile'])
def test_exit_zero_cannot_publish_mutated_original_table(inputs,fault):
    import sys
    s,bam,bed=inputs
    mutate={'identity':"rows[1][0]='wrong-input'",'nan':"rows[1][8]='NaN'",'duplicate-percentile':"rows[0][10]=rows[0][9]"}[fault]
    launcher=bam.parent.parent/'malformed-test-only'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,subprocess\nfrom pathlib import Path\nif "--version" in sys.argv:os.execv({TOOL!r},[{TOOL!r},*sys.argv[1:]])\nsubprocess.run([{TOOL!r},*sys.argv[1:]],check=True)\np=Path(sys.argv[sys.argv.index("-o")+1]+".geneBodyCoverage.txt")\nrows=[s.split("\\t") for s in p.read_text().splitlines()]\n{mutate}\np.write_text("\\n".join("\\t".join(r) for r in rows)+"\\n")\n');launcher.chmod(0o700)
    s=replace(s,rseqc_genebody=str(launcher))
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam)
        assert run['state']=='failed' and not any(r['path'].startswith('qc/') for r in run['reports'])
        assert next(e for e in run['executions'] if e['tool']=='rseqc_genebody')['exit_code']==0


def test_special_output_root_cannot_be_interpreted_as_htslib_index_syntax(inputs):
    s,bam,bed=inputs;s=replace(s,output=s.output.parent/'results ##idx## "quoted"')
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam,original_plot=bool(shutil.which("Rscript")))
        assert run['state']=='completed',run['error']
        index_command=next(e['argv'] for e in run['executions'] if e['tool']=='samtools' and e['argv'][1]=='view')
        assert index_command[-1].count('##idx##')==1
        assert index_command[-1].startswith('qc/')


@pytest.mark.skipif(not shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc')),reason='Genuine MultiQC required')
def test_failed_genuine_multqc_keeps_gene_body_originals_but_not_failed_bundle(inputs):
    import sys
    s,bam,bed=inputs;actual=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
    launcher=bam.parent.parent/'failed-multiqc-test-only'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,subprocess\nif "--version" in sys.argv:os.execv({actual!r},[{actual!r},*sys.argv[1:]])\nsubprocess.run([{actual!r},*sys.argv[1:]],check=True)\nsys.exit(9)\n');launcher.chmod(0o700)
    s=replace(s,multiqc=str(launcher))
    with TestClient(create_app(s)) as c:
        auth(c,s);run=launch(c,bam,multiqc=True)
        assert run['state']=='partial',run['error']
        row=run['qc']['results'][0];assert row['state']=='completed' and row['rseqc']['status']=='available'
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']}).status_code==200
        assert (s.output/run['id']/'multiqc/multiqc_report.html').exists()
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'multiqc/multiqc_report.html'}).status_code==403
    with TestClient(create_app(s)) as c:
        auth(c,s)
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']}).status_code==200
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'multiqc/multiqc_report.html'}).status_code==403
