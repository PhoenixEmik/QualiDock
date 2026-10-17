from dataclasses import replace
from pathlib import Path
import shutil

import pytest
from qualidock import rseqc
from qualidock.config import Settings

FIXTURE = Path(__file__).parent/'fixtures/rseqc-5.0.5'


@pytest.fixture
def annotation_config(tmp_path):
    bed = tmp_path/'genes.bed12';shutil.copyfile(FIXTURE/'genes.bed12',bed)
    return Settings(roots=[tmp_path],output=tmp_path/'out',frontend=tmp_path/'frontend',rna_annotations={'genes':str(bed)}),bed


def test_genuine_report_fidelity_and_units():
    result = rseqc.infer(FIXTURE/'input.infer_experiment.txt',FIXTURE/'input.infer_experiment.log',200000)
    assert result['layout']=='PairEnd' and result['sampled_alignments']=='10'
    assert [r[1] for r in result['rows']]==['0.2000','0.6000','0.2000']
    distribution = rseqc.distribution(FIXTURE/'input.read_distribution.txt')
    assert distribution['totals']==[['Total Reads','10'],['Total Tags','11'],['Total Assigned Tags','11']]
    assert distribution['rows'][0]==['CDS_Exons','3000','7','2.33']
    assert distribution['rows'][3]==['Introns','6000','4','0.67']


def test_annotation_identity_is_full_sha_and_bounded_geometry(annotation_config):
    import hashlib
    config,bed=annotation_config;value=rseqc.annotation(config,'genes')
    assert value['sha256']==hashlib.sha256(bed.read_bytes()).hexdigest()
    assert value['transcripts']==4 and value['blocks']==8 and value['contigs']=={'chrRNA':24000}
    assert rseqc.annotations(config)[0]['available']


@pytest.mark.parametrize('column,value',[(0,''),(1,'-1'),(2,'500'),(4,'1001'),(5,'.'),(6,'900'),(7,'6000'),(8,'256,0,0'),(9,'3'),(10,'1000,1000,,'),(11,'0,500,'),(11,'0,2500,'),(3,'gene name')])
def test_invalid_bed12_never_silently_repaired(annotation_config,column,value):
    config,bed=annotation_config;fields=bed.read_text().splitlines()[0].split('\t');fields[column]=value
    bed.write_text('\t'.join(fields)+'\n')
    with pytest.raises(ValueError):rseqc.annotation(config,'genes')


@pytest.mark.parametrize('fault',['escape','writable','empty','columns','case-collision','line-limit','total-limit'])
def test_annotation_security_and_limits(annotation_config,monkeypatch,fault):
    config,bed=annotation_config
    if fault=='escape':
        target=bed.with_suffix('.outside');bed.rename(target);bed.symlink_to(target)
    elif fault=='writable':bed.chmod(0o666)
    elif fault=='empty':bed.write_text('# empty\n')
    elif fault=='columns':bed.write_text('chrRNA\t1\t2\n')
    elif fault=='case-collision':bed.write_text(bed.read_text()+bed.read_text().splitlines()[0].replace('chrRNA','CHRRNA')+'\n')
    elif fault=='line-limit':bed.write_bytes(b'#'+b'a'*16384+b'\n')
    else:monkeypatch.setattr(rseqc,'ANNOTATION_LIMIT',1)
    with pytest.raises((ValueError,OSError)):rseqc.annotation(config,'genes')
    assert not rseqc.annotations(config)[0]['available']


@pytest.mark.parametrize('bad',[{'annotation':'../escape'},{'annotation':'x','mapq':True},{'annotation':'x','sample_size':0},{'annotation':'x','sample_size':10000001},{'annotation':'x','mapq':256},{'annotation':'x','shell':'bad'}])
def test_strict_options(bad):
    with pytest.raises(ValueError):rseqc.InferOptions.model_validate(bad)


@pytest.mark.parametrize('replacement',['NaN','-0.1000','1.1000','0.9000'])
def test_invalid_fractions_are_not_statistics(tmp_path,replacement):
    path=tmp_path/'infer.txt';path.write_text((FIXTURE/'input.infer_experiment.txt').read_text().replace('0.6000',replacement))
    with pytest.raises(ValueError):rseqc.infer(path,FIXTURE/'input.infer_experiment.log',200000)


def test_incomplete_and_mixed_reports_distinguish_unavailable_from_zero(tmp_path):
    path=tmp_path/'report.txt';path.write_text('Unknown data type: Mixture\n')
    data=rseqc.infer(path,FIXTURE/'input.infer_experiment.log',200000)
    assert data['rows']==[] and data['status']=='unavailable'
    path.write_text('')
    with pytest.raises(ValueError):rseqc.infer(path,FIXTURE/'input.infer_experiment.log',200000)
    with pytest.raises(ValueError):rseqc.distribution(path)


@pytest.mark.parametrize('mutation',['totals','tag-count','header','missing','not-numeric'])
def test_malformed_distribution_is_not_published(tmp_path,mutation):
    text=(FIXTURE/'input.read_distribution.txt').read_text()
    if mutation=='totals':text=text.replace('Total Assigned Tags           11','Total Assigned Tags           12')
    elif mutation=='tag-count':text=text.replace('7                   2.33','12                  2.33')
    elif mutation=='header':text=text.replace('Tags/Kb','Percent')
    elif mutation=='missing':text='\n'.join(l for l in text.splitlines() if not l.startswith('Introns'))
    else:text=text.replace('2.33','NaN')
    p=tmp_path/'report.txt';p.write_text(text)
    with pytest.raises(ValueError):rseqc.distribution(p)


def test_invalid_optional_annotation_catalog_does_not_break_configuration(annotation_config):
    config,_=annotation_config
    assert rseqc.annotations(replace(config,rna_annotations=[]))[0]['available'] is False


@pytest.mark.parametrize('version,compatible',[('5.05',True),('5.0.4',False),('5.05rc1',False),('5.06',False)])
def test_version_probe_preserves_exact_upstream_cli_contract(tmp_path,version,compatible):
    import asyncio,sys
    from qualidock.tools import detect_tool
    path=tmp_path/'infer_experiment.py';path.write_text(f'#!{sys.executable}\nprint({("infer_experiment.py "+version)!r})\n');path.chmod(0o700)
    result=asyncio.run(detect_tool('rseqc_infer',str(path)))
    assert result['compatible'] is compatible
    if compatible:assert result['version']=='5.05' and result['suite_version']=='5.0.5'


def test_missing_optional_rna_tools_do_not_break_fastqc(client,setup):
    from test_workspace import wait
    settings,root=setup
    settings.rseqc_infer='/missing/infer_experiment.py'
    config=client.get('/api/config').json()
    assert not config['tools']['rseqc_infer'] and config['rna_annotations']==[]
    response=client.post('/api/runs',json={'mode':'fastqc','paths':[str(next(root.glob('*.fastq')))]})
    assert wait(client,response.json()['id'])['state']=='completed'


def test_separate_stderr_preserves_original_diagnostic_and_refuses_existing_paths(tmp_path):
    import asyncio,sys
    from qualidock.executor import LocalExecutor
    output,diagnostic,log=tmp_path/'out.txt',tmp_path/'error.log',tmp_path/'analysis.log'
    executor=LocalExecutor(1024)
    code=asyncio.run(executor.execute('test',[sys.executable,'-c','import sys;print("original stdout");print("original stderr",file=sys.stderr)'],tmp_path,log,1,stdout=output,stderr=diagnostic))
    assert code==0 and output.read_text()=='original stdout\n' and diagnostic.read_text()=='original stderr\n'
    assert 'original stderr' in log.read_text()
    protected=tmp_path/'private';protected.write_text('must remain')
    link=tmp_path/'linked.log';link.symlink_to(protected)
    with pytest.raises(FileExistsError):
        asyncio.run(executor.execute('refuse',[sys.executable,'-c','pass'],tmp_path,log,1,stderr=link))
    assert protected.read_text()=='must remain'
