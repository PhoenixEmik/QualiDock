from pathlib import Path
import pytest
from pydantic import ValidationError
from qualidock.alignment import Options, header, parse_flagstat, parse_stats, readable, reference
from qualidock.config import Settings

FIXTURE=Path(__file__).parent/'fixtures/samtools-1.22.1'


def test_genuine_original_summaries_preserve_values_and_definitions():
    flagstat=parse_flagstat(FIXTURE/'flagstat.txt')
    assert flagstat['rows'][6]==['mapped (85.71% : 100.00%)','6','1']
    assert flagstat['rows'][11]==['properly paired (100.00% : N/A)','2','0']
    stats=parse_stats(FIXTURE/'stats.txt',flagstat)
    assert ['error rate:','0.000000e+00','# mismatches / bases mapped (cigar)'] in stats['rows']
    assert ['raw total sequences:','6','# excluding supplementary and secondary reads'] in stats['rows']


@pytest.mark.parametrize('change', ['truncate','duplicate','wrong-count','unknown-category','percentage'])
def test_invalid_flagstat_is_never_native_metrics(tmp_path,change):
    text=(FIXTURE/'flagstat.txt').read_text()
    if change=='percentage': text=text.replace('85.71%', 'NaN%')
    if change=='truncate': text='\n'.join(text.splitlines()[:-1])
    if change=='duplicate': text += text.splitlines()[0]+'\n'
    if change=='wrong-count': text=text.replace('6 + 1 mapped','900 + 1 mapped')
    if change=='unknown-category': text=text.replace('primary duplicates','imagined statistics')
    p=tmp_path/'flagstat.txt';p.write_text(text)
    with pytest.raises(ValueError): parse_flagstat(p)


@pytest.mark.parametrize('change',['nan','missing','duplicate','count'])
def test_invalid_or_inconsistent_stats(tmp_path,change):
    text=(FIXTURE/'stats.txt').read_text()
    if change=='nan': text=text.replace('0.000000e+00','NaN')
    if change=='missing': text='\n'.join(l for l in text.splitlines() if not l.startswith('SN\traw total'))
    if change=='duplicate': text+='SN\traw total sequences:\t6\n'
    if change=='count': text=text.replace('SN\traw total sequences:\t6','SN\traw total sequences:\t8')
    p=tmp_path/'stats.txt';p.write_text(text)
    with pytest.raises(ValueError): parse_stats(p,parse_flagstat(FIXTURE/'flagstat.txt'))


def test_header_requires_complete_local_reference_dictionary(tmp_path):
    p=tmp_path/'header.txt';p.write_text('@SQ\tSN:chr1\tLN:100\tUR:http://127.0.0.1/reference\n')
    assert header(p,{'contigs':{'chr1':100}})=={'chr1':100}
    for contigs in ({},{'chr1':99}):
        with pytest.raises(ValueError,match='fallback is forbidden'): header(p,{'contigs':contigs})
    p.write_text('@SQ\tSN:chr1\tLN:100\n@SQ\tSN:chr1\tLN:100\n')
    with pytest.raises(ValueError):header(p)


def test_options_and_reserved_htslib_paths(tmp_path):
    for options in ({'reference':'../escape'},{'multiqc':'yes'},{'paired':True},{'extra_args':'--ignore-md5'}):
        with pytest.raises(ValidationError):Options.model_validate(options)
    p=tmp_path/'x##idx##other.bam';p.touch()
    with pytest.raises(ValueError):readable(p)


def test_missing_reference_index_symlink_and_permissions(tmp_path):
    ref=tmp_path/'r.fa';ref.write_text('>chr1\nAAAA\n')
    config=Settings(roots=[tmp_path],output=tmp_path/'out',frontend=tmp_path,alignment_references={'test':str(ref)})
    with pytest.raises(OSError):reference(config,'test')
    fai=Path(str(ref)+'.fai');fai.write_text('chr1\t4\t6\t4\t5\n')
    assert reference(config,'test')['contigs']=={'chr1':4}
    fai.chmod(0o666)
    with pytest.raises(ValueError,match='writable'):reference(config,'test')
    fai.chmod(0o600);fai.unlink();fai.symlink_to(FIXTURE/'flagstat.txt')
    with pytest.raises((ValueError,OSError)):reference(config,'test')


def test_unavailable_alignment_tool_does_not_break_fastqc(client,setup):
    from test_workspace import wait
    settings,root=setup
    settings.samtools='/missing/samtools'
    assert not client.get('/api/config').json()['tools']['samtools']
    bam=root/'wrong.bam';bam.write_bytes(b'no')
    assert client.post('/api/runs',json={'mode':'samtools','paths':[str(bam)]}).status_code==400
    path=str(next(root.glob('*.fastq')))
    assert client.post('/api/runs',json={'mode':'samtools','paths':[path]}).status_code==400
    created=client.post('/api/runs',json={'mode':'fastqc','paths':[path]})
    assert created.status_code==201
    assert wait(client,created.json()['id'])['state']=='completed'


@pytest.mark.parametrize('version,library,compatible', [('1.24','1.24',True),('1.24rc1','1.24',False),('1.24','1.22.1',False),('1.22.1','1.24',False),('1.22.3','1.22.3',False),('1.23.2','1.23.2',False),('1.24','1.24.1',False),('1.25','1.25',False),('1.22.1','1.22.1',False)])
def test_explicit_version_contract(tmp_path,version,library,compatible):
    import asyncio,sys
    from qualidock.tools import detect_tool
    path=tmp_path/'samtools'
    path.write_text(f'#!{sys.executable}\nprint({f"samtools {version}\nUsing htslib {library}"!r})\n');path.chmod(0o700)
    assert asyncio.run(detect_tool('samtools',str(path)))['compatible'] is compatible


@pytest.mark.parametrize('configured',[None,False,'relative/reference.fa'])
def test_invalid_optional_reference_configuration_is_unavailable(tmp_path,configured):
    from qualidock.alignment import references
    config=Settings(roots=[tmp_path],output=tmp_path/'out',frontend=tmp_path,alignment_references={'test':configured})
    assert references(config)[0]['available'] is False
    with pytest.raises(ValueError):reference(config,'test')
