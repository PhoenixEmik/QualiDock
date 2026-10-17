from pathlib import Path
import shutil
import pytest
from pydantic import ValidationError
from qualidock.coverage import Options, parse, panel, distribution
from qualidock.config import Settings

FIXTURE=Path(__file__).parent/'fixtures/mosdepth-0.3.14'
CONTIGS={'chr1':100,'chr2':50}


def copied(tmp_path):
    shutil.copytree(FIXTURE,tmp_path,dirs_exist_ok=True)
    settings=Settings(roots=[tmp_path],output=tmp_path/'out',frontend=tmp_path,coverage_panels={'test':str(tmp_path/'panel.bed')})
    return settings,panel(settings,'test')


def test_actual_precision_thresholds_and_omitted_denominators(tmp_path):
    config,bed=copied(tmp_path)
    data=parse(tmp_path,'coverage',CONTIGS,bed)
    assert data['total']==['total','100','25','0.25000','0','1']
    assert data['reported_reference_bases']==100 and data['header_reference_bases']==150
    assert data['omitted_references']==['chr2']
    assert data['requested_region_bases']==40 and data['reported_region_bases']==30
    assert data['distribution']['rows']==[['1','0.25000'],['0','1.00000']]
    assert data['regions']['rows'][-1]==['chr2','0','10','zero','0.00000']
    assert data['thresholds']['rows'][0]==['chr1','0','15','pair','15','0','0','0']


@pytest.mark.parametrize('mutation',['columns','missing-total','duplicate','wrong-length','bad-total'])
def test_malformed_summary_never_becomes_native_coverage(tmp_path,mutation):
    config,bed=copied(tmp_path);p=tmp_path/'coverage.mosdepth.summary.txt';text=p.read_text()
    if mutation=='columns':text=text.replace('mean','invented')
    if mutation=='missing-total':text='\n'.join(l for l in text.splitlines() if not l.startswith('total\t'))
    if mutation=='duplicate':text+='chr1\t100\t25\t0.25000\t0\t1\n'
    if mutation=='wrong-length':text=text.replace('chr1\t100','chr1\t101')
    if mutation=='bad-total':text=text.replace('total\t100\t25','total\t100\t999')
    p.write_text(text)
    with pytest.raises(ValueError):parse(tmp_path,'coverage',CONTIGS,bed)


@pytest.mark.parametrize('value',['NaN','1.1','-0.1'])
def test_nonfinite_or_invalid_cdf_fraction(tmp_path,value):
    path=tmp_path/'dist.txt';path.write_text('total\t1\t'+value+'\ntotal\t0\t1.00000\n')
    with pytest.raises(ValueError):distribution(path,{'total'})


def test_duplicate_or_nonmonotonic_bins_and_incomplete_cdf(tmp_path):
    p=tmp_path/'dist.txt'
    for text in ['total\t0\t1\ntotal\t0\t1\n','total\t1\t0.9\ntotal\t0\t0.5\n','total\t1\t0.5\n']:
        p.write_text(text)
        with pytest.raises(ValueError):distribution(p,{'total'})


@pytest.mark.parametrize('text',['chr1\t0\t0\n','chr1\t10\t5\n','chr1\t0\t10\nchr1\t5\t15\n','chr1 0 5','chr1\t0\t5\tx\nchr1\t8\t10\n'])
def test_invalid_or_overlapping_bed_is_not_silently_fixed(tmp_path,text):
    config,bed=copied(tmp_path);(tmp_path/'panel.bed').write_text(text)
    with pytest.raises(ValueError):panel(config,'test')


def test_bed_symlink_and_write_permissions(tmp_path):
    config,bed=copied(tmp_path);p=tmp_path/'panel.bed';p.chmod(0o666)
    with pytest.raises(ValueError):panel(config,'test')
    p.chmod(0o600);p.unlink();p.symlink_to((FIXTURE/'panel.bed').resolve())
    with pytest.raises(ValueError):panel(config,'test')


@pytest.mark.parametrize('value',[{'mapq':True},{'mapq':-1},{'mapq':256},{'panel':'../bad'},{'fast_mode':True},{'threads':8}])
def test_only_supported_coverage_options(value):
    with pytest.raises(ValidationError):Options.model_validate(value)


def test_missing_coverage_tool_is_optional_and_wrong_types_rejected(client,setup):
    from test_workspace import wait
    settings,root=setup;settings.mosdepth='/missing/mosdepth'
    assert not client.get('/api/config').json()['tools']['mosdepth']
    source=str(next(root.glob('*.fastq')))
    assert client.post('/api/runs',json={'mode':'mosdepth','paths':[source]}).status_code==400
    created=client.post('/api/runs',json={'mode':'fastqc','paths':[source]})
    assert wait(client,created.json()['id'])['state']=='completed'


def test_malformed_thresholds_and_corrupt_gzip_are_rejected(tmp_path):
    import gzip
    config,bed=copied(tmp_path);p=tmp_path/'coverage.thresholds.bed.gz'
    raw=gzip.decompress(p.read_bytes()).decode()
    for bad in (raw.replace('pair\t15','pair\t16'),raw.replace('pair\t15','other\t15')):
        p.write_bytes(gzip.compress(bad.encode()))
        with pytest.raises(ValueError):parse(tmp_path,'coverage',CONTIGS,bed)
    p.write_bytes(b'not gzip')
    with pytest.raises((ValueError,OSError)):parse(tmp_path,'coverage',CONTIGS,bed)
