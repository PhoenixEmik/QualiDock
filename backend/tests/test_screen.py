"""FastQ Screen validation uses untouched genuine summary output as its baseline."""
from dataclasses import replace
from pathlib import Path
import pytest
from qualidock.config import Settings
from qualidock.fastq_screen import panel, listing, parse_report, Options, safe_path

FIXTURE=Path(__file__).parent/'fixtures/fastq-screen-0.16.0'


def test_original_summary_exact_columns_and_precision():
    value=parse_report(FIXTURE/'reads_screen.txt',['alpha','beta'],10,20)
    assert value['processed_reads']==20 and value['no_genome_percent']=='10.00'
    assert value['rows'][0][2:6]==['8','40.00','12','60.00']
    assert value['columns'][10]=='Multiple_hits_multiple_genomes'


@pytest.mark.parametrize('before,after',[
    ('version: 0.16.0','version: 0.17.0'), ('#Aligner: bowtie2','#Aligner: bwa'),
    ('subset: 10','subset: 0'), ('alpha\t20','unknown\t20'),
    ('alpha\t20\t8','alpha\t20\t9'), ('60.00','nan'),
    ('%Hit_no_genomes: 10.00','%Hit_no_genomes: 101.00'),
    ('beta\t20','alpha\t20'), ('#Reads_processed','Read counts'),
])
def test_invalid_or_incompatible_summary(tmp_path,before,after):
    text=(FIXTURE/'reads_screen.txt').read_text();assert before in text
    path=tmp_path/'broken.txt';path.write_text(text.replace(before,after))
    with pytest.raises(ValueError):parse_report(path,['alpha','beta'],10,20)


@pytest.mark.parametrize('options',[{'panel':'../escape'},{'panel':'valid','subset':False},{'panel':'valid','subset':0},
                                   {'panel':'valid','subset':1000001},{'panel':'valid','paired':True},{'panel':'valid','filter':'0000'}])
def test_no_untrusted_flags_or_filtering(options):
    with pytest.raises(ValueError):Options.model_validate(options)


def test_panel_safety_snapshots_missing_indexes_and_symlinks(tmp_path):
    # Bytes are placeholders for config validation only; no tool success is mocked.
    prefix=tmp_path/'alpha'
    for suffix in ('1','2','3','4','rev.1','rev.2'):(tmp_path/f'alpha.{suffix}.bt2').write_bytes(b'config-only placeholder')
    conf=tmp_path/'panel.conf';conf.write_text(f'DATABASE alpha {prefix}\n')
    settings=Settings(roots=[tmp_path],output=tmp_path/'results',frontend=tmp_path,nanoq='missing',bowtie2='/usr/bin/true',screen_panels={'approved':str(conf)})
    value=panel(settings,'approved');assert value['sha256'] and len(value['references'][0]['indexes'])==6
    with pytest.raises(ValueError):panel(settings,'arbitrary')
    for path in ['/tmp/space path','/tmp/$(touch_X)','/tmp/quote\'','/tmp/line\nnext']:
        with pytest.raises(ValueError):safe_path(Path(path))
    for line in ['BWA /bin/sh\n',f'DATABASE <script> {prefix}\n',f'DATABASE alpha {prefix};touch\n']:
        conf.write_text(line)
        assert not listing(settings)[0]['available']
    conf.write_text(f'DATABASE alpha {prefix}\n');conf.chmod(0o666)
    with pytest.raises(ValueError,match='writable'):panel(settings,'approved')
    conf.chmod(0o600)
    index=tmp_path/'alpha.1.bt2';index.unlink();index.symlink_to(tmp_path/'alpha.2.bt2')
    assert not listing(settings)[0]['available']
    conf.unlink();conf.symlink_to(tmp_path/'alpha.2.bt2')
    assert not listing(settings)[0]['available']
    assert not listing(replace(settings,screen_panels={'missing':'/missing/config'}))[0]['available']
    assert not listing(replace(settings,screen_panels=['invalid']))[0]['available']
