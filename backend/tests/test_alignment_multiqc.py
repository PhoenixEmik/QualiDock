"""Official MultiQC modules against untouched, genuine upstream reports."""
import asyncio
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock import multiqc, optional_qc
from qualidock.tools import locate_tool
from test_workspace import wait

ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'backend/tests/fixtures'
MULTIQC=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
SAMTOOLS=shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
INFER=shutil.which(os.environ.get('QUALIDOCK_RSEQC_INFER','infer_experiment.py'))
DIST=shutil.which(os.environ.get('QUALIDOCK_RSEQC_DISTRIBUTION','read_distribution.py'))
JAR=locate_tool('picard',os.environ.get('QUALIDOCK_PICARD','picard.jar'))
if os.environ.get('QUALIDOCK_REQUIRE_RNA_MULTIQC_TESTS')=='1' and not all([MULTIQC,SAMTOOLS,INFER,DIST,JAR]):
    raise RuntimeError('Required genuine RNA/Picard/MultiQC executables missing')


def fixture(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/f'scripts/prepare-{name}-test.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def original_reports(tmp_path):
    reports=[]
    sources={}
    for n in (1,2):
        # Deliberately identical original Picard INPUT=basename, different report identities.
        for suffix,source in [('infer_experiment',FIX/'rseqc-5.0.5/input.infer_experiment.txt'),
                              ('read_distribution',FIX/'rseqc-5.0.5/input.read_distribution.txt'),
                              ('insert_size_metrics',FIX/'picard-3.5.0/paired.insert_size_metrics.txt')]:
            target=tmp_path/f'input-{n}'/f'i_{n}.{suffix}.txt';target.parent.mkdir(exist_ok=True)
            raw=source.read_bytes();target.write_bytes(raw);sources[target]=raw;reports.append(target)
    return reports,sources


@pytest.mark.skipif(not MULTIQC,reason='Actual MultiQC required')
def test_official_rna_picard_modules_collision_safe_and_exact(tmp_path):
    reports,sources=original_reports(tmp_path)
    version=subprocess.run([MULTIQC,'--version'],check=True,capture_output=True,text=True).stdout.strip().split()[-1]
    config={'picard_config':{'s_name_filenames':True}} if version=='1.25.1' else {'use_filename_as_sample_name':['picard']}
    cfg=tmp_path/'config.json';cfg.write_text(json.dumps(config))
    listing=tmp_path/'files.txt';listing.write_text(''.join(str(p)+'\n' for p in reports))
    output=tmp_path/'multiqc'
    subprocess.run([MULTIQC,'--file-list',str(listing),'--outdir',str(output),'--config',str(cfg),'--force','--no-version-check','--data-format','json'],check=True,capture_output=True)
    data=json.loads((output/'multiqc_data/multiqc_data.json').read_text());raw=data['report_saved_raw_data']
    summary=asyncio.run(multiqc.summary(tmp_path))
    for mode,suffix in [('rseqc-infer','infer_experiment'),('rseqc-distribution','read_distribution'),('picard','insert_size_metrics')]:
        selected=[p for p in reports if p.name.endswith(suffix+'.txt')]
        names=asyncio.run(multiqc.alignment_sample_names(tmp_path,mode))
        mapped=asyncio.run(multiqc.report_names(tmp_path,selected,summary,sample_names=names))
        assert len(mapped)==len(set(mapped.values()))==2 and None not in mapped.values()
        if mode=='rseqc-infer':
            for name in mapped.values():assert raw['multiqc_rseqc_infer_experiment'][name]=={'pe_sense':0.6,'pe_antisense':0.2,'failed':0.2}
        elif mode=='rseqc-distribution':
            for name in mapped.values():
                row=raw['multiqc_rseqc_read_distribution'][name]
                assert (row['total_reads'],row['total_tags'],row['cds_exons_tag_count'],row['introns_tag_count'])==(10,11,7,4)
                assert Decimal(str(row['introns_tags_kb']))==Decimal('0.67')
        else:
            for name in mapped.values():
                fr=raw['multiqc_picard_insertSize'][name+'_FR'];tandem=raw['multiqc_picard_insertSize'][name+'_TANDEM']
                assert (fr['READ_PAIRS'],fr['MEDIAN_INSERT_SIZE'],fr['MEAN_INSERT_SIZE'],fr['STANDARD_DEVIATION'])==(3,250,250,100)
                assert tandem['STANDARD_DEVIATION']=='?'
    assert all(path.read_bytes()==raw for path,raw in sources.items())
    evidence=Path('validation/rna-multiqc')/version;evidence.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(output/'multiqc_data/multiqc_data.json',evidence/'genuine-mixed-data.json')
    (evidence/'provenance.json').write_text(json.dumps({'multiqc':version,'config':config,'sources':{str(p):str(p) for p in sources}}))


def test_per_library_aggregation_is_explicitly_unsupported_not_silently_combined():
    with pytest.raises(ValueError,match='overlapping populations'):
        optional_qc.options('picard',{'by_library':True,'multiqc':True})
    assert optional_qc.options('picard',{'by_library':True})['multiqc'] is False


@pytest.mark.parametrize('mode',['picard','rseqc-infer','rseqc-distribution'])
@pytest.mark.parametrize('aggregation_failure',[False,True])
def test_application_originals_survive_aggregation_and_restart(tmp_path,mode,aggregation_failure):
    if not MULTIQC or not SAMTOOLS or (mode=='picard' and not JAR) or (mode!='picard' and not all([INFER,DIST])):
        pytest.skip('Genuine alignment/RNA/Picard tools required; mandatory in provisioned CI')
    if mode=='picard':bam=fixture('insert').prepare(tmp_path/'inputs',SAMTOOLS);bed=None
    else:bam,bed=fixture('rna').prepare(tmp_path/'inputs',SAMTOOLS)
    second=bam.parent/'other'/bam.name;second.parent.mkdir();shutil.copyfile(bam,second)
    originals={p:p.read_bytes() for p in bam.parent.rglob('*') if p.is_file()}
    executable=MULTIQC
    if aggregation_failure:
        wrapper=tmp_path/'failing-multiqc'
        wrapper.write_text(f'#!{sys.executable}\nimport os,sys\nif "--version" in sys.argv:os.execv({MULTIQC!r},[{MULTIQC!r},*sys.argv[1:]])\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index("--outdir")+1]);p.mkdir(exist_ok=True)\n(p/"multiqc_report.html").write_text("<h1>Incomplete diagnostic probe</h1>")\n(p/"incomplete.json").write_text("{{}}")\nsys.exit(9)\n');wrapper.chmod(0o700);executable=str(wrapper)
    config=Settings(roots=[bam.parent],output=tmp_path/'results',frontend=tmp_path/'frontend',samtools=SAMTOOLS,picard=JAR or 'picard.jar',
        multiqc=executable,rseqc_infer=INFER or 'infer_experiment.py',rseqc_distribution=DIST or 'read_distribution.py',
        rna_annotations={'genes':str(bed)} if bed else {},cpus=1,memory_mb=2048,allow_root=True)
    options={'multiqc':True,**({'annotation':'genes'} if bed else {})}
    with TestClient(create_app(config)) as c:
        c.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})
        created=c.post('/api/runs',json={'mode':mode,'paths':[str(bam),str(second)],'qc_options':options})
        assert created.status_code==201,created.text
        run=wait(c,created.json()['id'],timeout=120)
        assert run['state']==('partial' if aggregation_failure else 'completed'),run['error']
        assert run['sample_count']==2 and all(r['state']=='completed' for r in run['qc']['results'])
        for row in run['qc']['results']:
            response=c.get(f'/api/runs/{run["id"]}/download',params={'path':row['report']})
            assert response.status_code==200 and response.content==(config.output/run['id']/row['report']).read_bytes()
        if aggregation_failure:
            assert 'code 9' in run['error']
            assert (config.output/run['id']/'multiqc/multiqc_report.html').exists()
            assert not any(r['path'].startswith('multiqc/') for r in run['reports'])
            assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'multiqc/multiqc_report.html'}).status_code==403
        else:
            mappings=run['report_input_map'];assert len(mappings)==2 and len({r['multiqc_name'] for r in mappings.values()})==2
            assert c.get('/api/report-preview',params={'run_id':run['id'],'path':'multiqc/multiqc_report.html'}).status_code==200
        shutil.copytree(config.output/run['id'],Path('validation/rna-multiqc')/(mode+('-failed' if aggregation_failure else '-success')),dirs_exist_ok=True)
    with TestClient(create_app(config)) as c:
        c.headers.update({'Authorization':'Bearer '+config.token,'X-QualiDock-Request':'1'})
        restored=c.get('/api/runs/'+run['id']).json()
        assert restored['report_input_map']==run['report_input_map'] and restored['qc']==run['qc']
        assert restored['reports']==run['reports']
        if aggregation_failure:assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'multiqc/multiqc_report.html'}).status_code==403
        assert c.get('/api/runs/'+run['id']+'/configuration').json()['qc_options']['multiqc']
    assert all(p.read_bytes()==raw for p,raw in originals.items())


@pytest.mark.skipif(not MULTIQC,reason='Actual MultiQC required')
def test_original_genebody_report_values_and_source_mapping(tmp_path):
    source=FIX/'rseqc-5.0.5/genebody/gene-body.geneBodyCoverage.txt'
    report=tmp_path/'input.geneBodyCoverage.txt';report.write_bytes(source.read_bytes())
    listing=tmp_path/'files.txt';listing.write_text(str(report)+'\n')
    subprocess.run([MULTIQC,'--file-list',str(listing),'--outdir',str(tmp_path/'multiqc'),'--force','--no-version-check','--data-format','json'],check=True,capture_output=True)
    data=json.loads((tmp_path/'multiqc/multiqc_data/multiqc_data.json').read_text())
    rows=data['report_saved_raw_data']['rseqc_gene_body_cov']['input']
    expected=source.read_text().splitlines()[1].split('\t')[1:]
    assert [Decimal(str(rows[str(i)])) for i in range(1,101)]==list(map(Decimal,expected))
    names=asyncio.run(multiqc.alignment_sample_names(tmp_path,'rseqc-genebody'))
    mapping=asyncio.run(multiqc.report_names(tmp_path,[report],sample_names=names))
    assert mapping=={report.name:'input'}
    assert report.read_bytes()==source.read_bytes()
    version=subprocess.run([MULTIQC,'--version'],check=True,capture_output=True,text=True).stdout.strip().split()[-1]
    saved=Path('validation/rna-multiqc')/version;saved.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(tmp_path/'multiqc/multiqc_data/multiqc_data.json',saved/'genebody-data.json')
