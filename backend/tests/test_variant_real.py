"""Actual BCFtools, unchanged source bytes and authenticated run lifecycle."""
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

TOOL=shutil.which(os.environ.get('QUALIDOCK_BCFTOOLS','bcftools'))
if os.environ.get('QUALIDOCK_REQUIRE_VARIANT_TESTS')=='1' and not TOOL:raise RuntimeError('Genuine BCFtools 1.24 required')
pytestmark=pytest.mark.skipif(not TOOL,reason='Genuine BCFtools unavailable; mandatory in provisioned CI')
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('prepare_variants',ROOT/'scripts/prepare-variant-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def auth(c,s):c.headers.update({'Authorization':'Bearer '+s.token,'X-QualiDock-Request':'1'})
def hashes(root):return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def inputs(tmp_path):
    paths=fixture.prepare(tmp_path/'inputs',TOOL)
    settings=Settings(roots=[tmp_path/'inputs'],output=tmp_path/'results',frontend=tmp_path/'frontend',bcftools=TOOL,java='/missing/java',cpus=1,memory_mb=1024,allow_root=True)
    return settings,paths


@pytest.mark.parametrize('case',['snps','indels','mixed','multisample','missing-depth','no-genotype','missing-alleles','symbolic','gvcf','empty','gzip','bgzf','bcf','uncompressed-bcf','raw-bcf','vcf42','multisample-bcf','multisample-bgzf'])
def test_actual_formats_original_report_source_identity_and_restart(inputs,case):
    settings,paths=inputs;source=paths[case];before=hashes(source.parent)
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/config').status_code==401
        auth(c,settings)
        entries=c.get('/api/files',params={'path':str(source.parent)}).json()['entries']
        item=next(e for e in entries if e['name']==source.name)
        assert item['kind']=='variant' and item['read'] is None and not item['paired']
        response=c.post('/api/runs',json={'mode':'bcftools','paths':[str(source)]})
        assert response.status_code==201,response.text
        run=wait(c,response.json()['id'],timeout=60)
        assert run['state']=='completed',(run['error'],(settings.output/run['id']/'analysis.log').read_text())
        assert run['sample_count']==1 and not run['input_pairing'] and not run['sample_groups'] and not run['sample_input_paths'] and not run.get('derived_datasets')
        row=run['qc']['results'][0]
        execution=next(e for e in run['executions'] if e['tool']=='bcftools')
        expected=subprocess.run(execution['argv'],check=True,capture_output=True).stdout
        downloaded=c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']})
        assert downloaded.status_code==200 and downloaded.content==expected
        sn=[line.split('\t')[2:] for line in expected.decode().splitlines() if line.startswith('SN\t')]
        assert row['variant']['summary']['rows']==sn
        assert run['tools']['bcftools']['version']==run['tools']['bcftools']['htslib_version']=='1.24'
        assert execution['argv'][1:4]==['stats','--threads','0'] and len(run['executions'])==1
        assert execution['environment']=={'REF_PATH':'/dev/null','REF_CACHE':'/dev/null','HTS_PATH':'','BCFTOOLS_PLUGINS':''}
        assert c.get('/api/history?mode=bcftools').json()['total']==1
        draft=c.get(f'/api/runs/{run["id"]}/configuration').json()
        assert draft['mode']=='bcftools' and draft['qc_options']=={'per_sample':False,'multiqc':False}
        assert not any(p.suffix in {'.vcf','.bcf','.gz','.tbi','.csi'} for p in (settings.output/run['id']).rglob('*'))
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        restored=c.get('/api/runs/'+run['id']).json()
        assert restored['qc']==run['qc'] and restored['reports']==run['reports']
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']}).content==expected
    assert hashes(source.parent)==before


@pytest.mark.parametrize('case',['multisample','missing-depth','no-genotype','gvcf'])
def test_explicit_sample_statistics_and_sample_absence_contract(inputs,case):
    settings,paths=inputs
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        assert c.post('/api/runs',json={'mode':'bcftools','paths':[str(paths['snps'])],'qc_options':{'per_sample':True}}).status_code==400
        response=c.post('/api/runs',json={'mode':'bcftools','paths':[str(paths[case])],'qc_options':{'per_sample':True}})
        assert response.status_code==201,response.text
        run=wait(c,response.json()['id'],timeout=60)
        assert run['state']=='completed',run['error']
        assert '--samples' in run['executions'][0]['argv']
        assert run['qc']['results'][0]['variant']['sample_statistics_available'] is (case!='no-genotype')


def test_partial_inputs_fail_without_publishing_incomplete_reports(inputs):
    settings,paths=inputs
    invalid=paths['snps'].with_name('bad-body.vcf')
    invalid.write_text(paths['snps'].read_text().replace('chr1\t20','chr1\tnot-a-coordinate'))
    before=hashes(invalid.parent)
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        created=c.post('/api/runs',json={'mode':'bcftools','paths':[str(paths['mixed']),str(invalid)]})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'],timeout=60)
        assert run['state']=='partial' and run['sample_count']==1
        failed=next(r for r in run['qc']['results'] if r['state']=='failed')
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':failed['report']}).status_code==403
        assert not any(r['path'].startswith('qc/'+failed['id']+'/') for r in run['reports'])
    assert before==hashes(invalid.parent)


@pytest.mark.parametrize('interrupt',[False,True])
def test_cancel_and_restart_do_not_publish_unverified_stats(inputs,interrupt):
    settings,paths=inputs
    wrapper=settings.output.parent/'held-bcftools'
    wrapper.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "--version" not in sys.argv:time.sleep(30)\nos.execv({TOOL!r},[{TOOL!r},*sys.argv[1:]])\n');wrapper.chmod(0o700)
    settings=replace(settings,bcftools=str(wrapper))
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        created=c.post('/api/runs',json={'mode':'bcftools','paths':[str(paths['mixed'])]})
        assert created.status_code==201,created.text
        for _ in range(200):
            run=c.get('/api/runs/'+created.json()['id']).json()
            if run['executions']:break
            time.sleep(.02)
        else:raise AssertionError('Real BCFtools execution was not reached')
        if not interrupt:
            assert c.post('/api/runs/'+run['id']+'/cancel').status_code==200
            assert wait(c,run['id'])['state']=='cancelled'
    with TestClient(create_app(settings)) as c:
        auth(c,settings);restored=c.get('/api/runs/'+run['id']).json()
        assert restored['state']==('interrupted' if interrupt else 'cancelled')
        assert not any(r['path'].startswith('qc/') for r in restored['reports'])
