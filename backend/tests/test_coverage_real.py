"""Actual mosdepth 0.3.14 over independently defined small SAM records."""
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
from test_alignment_real import fixture, auth, digest

SAMTOOLS = shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
MOSDEPTH = shutil.which(os.environ.get('QUALIDOCK_MOSDEPTH','mosdepth'))
if os.environ.get('QUALIDOCK_REQUIRE_COVERAGE_TESTS') == '1' and not (SAMTOOLS and MOSDEPTH):
    raise RuntimeError('Actual mosdepth and SAMtools required')
pytestmark = pytest.mark.skipif(not (SAMTOOLS and MOSDEPTH), reason='Actual mosdepth/SAMtools unavailable')


@pytest.fixture
def coverage_inputs(tmp_path):
    bam,cram,ref = fixture.prepare(tmp_path/'inputs',SAMTOOLS)
    for source in (bam,cram):subprocess.run([SAMTOOLS,'index',str(source)],check=True,capture_output=True)
    panel = ref.parent/'panel.bed'
    panel.write_text('chr1\t0\t15\tpair\nchr1\t20\t25\tsupplementary\nchr1\t30\t35\tduplicate\nchr1\t50\t55\tsingle\nchr2\t0\t10\tzero\n')
    config = Settings(roots=[ref.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',token='coverage-test',
        samtools=SAMTOOLS,mosdepth=MOSDEPTH,alignment_references={'test':str(ref)},coverage_panels={'test':str(panel)},cpus=1,memory_mb=2048,allow_root=True)
    return config,bam,cram,ref,panel


@pytest.mark.parametrize('kind',['bam','cram'])
@pytest.mark.parametrize('regional',[False,True])
def test_actual_coverage_and_exact_original_reports(coverage_inputs,kind,regional):
    config,bam,cram,ref,bed = coverage_inputs
    source = bam if kind == 'bam' else cram
    hashes = {p:digest(p) for p in source.parent.iterdir()}
    independent = source.parent.parent/'independent';independent.mkdir()
    prefix = independent/'standalone'
    argv = [MOSDEPTH,'--no-per-base','--threads','0','--flag','1796','--mapq','0']
    if kind == 'cram':argv += ['--fasta',str(ref)]
    if regional:argv += ['--by',str(bed),'--thresholds','1,10,20,30']
    subprocess.run([*argv,str(prefix),str(source)],check=True,capture_output=True,env={**os.environ,'MOSDEPTH_PRECISION':'5','REF_PATH':'/dev/null','REF_CACHE':'/dev/null'})
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created = c.post('/api/runs',json={'mode':'mosdepth','paths':[str(source)],'qc_options':{'reference':'test' if kind == 'cram' else None,'panel':'test' if regional else None}})
        assert created.status_code == 201,created.text
        run = wait(c,created.json()['id'],timeout=60)
        retained=Path('validation/coverage')/(kind+('-bed' if regional else '-global'))
        shutil.copytree(config.output/run['id'],retained,dirs_exist_ok=True)
        assert run['state'] == 'completed',(run['error'],(config.output/run['id']/'analysis.log').read_text()[-5000:])
        assert run['tools']['mosdepth']['version'] == '0.3.14'
        row = run['qc']['results'][0];data = row['mosdepth']
        # Pair overlap correction: 15 pair bases + 5 supplementary + 5 single.
        # Secondary/QC-failed/duplicate/unmapped are excluded by original 1796.
        assert data['total'] == ['total','100','25','0.25000','0','1']
        assert data['distribution']['rows'] == [['1','0.25000'],['0','1.00000']]
        assert data['reported_reference_bases'] == 100 and data['header_reference_bases'] == 150
        assert data['omitted_references'] == ['chr2'] and data['omitted_reference_count'] == 1
        assert not run['input_pairing'] and not run['sample_groups'] and not run.get('derived_datasets')
        if regional:
            assert data['requested_region_bases'] == 40 and data['reported_region_bases'] == 30
            assert [r[4] for r in data['thresholds']['rows']] == ['15','5','0','5','0']
            assert all(r[5:] == ['0','0','0'] for r in data['thresholds']['rows'])
            assert data['regions']['rows'][-1] == ['chr2','0','10','zero','0.00000']
        for name,path in data['reports'].items():
            response = c.get(f'/api/runs/{run["id"]}/download',params={'path':path})
            assert response.status_code == 200,(path,response.text[:100])
            assert response.content == (config.output/run['id']/path).read_bytes()
            if name in {'summary','global_distribution','regional_distribution'}:
                assert response.content == Path(str(prefix)+path[path.rfind(row['id'])+len(row['id']):]).read_bytes()
            if name in {'regions','thresholds'}:
                suffix = '.'+name+'.bed.gz'
                assert gzip.decompress(response.content) == gzip.decompress(Path(str(prefix)+suffix).read_bytes())
        execution = next(e for e in run['executions'] if e['tool'] == 'mosdepth')
        assert '--no-per-base' in execution['argv'] and '--fast-mode' not in execution['argv'] and '--fragment-mode' not in execution['argv']
        assert '##idx##' in execution['argv'][-1] and execution['environment']['MOSDEPTH_PRECISION'] == '5'
        assert not list((config.output/run['id']).rglob('*.per-base.*'))
        assert not any(e['argv'][1] in {'sort','index','view','faidx'} for e in run['executions'] if e['tool'] == 'samtools')
        assert c.post(f'/api/runs/{run["id"]}/integrity',json={'mode':'full'}).status_code == 400
        assert c.get(f'/api/runs/{run["id"]}/configuration').json()['qc_options'] == run['qc']['options']
    with TestClient(create_app(config)) as c:
        auth(c,config)
        restored=c.get('/api/runs/'+run['id']).json()
        assert restored['qc'] == run['qc']
        assert c.get('/api/history?mode=mosdepth').json()['total'] == 1
    assert hashes == {p:digest(p) for p in source.parent.iterdir()}


@pytest.mark.parametrize('fault',['missing','magic','truncated','escape'])
def test_invalid_or_unavailable_indexes_do_not_publish(coverage_inputs,fault):
    config,bam,cram,ref,bed=coverage_inputs
    idx=Path(str(bam)+'.bai');original=idx.read_bytes();source_hash=digest(bam)
    if fault=='missing':idx.unlink()
    if fault=='magic':idx.write_bytes(b'not an index')
    if fault=='truncated':idx.write_bytes(b'BAI\x01')
    if fault=='escape':
        outside=bam.parent.parent/'outside.bai';outside.write_bytes(original);idx.unlink();idx.symlink_to(outside)
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)]})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and not run['sample_count']
        assert not any(p['path'].startswith('qc/') for p in run['reports'])
        if fault=='missing':
            sam=c.post('/api/runs',json={'mode':'samtools','paths':[str(bam)]})
            assert wait(c,sam.json()['id'])['state']=='completed'
    assert digest(bam)==source_hash


def test_claimed_sort_order_does_not_replace_full_record_check(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    sam=bam.parent/'unsorted.sam'
    original=(Path(__file__).parent/'fixtures/samtools-1.22.1/input.sam').read_text().splitlines()
    header=[l for l in original if l.startswith('@')];records=[l for l in original if not l.startswith('@')]
    sam.write_text('\n'.join([*header,records[6],*records[:6],records[7]])+'\n')
    bad=bam.parent/'unsorted.bam'
    subprocess.run([SAMTOOLS,'view','-b','-o',str(bad),str(sam)],check=True,capture_output=True)
    shutil.copyfile(Path(str(bam)+'.bai'),Path(str(bad)+'.bai'))
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bad)]})
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and 'coordinate-sorted' in run['error']
        assert not any(e['tool']=='mosdepth' for e in run['executions'])


@pytest.mark.parametrize('options,expected_bases',[({'exclude_supplementary':True},'20'),({'mapq':61},'0')])
def test_actual_filter_semantics_and_zero_coverage(coverage_inputs,options,expected_bases):
    config,bam,cram,ref,bed=coverage_inputs
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'qc_options':options})
        run=wait(c,created.json()['id'])
        assert run['state']=='completed',run['error']
        assert run['qc']['results'][0]['mosdepth']['total'][2]==expected_bases


def test_only_unreported_contig_bed_is_not_fabricated_into_global_total(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    bed.write_text('chr2\t0\t10\tzero\n')
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'qc_options':{'panel':'test'}})
        run=wait(c,created.json()['id'])
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['mosdepth']
        assert data['requested_region_bases']==10 and data['reported_region_bases']==0
        assert data['thresholds']['rows']==[['chr2','0','10','zero','0','0','0','0']]
        assert data['reported_reference_bases']==100 and data['total'][2]=='25'


def test_wrong_cram_reference_and_bed_bounds_fail_before_coverage(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    wrong=ref.parent/'wrong.fa';wrong.write_text(ref.read_text().replace('A','T'))
    subprocess.run([SAMTOOLS,'faidx',str(wrong)],check=True,capture_output=True)
    bad=replace(config,alignment_references={'wrong':str(wrong)})
    with TestClient(create_app(bad)) as c:
        auth(c,bad)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(cram)],'qc_options':{'reference':'wrong'}})
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and not any(e['tool']=='mosdepth' for e in run['executions'])
    bed.write_text('chr1\t0\t101\toutside\n')
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'qc_options':{'panel':'test'}})
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and 'outside' in run['error']
        assert not any(e['tool']=='mosdepth' for e in run['executions'])


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancelled_or_interrupted_outputs_are_not_published(coverage_inputs,interrupt):
    config,bam,cram,ref,bed=coverage_inputs
    launcher=bam.parent/'slow-mosdepth'
    launcher.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "--version" not in sys.argv: time.sleep(30)\nos.execv({MOSDEPTH!r},[{MOSDEPTH!r},*sys.argv[1:]])\n')
    launcher.chmod(0o700);config=replace(config,mosdepth=str(launcher));before=digest(bam)
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)]})
        assert created.status_code==201,created.text
        for _ in range(200):
            run=c.get('/api/runs/'+created.json()['id']).json()
            if any(e['tool']=='mosdepth' for e in run['executions']):break
            time.sleep(.02)
        else:raise AssertionError('Actual SAMtools preflight/MOS stage not reached')
        if not interrupt:
            assert c.post(f'/api/runs/{run["id"]}/cancel').status_code==200
    with TestClient(create_app(config)) as c:
        auth(c,config)
        restored=c.get('/api/runs/'+run['id']).json()
        expected='interrupted' if interrupt else 'cancelled'
        assert restored['state']==restored['qc']['results'][0]['state']==expected
        assert not any(p['path'].startswith('qc/') for p in restored['reports'])
    assert digest(bam)==before


def test_csi_index_and_registered_regional_artifact_boundaries(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    subprocess.run([SAMTOOLS,'index','-c',str(bam)],check=True,capture_output=True)
    before={p:digest(p) for p in bam.parent.iterdir()}
    with TestClient(create_app(config)) as c:
        assert c.get('/api/config').status_code==401
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'qc_options':{'panel':'test'}})
        run=wait(c,created.json()['id'])
        assert run['state']=='completed',run['error']
        data=run['qc']['results'][0]['mosdepth']
        assert data['index']['path'].endswith('.csi')
        extra=Path(data['reports']['regions']).with_name('unregistered.fastq.gz')
        (config.output/run['id']/extra).write_bytes(gzip.compress(b'@read\nA\n+\nI\n'))
        c.app.state.manager.refresh_reports(c.app.state.manager.runs[run['id']])
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':str(extra)}).status_code==403
        artifact=config.output/run['id']/data['reports']['thresholds']
        artifact.unlink();artifact.symlink_to(bed)
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':data['reports']['thresholds']}).status_code==403
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'../outside.gz'}).status_code==403
        assert c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'qc_options':{'index':'/etc/passwd'}}).status_code==400
        assert c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)],'input_pairing':[{'path':str(bam),'assignment':'single'}]}).status_code==400
    assert before=={p:digest(p) for p in bam.parent.iterdir()}


def test_zero_exit_with_incomplete_actual_report_is_not_success(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    wrapper=bam.parent/'incomplete-mosdepth'
    wrapper.write_text(f'#!{sys.executable}\nimport subprocess,sys\nfrom pathlib import Path\ncode=subprocess.call([{MOSDEPTH!r},*sys.argv[1:]])\nif code==0 and "--version" not in sys.argv: Path(sys.argv[-2]+".mosdepth.summary.txt").write_text("chrom\\tlength\\tbases\\tmean\\tmin\\tmax\\n")\nsys.exit(code)\n')
    wrapper.chmod(0o700);config=replace(config,mosdepth=str(wrapper))
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam)]})
        run=wait(c,created.json()['id'])
        assert any(e['tool']=='mosdepth' and e['exit_code']==0 for e in run['executions'])
        assert run['state']=='failed' and not run['sample_count']
        assert not any(p['path'].startswith('qc/') for p in run['reports'])


def test_partial_results_keep_distinct_file_identities(coverage_inputs):
    config,bam,cram,ref,bed=coverage_inputs
    other=bam.parent/'second';other.mkdir();duplicate=other/bam.name
    shutil.copyfile(bam,duplicate)
    # Missing index is an independent per-file failure, not a renamed/merged read.
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(bam),str(duplicate)]})
        run=wait(c,created.json()['id'])
        assert run['state']=='partial' and run['sample_count']==1
        good,bad=run['qc']['results']
        assert good['state']=='completed' and bad['state']=='failed' and good['id']!=bad['id']
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':good['report']}).status_code==200
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':bad['report']}).status_code==403


@pytest.mark.parametrize('corrupt',[False,True])
def test_missing_or_corrupt_cram_index_is_not_rebuilt(coverage_inputs,corrupt):
    config,bam,cram,ref,bed=coverage_inputs
    idx=Path(str(cram)+'.crai')
    if corrupt:idx.write_bytes(b'corrupt CRAI')
    else:idx.unlink()
    before={p:digest(p) for p in cram.parent.iterdir()}
    with TestClient(create_app(config)) as c:
        auth(c,config)
        created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(cram)],'qc_options':{'reference':'test'}})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'])
        assert run['state']=='failed' and not any(e['tool']=='mosdepth' for e in run['executions'])
    assert before=={p:digest(p) for p in cram.parent.iterdir()}


def test_cram_coverage_ignores_remote_search_and_reference_cache(coverage_inputs,monkeypatch):
    import http.server,threading
    config,bam,cram,ref,bed=coverage_inputs;requests=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path);self.send_response(404);self.end_headers()
        def log_message(self,*args):pass
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        cache=ref.parent/'unwanted-cache'
        monkeypatch.setenv('REF_PATH',f'http://127.0.0.1:{server.server_port}/%s')
        monkeypatch.setenv('REF_CACHE',str(cache/'%2s/%2s/%s'))
        try:
            with TestClient(create_app(config)) as c:
                auth(c,config)
                created=c.post('/api/runs',json={'mode':'mosdepth','paths':[str(cram)],'qc_options':{'reference':'test'}})
                run=wait(c,created.json()['id'])
                assert run['state']=='completed',run['error']
            assert not requests and not cache.exists()
        finally:
            server.shutdown();thread.join()


def test_existing_benchmark_records_actual_coverage_resources(coverage_inputs,monkeypatch):
    import importlib.util
    config,bam,cram,ref,bed=coverage_inputs
    spec=importlib.util.spec_from_file_location('coverage_benchmark',Path(__file__).resolve().parents[2]/'scripts/benchmark-analysis.py')
    benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)
    monkeypatch.setenv('QUALIDOCK_SAMTOOLS',SAMTOOLS);monkeypatch.setenv('QUALIDOCK_MOSDEPTH',MOSDEPTH)
    monkeypatch.setenv('QUALIDOCK_COVERAGE_PANELS',json.dumps({'test':str(bed)}))
    output=bam.parent.parent/'benchmark'
    args=benchmark.parser().parse_args(['--input',str(bam),'--output',str(output),'--mode','mosdepth','--coverage-panel','test','--threads','1','--hash-inputs'])
    benchmark.main(args)
    evidence=json.loads((output/'benchmark.json').read_text())
    assert evidence['terminal_state']=='completed' and evidence['input_integrity_unchanged']
    assert evidence['hash_only_source_passes']==2 and evidence['registered_report_bytes']>0
    assert not evidence['derived_outputs'] and not evidence['unpublished_fastqs']
    assert evidence['waited_child_cpu_seconds']>0 and evidence['execution_stages']
    assert [s['tool'] for s in evidence['execution_stages']]==['samtools','samtools','samtools','mosdepth']
    retained=Path('validation/coverage/benchmark');shutil.copytree(output,retained,dirs_exist_ok=True)
